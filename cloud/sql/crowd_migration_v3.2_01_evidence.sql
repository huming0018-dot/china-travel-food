-- ============================================================
-- CROWD MIGRATION v3.2 · 01 证据真实性（外部审计 #7/#8/#9/#5）
-- 目标：
--   #7  URL 内 note_id 必须与 note_id 字段一致（防错配/伪造 URL）
--   #8  dedupe 键改为 platform+note_id（改标题不可绕过；同名不同笔记不误杀）
--   #9  拒收逐条落库（gate_status 扩展枚举），拒收率风控真正生效
--   #5  服务端按"每关键词达 kpi_min"判定完成（与插件 v3.2 对齐）
-- 执行前提：先在 SQL Editor 备份（create table crowd_proofs_bak_20261003 as select * from crowd_proofs;）
-- 幂等：可重复执行
-- ============================================================

-- ------------------------------------------------------------
-- 1) gate_status 枚举扩展（允许 duplicate_skipped/task_closed/invalid/error）
-- ------------------------------------------------------------
alter table public.crowd_proofs drop constraint if exists crowd_proofs_gate_status_check;
alter table public.crowd_proofs add constraint crowd_proofs_gate_status_check
  check (gate_status in ('accepted','rejected','duplicate_skipped','task_closed','invalid','error'));

-- ------------------------------------------------------------
-- 2) 去重键重构：note 按 note_id 全局唯一；rating 按 参与者+note_id 唯一
--    （删除旧的标题归一化部分唯一索引——改标题即可绕过，且同名不同笔记被误杀）
-- ------------------------------------------------------------
drop index if exists idx_crowd_proofs_dedupe;
-- note：同一篇笔记全局仅保留一条 accepted 证据（先到先得，计酬只给首个有效提交）
create unique index if not exists uq_crowd_proofs_note_noteid
  on public.crowd_proofs(note_id) where kind = 'note' and gate_status = 'accepted';
-- rating：同一参与者对同一篇笔记最多一条有效评分（跨参与者可并存）
create unique index if not exists uq_crowd_proofs_rating_pid_note
  on public.crowd_proofs(participant_id, note_id) where kind = 'rating' and gate_status = 'accepted';

-- ------------------------------------------------------------
-- 3) crowd_tasks 增加按关键词进度（per-kw KPI，外部审计 #5）
-- ------------------------------------------------------------
alter table public.crowd_tasks add column if not exists kw_progress jsonb not null default '{}'::jsonb;

-- ------------------------------------------------------------
-- 4) 重写提交函数：URL-ID 一致性 + note_id 去重 + 拒收落库 + per-kw 完成判定
-- ------------------------------------------------------------
create or replace function public.crowd_submit_proof(p_participant_id text, p_envelope jsonb)
 returns jsonb
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
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
  v_task_open   boolean;
  v_task_status text;
  v_new_progress int;
  v_row         jsonb;
  v_quota       int;
  v_today_used  int;
  v_reject_accum int;
  v_accept_accum int;
  v_reject_rate float;
  v_note_exists boolean;
  v_dedupe      text;
  v_url_id      text;
  v_pack_type   text;
  v_pack        jsonb;
  v_kpi         int;
  v_kw_index    int;
  v_kw_progress jsonb;
  v_all_kw_done boolean;
  v_pack_len    int;
  v_reason_text text;
  v_reason_deduped text;
  v_verdict     text;
  v_i           int;
begin
  -- #6 前置（迁移02启用后生效）：认证身份绑定校验（auth.uid 必须等于参与者绑定）
  -- 迁移02未启用前 auth.uid() 为 null，此校验自动跳过（向后兼容）
  if (select count(*) from public.crowd_participants
       where participant_id = p_participant_id and auth_user_id is not null) > 0
     and (select auth_user_id from public.crowd_participants
          where participant_id = p_participant_id) is distinct from auth.uid() then
    return jsonb_build_object('ok', false, 'reason', 'auth_identity_mismatch');
  end if;

  select status into v_status
    from public.crowd_participants
   where participant_id = p_participant_id
   for update;
  if v_status is null or v_status in ('suspended', 'blacklisted', 'rejected') then
    return jsonb_build_object('ok', false, 'reason', 'participant_unavailable');
  end if;

  v_task_id := (p_envelope->>'task_id')::bigint;
  v_seq     := (p_envelope->>'proof_seq')::int;
  v_sync    := coalesce((p_envelope->>'sync_version')::int, 1);
  v_captured:= coalesce((p_envelope->>'captured_at')::timestamptz, now());
  v_items   := coalesce(p_envelope->'items', '[]'::jsonb);
  v_kw_index:= coalesce((p_envelope->>'kw_index')::int, -1);

  if v_sync <> 1 then
    return jsonb_build_object('ok', false, 'reason', 'sync_version_mismatch',
                              'expected', 1, 'got', v_sync);
  end if;
  if v_task_id is null or v_seq is null then
    return jsonb_build_object('ok', false, 'reason', 'envelope_missing_task_or_seq');
  end if;

  if coalesce(p_envelope->>'participant_id','') <> p_participant_id then
    return jsonb_build_object('ok', false, 'reason', 'participant_id_mismatch');
  end if;

  if v_captured > now() + interval '10 minutes' then
    return jsonb_build_object('ok', false, 'reason', 'captured_at_future',
                              'captured_at', v_captured, 'server_now', now());
  end if;
  if v_captured < now() - interval '7 days' then
    return jsonb_build_object('ok', false, 'reason', 'captured_at_too_old');
  end if;

  -- #14 租约校验（迁移03启用后生效）：任务须由本人认领或仍开放
  select status, pack_type, kpi_min, pack, coalesce(kw_progress,'{}'::jsonb)
    into v_task_status, v_pack_type, v_kpi, v_pack, v_kw_progress
    from public.crowd_tasks where task_id = v_task_id;
  if v_task_status is null then
    return jsonb_build_object('ok', false, 'reason', 'task_not_found');
  end if;
  v_task_open := (v_task_status = 'open');
  if not v_task_open and v_task_status <> 'in_progress' then
    return jsonb_build_object('ok', false, 'reason', 'task_not_open');
  end if;
  if (select claimed_by from public.crowd_tasks where task_id = v_task_id)
     is not null
     and (select claimed_by from public.crowd_tasks where task_id = v_task_id) <> p_participant_id then
    return jsonb_build_object('ok', false, 'reason', 'task_claimed_by_other');
  end if;
  v_pack_len := jsonb_array_length(v_pack);

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

  for v_item in select * from jsonb_array_elements(v_items) loop
    v_verdict := null;
    -- 任务状态复查（循环内）
    select (status = 'open') into v_task_open
      from public.crowd_tasks where task_id = v_task_id;
    if v_task_open is distinct from true then
      v_verdict := 'task_closed';
    else
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

      if v_kind not in ('note','rating') then
        v_verdict := 'invalid';
      elsif v_note_id is null or v_note_url is null then
        v_verdict := 'invalid';
      elsif v_note_url !~ '^https://www\.xiaohongshu\.com/explore/[0-9a-f]{24}(\?.*)?$'
        and v_note_url !~ '^https://www\.xiaohongshu\.com/discovery/item/[0-9a-f]{24}(\?.*)?$' then
        v_verdict := 'invalid';
      elsif v_note_id !~ '^[0-9a-f]{24}$' then
        v_verdict := 'invalid';
      else
        -- #7 修复：URL 内提取的 note_id 必须等于字段 note_id（防错配/伪造）
        v_url_id := coalesce(
          (regexp_match(v_note_url, '/explore/([0-9a-f]{24})'))[1],
          (regexp_match(v_note_url, '/discovery/item/([0-9a-f]{24})'))[1]
        );
        if v_url_id is null or v_url_id <> v_note_id then
          v_verdict := 'invalid';
        elsif coalesce(length(regexp_replace(v_title, '[\s[:punct:]]', '', 'g')), 0) < 2 then
          v_verdict := 'invalid';
        elsif v_kind = 'rating' then
          if v_rating is null or v_rating < 1 or v_rating > 5 then
            v_verdict := 'invalid';
          else
            -- #7 修复：理由必须≥8个去重字符且非纯重复汉字（如"好好好好好好好好"）
            v_reason_text := coalesce(v_rating_reason,'');
            v_reason_deduped := regexp_replace(v_reason_text, '[\s[:punct:]]', '', 'g');
            if coalesce(length(v_reason_deduped),0) < 8 then
              v_verdict := 'invalid';
            elsif length(v_reason_deduped) > 0 and length(regexp_replace(v_reason_deduped, (substring(v_reason_deduped,1,1))::text, '', 'g')) = 0 then
              v_verdict := 'invalid';  -- 全部同一字符
            end if;
          end if;
          if v_verdict is null then
            select exists (
              select 1 from public.crowd_proofs
               where note_id = v_note_id and gate_status = 'accepted' and kind = 'note'
            ) into v_note_exists;
            if v_note_exists is not true then
              v_verdict := 'invalid';  -- rating 必须锚定已收录笔记
            else
              v_dedupe := md5('r:' || p_participant_id || ':' || v_note_id);
            end if;
          end if;
        else
          -- #8 修复：note 去重键 = platform+note_id（改标题不可绕过）
          v_dedupe := md5('xhs:' || v_note_id);
        end if;
      end if;
    end if;

    -- 配额检查（仅对将 accepted 的条目）
    if v_verdict is null and coalesce(v_quota, 0) > 0 and (v_today_used + v_accepted) >= v_quota then
      v_verdict := 'invalid';
    end if;

    -- 逐条落库（#9 修复：拒收也写库，风控统计真实；verdict 写入 gate_status）
    if v_verdict is not null then
      begin
        insert into public.crowd_proofs
          (participant_id, task_id, proof_seq, captured_at, sync_version,
           kind, note_id, note_url, title, excerpt, author,
           rating, rating_reason, matched_store, anchor_score, raw_query,
           gate_status, dedupe_key)
        values
          (p_participant_id, v_task_id, v_seq, v_captured, v_sync,
           coalesce(v_kind,'note'), coalesce(v_note_id,''), coalesce(v_note_url,''),
           v_title, v_excerpt, v_author,
           v_rating, v_rating_reason, v_matched, v_anchor, v_raw,
           v_verdict, null)
        on conflict (participant_id, task_id, proof_seq, note_id) do nothing;
      exception when others then null; -- 拒收记录尽力而为，不阻断主流程
      end;
      v_row := jsonb_build_object('note_id', coalesce(v_note_id,'?'), 'gate', v_verdict);
    else
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
           'accepted', v_dedupe)
        on conflict (participant_id, task_id, proof_seq, note_id) do nothing;
        if found then
          v_accepted := v_accepted + 1;
          v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'accepted');
        else
          v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
        end if;
      exception
        when unique_violation then
          v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
        when others then
          v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'error', 'msg', SQLERRM);
      end;
    end if;
    v_result := v_result || v_row;
  end loop;

  -- 进度更新（#5 修复：keyword 包按每词 KPI；store 包按包累计）
  if v_accepted > 0 then
    if v_pack_type = 'keyword' and v_kw_index >= 0 and v_kw_index < v_pack_len then
      v_kw_progress := jsonb_set(coalesce(v_kw_progress,'{}'::jsonb), array[v_kw_index::text],
        to_jsonb(coalesce((v_kw_progress->>(v_kw_index::text))::int, 0) + v_accepted));
      -- 所有关键词均达 kpi_min → fulfilled
      v_all_kw_done := true;
      for i in 0..(v_pack_len-1) loop
        if coalesce((v_kw_progress->>(i::text))::int, 0) < v_kpi then
          v_all_kw_done := false;
          exit;
        end if;
      end loop;
      update public.crowd_tasks
         set kw_progress = v_kw_progress,
             progress = progress + v_accepted,
             status = case when v_all_kw_done then 'fulfilled' else status end,
             updated_at = now()
       where task_id = v_task_id;
    else
      update public.crowd_tasks
         set progress = progress + v_accepted,
             status = case when progress + v_accepted >= kpi_min then 'fulfilled' else status end,
             updated_at = now()
       where task_id = v_task_id;
    end if;
    update public.crowd_participants
       set total_effective = total_effective + v_accepted,
           last_active_at = now()
     where participant_id = p_participant_id;
  end if;

  -- 拒收率风控（#9 修复：拒收已落库，此统计真实生效）
  select coalesce(sum(case when gate_status='accepted' then 1 else 0 end),0),
         coalesce(sum(case when gate_status in ('rejected','invalid') then 1 else 0 end),0)
    into v_accept_accum, v_reject_accum
    from public.crowd_proofs
   where participant_id = p_participant_id;
  if (v_accept_accum + v_reject_accum) > 20 then
    v_reject_rate := v_reject_accum::float / (v_accept_accum + v_reject_accum);
    if v_reject_rate > 0.6 then
      update public.crowd_participants
         set status = 'suspended', review_note = 'auto_suspend: reject_rate ' || round(v_reject_rate::numeric,2)
       where participant_id = p_participant_id;
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
    'results', v_result,
    'new_progress', coalesce(v_new_progress, 0)
  );
end;
$function$;

-- ============================================================
-- 验证：
--  1) 提交 note_id 与 URL 不一致 → results 含 gate=invalid，且库内落 invalid 行
--  2) 同 note_id 改标题再提交 → 第二条 duplicate_skipped（dedupe 基于 note_id）
--  3) 拒收率统计：select participant_id, gate_status, count(*) from crowd_proofs group by 1,2;
--  4) 任务完成：keyword 包每词达 kpi 才 fulfilled
-- 回滚：drop index uq_crowd_proofs_note_noteid; drop index uq_crowd_proofs_rating_pid_note;
--       alter table crowd_proofs drop constraint crowd_proofs_gate_status_check;
--       -- 恢复函数：用 crowd_submit_proof_live_v2.sql 原版重放
-- ============================================================
