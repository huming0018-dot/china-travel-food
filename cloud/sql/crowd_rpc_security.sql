-- ============================================================
-- crowd_rpc_security.sql — 众包安全加固：插件只走 RPC，不再直连表
-- PM 窗口 · 2026-10-02 · 在 Supabase SQL Editor / Management API 执行
--
-- 架构决策（smoke 审计结论）：
--   旧方案：插件用 anon key 直接 SELECT crowd_tasks / INSERT crowd_proofs
--   → 失败：crowd_tasks/proofs 无 anon policy → 插件拉不到任务、回传被 42501 拒
--   → 且 participants 的 anon SELECT(pending or approved) 会泄漏全部参与者
--   新方案：插件只用 anon key 调用 RPC（security definer，以函数owner权限执行）
--     crowd_fetch_tasks(pid)   → 校验 approved → 返回 open 任务包
--     crowd_submit_proof(pid, envelope jsonb) → 服务端校验 → 落库+回写
--   anon 对 4 张表零权限（报名 insert 除外），任何绕过 RPC 的直连都失败
-- ============================================================

-- ------------------------------------------------------------
-- 0) 撤销危险的 participants anon SELECT（防泄漏他人 contact/编号）
-- ------------------------------------------------------------
drop policy if exists "crowd_apply_self_read" on public.crowd_participants;

-- ------------------------------------------------------------
-- 1) crowd_fetch_tasks(pid) — 插件领任务（security definer）
--    校验：参与者存在且 approved；返回 status=open 任务包（不含 progress 细节）
-- ------------------------------------------------------------
create or replace function public.crowd_fetch_tasks(p_participant_id text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_status text;
  v_rows jsonb;
begin
  -- 参与者管控闸门（与 ingest 一致的口径）
  select status into v_status
    from public.crowd_participants
   where participant_id = p_participant_id;
  if v_status is null then
    return jsonb_build_object('ok', false, 'reason', 'participant_not_found');
  end if;
  if v_status <> 'approved' then
    return jsonb_build_object('ok', false, 'reason', 'participant_status_' || v_status);
  end if;

  select coalesce(jsonb_agg(jsonb_build_object(
           'task_id', t.task_id,
           'pack_type', t.pack_type,
           'pack', t.pack,
           'target', t.target,
           'kpi_min', t.kpi_min,
           'quota_day', t.quota_day
         ) order by t.task_id), '[]'::jsonb)
    into v_rows
    from public.crowd_tasks t
   where t.status = 'open';

  return jsonb_build_object('ok', true, 'tasks', v_rows);
end;
$$;

revoke all on function public.crowd_fetch_tasks(text) from public;
grant execute on function public.crowd_fetch_tasks(text) to anon, authenticated, service_role;

-- ------------------------------------------------------------
-- 2) crowd_submit_proof(pid, envelope jsonb) — 插件回传（security definer）
--    服务端校验：approved → sync_version=1 → 幂等 → 域名/字段规则
--    返回逐条结果：{ok, accepted: N, rejected: [...], new_progress}
-- ------------------------------------------------------------
create or replace function public.crowd_submit_proof(p_participant_id text, p_envelope jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_status      text;
  v_task_id     bigint;
  v_seq         int;
  v_sync        int;
  v_items       jsonb;
  v_item        jsonb;
  v_kind        text;
  v_note_id     text;
  v_note_url    text;
  v_title       text;
  v_excerpt     text;
  v_author      text;
  v_rating      numeric;
  v_rating_reason text;
  v_matched     text;
  v_anchor      float;
  v_raw         text;
  v_captured    timestamptz;
  v_result      jsonb := '[]'::jsonb;
  v_accepted    int := 0;
  v_rejected    text[] := '{}';
  v_task_open   boolean;
  v_new_progress int;
  v_row         jsonb;
  v_quota       int;
  v_today_used  int;
begin
  -- ① 参与者管控闸门
  select status into v_status
    from public.crowd_participants
   where participant_id = p_participant_id;
  if v_status is null then
    return jsonb_build_object('ok', false, 'reason', 'participant_not_found');
  end if;
  if v_status <> 'approved' then
    return jsonb_build_object('ok', false, 'reason', 'participant_status_' || v_status);
  end if;

  -- ② 信封结构
  v_task_id := (p_envelope->>'task_id')::bigint;
  v_seq     := (p_envelope->>'proof_seq')::int;
  v_sync    := coalesce((p_envelope->>'sync_version')::int, 1);
  v_captured:= coalesce((p_envelope->>'captured_at')::timestamptz, now());
  v_items   := coalesce(p_envelope->'items', '[]'::jsonb);

  if v_sync <> 1 then
    return jsonb_build_object('ok', false, 'reason', 'sync_version_mismatch',
                              'expected', 1, 'got', v_sync);
  end if;
  if v_task_id is null or v_seq is null then
    return jsonb_build_object('ok', false, 'reason', 'envelope_missing_task_or_seq');
  end if;

  -- ②b 【安全】envelope内 participant_id 必须与调用参数一致（防跨参与者污染他人记录）
  if coalesce(p_envelope->>'participant_id','') <> p_participant_id then
    return jsonb_build_object('ok', false, 'reason', 'participant_id_mismatch');
  end if;

  -- ③ 任务必须存在且 open
  select (status = 'open') into v_task_open
    from public.crowd_tasks where task_id = v_task_id;
  if v_task_open is distinct from true then
    return jsonb_build_object('ok', false, 'reason', 'task_not_open');
  end if;

  -- ③b 【安全】日配额强制：当日已 accepted 条数 ≥ quota_day 即拒（防刷单/DoS）
  select quota_day into v_quota
    from public.crowd_participants where participant_id = p_participant_id;
  select count(*) into v_today_used
    from public.crowd_proofs
   where participant_id = p_participant_id
     and gate_status = 'accepted'
     and created_at >= date_trunc('day', now());
  if coalesce(v_quota, 0) > 0 and v_today_used >= v_quota then
    return jsonb_build_object('ok', false, 'reason', 'quota_exceeded',
                              'quota_day', v_quota, 'used_today', v_today_used);
  end if;

  -- ④ 逐条校验+落库（幂等键由唯一约束兜底，重复静默跳过）
  for v_item in select * from jsonb_array_elements(v_items) loop
    v_kind  := v_item->>'kind';
    v_note_id := v_item->>'note_id';
    v_note_url := v_item->>'note_url';
    v_title := v_item->>'title';
    v_excerpt := left(coalesce(v_item->>'excerpt',''), 200);
    v_author  := v_item->>'author';
    v_rating  := (v_item->>'rating')::numeric;
    v_rating_reason := v_item->>'rating_reason';
    v_matched := v_item->>'matched_store';
    v_anchor  := (v_item->>'anchor_score')::float;
    v_raw     := v_item->>'raw_query';

    -- 字段级校验
    if v_kind not in ('note','rating') then
      v_rejected := v_rejected || format('item_kind_invalid:%s', coalesce(v_note_id,'?'));
      continue;
    end if;
    if v_note_id is null or v_note_url is null then
      v_rejected := v_rejected || format('item_missing_note:%s', coalesce(v_note_id,'?'));
      continue;
    end if;
    if position('xiaohongshu.com' in v_note_url) = 0 then
      v_rejected := v_rejected || format('item_url_not_xhs:%s', v_note_id);
      continue;
    end if;
    if v_kind = 'rating' and (v_rating is null or v_rating < 1 or v_rating > 5) then
      v_rejected := v_rejected || format('item_rating_out_of_range:%s', v_note_id);
      continue;
    end if;
    if v_kind = 'rating' and coalesce(length(v_rating_reason),0) < 8 then
      v_rejected := v_rejected || format('item_rating_reason_too_short:%s', v_note_id);
      continue;
    end if;

    -- 幂等写入（唯一约束冲突=已存在，静默跳过）
    begin
      insert into public.crowd_proofs
        (participant_id, task_id, proof_seq, captured_at, sync_version,
         kind, note_id, note_url, title, excerpt, author,
         rating, rating_reason, matched_store, anchor_score, raw_query,
         gate_status, dedupe_key)
      values
        (p_participant_id, v_task_id, v_seq, v_captured, v_sync,
         v_kind, v_note_id, v_note_url, v_title, v_excerpt, v_author,
         v_rating, v_rating_reason, v_matched, v_anchor, v_raw,
         'accepted', md5(coalesce(v_title,'') || '|' || coalesce(v_note_id,'')))
      on conflict (participant_id, task_id, proof_seq, note_id) do nothing;
      if found then
        v_accepted := v_accepted + 1;
        v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'accepted');
      else
        v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
      end if;
    exception when others then
      v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'error', 'msg', SQLERRM);
    end;
    v_result := v_result || v_row;
  end loop;

  -- ⑤ 回写任务进度 + 参与者累计（只在有新增 accepted 时）
  if v_accepted > 0 then
    update public.crowd_tasks
       set progress = progress + v_accepted,
           status = case when progress + v_accepted >= kpi_min then 'fulfilled' else status end,
           updated_at = now()
     where task_id = v_task_id;
    update public.crowd_participants
       set total_effective = total_effective + v_accepted,
           last_active_at = now()
     where participant_id = p_participant_id;
  end if;

  select progress into v_new_progress from public.crowd_tasks where task_id = v_task_id;

  return jsonb_build_object(
    'ok', true,
    'accepted', v_accepted,
    'rejected', v_rejected,
    'results', v_result,
    'new_progress', coalesce(v_new_progress, 0)
  );
end;
$$;

revoke all on function public.crowd_submit_proof(text, jsonb) from public;
grant execute on function public.crowd_submit_proof(text, jsonb) to anon, authenticated, service_role;

-- ------------------------------------------------------------
-- 3) 兜底：显式收窄 anon 权限（默认已 deny，双保险）
-- ------------------------------------------------------------
revoke select, insert, update, delete on public.crowd_tasks       from anon;
revoke select, insert, update, delete on public.crowd_proofs      from anon;
revoke select, insert, update, delete on public.crowd_reviews     from anon;
revoke select, insert, update, delete on public.crowd_settlements from anon;
-- participants：仅保留报名 insert(pending)；SELECT 已撤销策略
revoke select, update, delete on public.crowd_participants from anon;

-- 验证：
--   select public.crowd_fetch_tasks('P-TEST') ;
--   select public.crowd_submit_proof('P-TEST', '{"task_id":1,"proof_seq":1,"sync_version":1,"captured_at":"2026-10-02T00:00:00Z","items":[]}');
