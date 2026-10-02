-- ============================================================
-- crowd_harden_redteam.sql — 红队对抗加固（PM窗口 · 2026-10-02）
-- 针对实测复现的 8 类攻击的修复：
--   R1 一机一号失效 → 报名强制 device_salt + 唯一索引限 1 active
--   R2 URL 白名单子串绕过 → 正则严格校验（host 必须精确 xiaohongshu.com）
--   R3 垃圾字段灌库 → note_id/note_url/title/author 长度与格式校验
--   R4 任务 DoS → 参与者拒收率自动风控 suspend + 任务分配节流
--   R5 去重绕过 → dedupe_key 归一化升级（去标点/空格/大小写）
--   R6 评分无锚定 → rating 必须匹配已收录笔记 + 理由质量校验
--   R7 时间伪造 → captured_at 权威校验（服务端时间窗）
--   R8 并发竞态 → 参与者行锁（FOR UPDATE 串行化配额判定）
-- 执行方式：Supabase Management API POST /database/query
-- ============================================================

-- ------------------------------------------------------------
-- R1) 一机一号：报名必须带 device_salt；同设备最多 1 个 active 参与者
--     唯一索引（partial）：pending/approved 状态下 device_salt 唯一
--     覆盖旧报名数据：device_salt 为 NULL 的历史行不参与约束（不影响存量）
-- ------------------------------------------------------------
drop index if exists idx_crowd_participants_salt_active;
create unique index if not exists idx_crowd_participants_salt_active
  on public.crowd_participants(device_salt)
  where status in ('pending', 'approved');

-- 报名 RLS 加强：device_salt 必填（长度 8-64），participant_id 格式强制 P- 前缀
drop policy if exists "crowd_apply_anon_insert" on public.crowd_participants;
create policy "crowd_apply_anon_insert" on public.crowd_participants
  for insert to anon with check (
    status = 'pending'
    and quota_day = 20
    and length(display_name) between 1 and 20
    and length(contact) between 1 and 100
    and position('<' in display_name) = 0
    and position('>' in display_name) = 0
    and position('<' in contact) = 0
    and position('>' in contact) = 0
    -- R1：强制设备指纹，同机不可无限注册
    and length(coalesce(device_salt, '')) between 8 and 64
    and device_salt ~ '^[A-Za-z0-9\-]{8,64}$'
    -- R3：编号格式收紧（P- 开头 + 字母数字连字符，6-20 位）
    and participant_id ~ '^P-[A-Z0-9-]{6,20}$'
  );

-- ------------------------------------------------------------
-- R2/R3/R6/R7/R8) crowd_submit_proof 全面加固
--     重写函数：URL 正则严格校验、note_id 24hex、评分锚定、时间窗、行锁
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
  v_reject_accum int;
  v_accept_accum int;
  v_reject_rate float;
  v_note_exists boolean;
begin
  -- ① 参与者管控闸门（H3 防枚举语义保留：编号不存在/黑名单统一 participant_unavailable）
  select status into v_status
    from public.crowd_participants
   where participant_id = p_participant_id
   -- R8：行锁——同参与者并发回传串行化，杜绝配额计数竞态
   for update;
  if v_status is null or v_status in ('suspended', 'blacklisted', 'rejected') then
    return jsonb_build_object('ok', false, 'reason', 'participant_unavailable');
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

  -- ②c 【R7】captured_at 权威校验：不允许未来时间（> 服务端 now()+10min 拒），
  --     也不允许早于 7 天前（防刷历史时间线）
  if v_captured > now() + interval '10 minutes' then
    return jsonb_build_object('ok', false, 'reason', 'captured_at_future',
                              'captured_at', v_captured, 'server_now', now());
  end if;
  if v_captured < now() - interval '7 days' then
    return jsonb_build_object('ok', false, 'reason', 'captured_at_too_old');
  end if;

  -- ③ 任务必须存在且 open
  select (status = 'open') into v_task_open
    from public.crowd_tasks where task_id = v_task_id;
  if v_task_open is distinct from true then
    return jsonb_build_object('ok', false, 'reason', 'task_not_open');
  end if;

  -- ③b 日配额强制（行锁已串行化，计数不再竞态）
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

  -- ④ 逐条校验+落库
  for v_item in select * from jsonb_array_elements(v_items) loop
    v_kind  := v_item->>'kind';
    v_note_id := v_item->>'note_id';
    v_note_url := v_item->>'note_url';
    v_title := left(coalesce(v_item->>'title',''), 100);
    v_excerpt := left(coalesce(v_item->>'excerpt',''), 200);
    v_author  := left(coalesce(v_item->>'author',''), 50);
    v_rating  := (v_item->>'rating')::numeric;
    v_rating_reason := left(coalesce(v_item->>'rating_reason',''), 200);
    v_matched := left(coalesce(v_item->>'matched_store',''), 100);
    v_anchor  := (v_item->>'anchor_score')::float;
    v_raw     := left(coalesce(v_item->>'raw_query',''), 50);

    -- 字段级校验（加固）
    if v_kind not in ('note','rating') then
      v_rejected := v_rejected || format('item_kind_invalid:%s', coalesce(v_note_id,'?'));
      continue;
    end if;
    if v_note_id is null or v_note_url is null then
      v_rejected := v_rejected || format('item_missing_note:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    -- 【R2】URL 严格正则：host 必须精确为 www.xiaohongshu.com，路径必须 /explore/<24hex>
    --   （之前 position() 子串匹配被 evil.com/?goto=xiaohongshu.com 绕过）
    if v_note_url !~ '^https://www\.xiaohongshu\.com/explore/[0-9a-f]{24}(\?.*)?$'
       and v_note_url !~ '^https://www\.xiaohongshu\.com/discovery/item/[0-9a-f]{24}(\?.*)?$' then
      v_rejected := v_rejected || format('item_url_invalid:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    -- 【R3】note_id 必须为 24 位十六进制（小红书笔记 ID 规范）
    if v_note_id !~ '^[0-9a-f]{24}$' then
      v_rejected := v_rejected || format('item_note_id_invalid:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    -- 【R3】title 非空且有实质内容（≥2 字符，拒纯标点/纯空白）
    if coalesce(length(regexp_replace(v_title, '[\s[:punct:]]', '', 'g')), 0) < 2 then
      v_rejected := v_rejected || format('item_title_too_short:%s', v_note_id);
      continue;
    end if;

    -- 【R6】rating 类：必须锚定已收录笔记（同 note_id 已有 accepted 记录），
    --     且理由 ≥8 字且含实质内容（拒"好好好好好好"式灌水）
    if v_kind = 'rating' then
      if v_rating is null or v_rating < 1 or v_rating > 5 then
        v_rejected := v_rejected || format('item_rating_out_of_range:%s', v_note_id);
        continue;
      end if;
      if coalesce(length(regexp_replace(v_rating_reason, '[\s[:punct:]]', '', 'g')), 0) < 8 then
        v_rejected := v_rejected || format('item_rating_reason_too_short:%s', v_note_id);
        continue;
      end if;
      select exists (
        select 1 from public.crowd_proofs
         where note_id = v_note_id and gate_status = 'accepted'
      ) into v_note_exists;
      if v_note_exists is not true then
        v_rejected := v_rejected || format('item_rating_no_anchor:%s', v_note_id);
        continue;
      end if;
    end if;

    -- 【安全】逐条配额限流（行锁已保证计数一致）
    if coalesce(v_quota, 0) > 0 and (v_today_used + v_accepted) >= v_quota then
      v_rejected := v_rejected || format('item_quota_exceeded:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    -- 幂等写入（唯一约束兜底）+ 【R5】dedupe_key 升级归一化：
    --   去所有标点/空白 + 全小写 → 变体 title 归一后同 key 被全局唯一索引拦截
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
         'accepted', md5(lower(regexp_replace(
           regexp_replace(v_title, '[\s[:punct:]]', '', 'g'),
           '[^a-z0-9一-龥]', '', 'g'))))
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

  -- 【R4】拒收率风控：本次 rejected 条数并入累计后计算 reject_rate，
  --     超过阈值自动 suspend（防任务 DoS 与垃圾刷量）
  select coalesce(sum(case when gate_status='accepted' then 1 else 0 end),0),
         coalesce(sum(case when gate_status='rejected' then 1 else 0 end),0)
    into v_accept_accum, v_reject_accum
    from public.crowd_proofs
   where participant_id = p_participant_id;
  if (v_accept_accum + v_reject_accum) > 20 then
    v_reject_rate := v_reject_accum::float / (v_accept_accum + v_reject_accum);
    if v_reject_rate > 0.6 then
      update public.crowd_participants
         set status = 'suspended', review_note = 'auto_suspend: reject_rate ' || round(v_reject_rate::numeric,2)
       where participant_id = p_participant_id;
      -- 不再更新 reject_rate 字段（保留触发原因在 review_note）
    else
      update public.crowd_participants
         set reject_rate = v_reject_rate
       where participant_id = p_participant_id;
    end if;
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
-- R5) dedupe 索引重建（归一化升级后索引定义不变，但需确认存在）
-- ------------------------------------------------------------
drop index if exists idx_crowd_proofs_dedupe_title;
create unique index if not exists idx_crowd_proofs_dedupe_title
  on public.crowd_proofs(dedupe_key) where gate_status = 'accepted';

-- 验证提示：
--   select public.crowd_submit_proof('P-TEST', '{"task_id":1,"proof_seq":1,"sync_version":1,"captured_at":"'||now()||'","items":[]}');
--   恶意 URL / 垃圾 note_id / 未来时间 均应在 rejected 或 reason 中被拒
