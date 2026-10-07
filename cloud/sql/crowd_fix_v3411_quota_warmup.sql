-- crowd_fix_v3411_quota_warmup.sql
-- 方案 A：注册日配额 25±20% 设备抖动（crowd_register_participant 全量替换）
-- 方案 C：风控信号日志 + 近 48h 信号 ≥2 自动降额 30%（crowd_submit_proof 有效配额）
-- 幂等：CREATE OR REPLACE / IF NOT EXISTS；已在生产执行 2026-10-07

create table if not exists public.crowd_risk_log (
  id bigint generated always as identity primary key,
  participant_id text not null,
  signal text not null,
  detail text,
  created_at timestamptz not null default now()
);
create index if not exists idx_risk_log_pid_time on public.crowd_risk_log(participant_id, created_at desc);

create or replace function public.crowd_report_risk(p_participant_id text, p_signal text, p_detail text default '')
returns jsonb language plpgsql security definer set search_path to 'public' as $f$
begin
  if length(coalesce(p_participant_id,'')) = 0 or length(coalesce(p_participant_id,'')) > 20
     or length(coalesce(p_signal,'')) = 0 or length(coalesce(p_signal,'')) > 40
     or length(coalesce(p_detail,'')) > 300 then
    return jsonb_build_object('ok', false, 'reason', 'bad_args');
  end if;
  insert into public.crowd_risk_log (participant_id, signal, detail)
  values (p_participant_id, p_signal, p_detail);
  return jsonb_build_object('ok', true);
end $f$;
revoke all on function public.crowd_report_risk(text, text, text) from public;
grant execute on function public.crowd_report_risk(text, text, text) to anon, authenticated;

create or replace function public.crowd_register_participant(
  p_display_name text default null,
  p_contact      text default null,
  p_device_salt  text default null,
  p_source       text default 'extension'
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id              text;
  v_source          text;
  v_constraint      text;
  v_attempt         int;
  v_existing_id     text;
  v_existing_status text;
  v_display         text;
  v_contact         text;
  v_quota_jitter    int;
begin
  -- device_salt 必填（R1 一机一号辅助风控信号；只是辅助信号，
  -- 不构成设备/账号唯一性证明，主要控制留给身份与审核流程）
  if p_device_salt is null or p_device_salt !~ '^[A-Za-z0-9\-]{8,64}$' then
    return jsonb_build_object('ok', false, 'reason', 'device_salt_invalid');
  end if;

  -- display_name / contact 可选；提供时沿用注入字符与长度校验
  if p_display_name is not null
     and (length(p_display_name) > 20
          or position('<' in p_display_name) > 0
          or position('>' in p_display_name) > 0) then
    return jsonb_build_object('ok', false, 'reason', 'display_name_invalid');
  end if;
  if p_contact is not null
     and (length(p_contact) > 100
          or position('<' in p_contact) > 0
          or position('>' in p_contact) > 0) then
    return jsonb_build_object('ok', false, 'reason', 'contact_invalid');
  end if;

  -- device_salt 幂等恢复（先于编号生成）：同设备已有 active 参与者 → 返还原编号。
  -- 与 idx_crowd_participants_salt_active 部分唯一索引同口径（pending/approved）。
  select participant_id, status
    into v_existing_id, v_existing_status
    from public.crowd_participants
   where device_salt = p_device_salt
     and status in ('pending', 'approved')
   order by applied_at
   limit 1;
  if v_existing_id is not null then
    return jsonb_build_object(
      'ok', true,
      'participant_id', v_existing_id,
      'reused', true,
      'status', v_existing_status
    );
  end if;

  -- source 白名单外一律收敛为服务端默认值（客户端传入的管理语义字段不采纳）
  v_source := case
                when p_source in ('extension', 'public', 'referral', 'crew')
                  then p_source
                else 'extension'
              end;
  v_display := nullif(btrim(coalesce(p_display_name, '')), '');
  v_contact := coalesce(nullif(btrim(coalesce(p_contact, '')), ''), '');

  -- 服务端生成编号：P- + 8 位大写字母数字；主键撞号重试，最多 20 次
  for v_attempt in 1..20 loop
    v_id := 'P-' || (
      select string_agg(
               substr('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                      (floor(random() * 36) + 1)::int, 1), '')
        from generate_series(1, 8)
    );
    begin
      -- v3.4.11 方案 A：日配额 25±20% 设备抖动定型（消灭"全员同一固定值"检测特征）
      v_quota_jitter := 20 + floor(random() * 11)::int;  -- 20~30 均匀
      insert into public.crowd_participants
        (participant_id, display_name, contact, device_salt, source, quota_day)
      values
        (v_id, coalesce(v_display, v_id), v_contact, p_device_salt, v_source, v_quota_jitter);
      return jsonb_build_object(
        'ok', true,
        'participant_id', v_id,
        'reused', false,
        'status', 'pending',
        'quota_day', v_quota_jitter
      );
    exception
      when unique_violation then
        get stacked diagnostics v_constraint = constraint_name;
        -- 并发下同设备抢先注册成功（R1 部分唯一索引）→ 按幂等恢复口径返回已有编号
        if v_constraint = 'idx_crowd_participants_salt_active' then
          select participant_id, status
            into v_existing_id, v_existing_status
            from public.crowd_participants
           where device_salt = p_device_salt
             and status in ('pending', 'approved')
           order by applied_at
           limit 1;
          if v_existing_id is not null then
            return jsonb_build_object(
              'ok', true,
              'participant_id', v_existing_id,
              'reused', true,
              'status', v_existing_status
            );
          end if;
          return jsonb_build_object('ok', false, 'reason', 'device_already_registered');
        end if;
        -- 其余唯一冲突即编号撞号（crowd_participants_pkey）→ 继续重试
    end;
  end loop;
  return jsonb_build_object('ok', false, 'reason', 'id_generation_retry_exhausted');
end;
$$;

CREATE OR REPLACE FUNCTION public.crowd_submit_proof(p_participant_id text, p_envelope jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  v_submission_id   uuid;
  v_legacy_submit   boolean := false;
  v_existing        jsonb;
  v_parse_error     boolean := false;
  v_status          text;
  v_task_id         bigint;
  v_seq             int;
  v_sync            int;
  v_items           jsonb;
  v_captured        timestamptz;
  v_item            jsonb;
  v_idx             int;
  v_item_parse_err  boolean;
  v_kind            text;
  v_platform        text;
  v_note_id         text;
  v_note_url        text;
  v_url_id          text;
  v_title           text;
  v_quality         jsonb;   -- v3.4.2：质量标记（如 no_title），随 accepted 入库待复核
  v_excerpt         text;
  v_author          text;
  v_rating          numeric;
  v_rating_reason   text;
  v_matched         text;
  v_anchor          float;
  v_raw             text;
  v_keyword         text;
  v_kw_ok           boolean;
  v_result          jsonb := '[]'::jsonb;
  v_accepted        int := 0;
  v_rejected        text[] := '{}';
  v_task_status     text;
  v_claimed_by      text;
  v_pack            jsonb;         -- 实测为 jsonb 标准数组；用前以 jsonb_typeof='array' 防御
  v_kpi_min         int;
  v_new_progress    int;
  v_quota           int;
  v_today_used      int;
  v_reject_accum    int;
  v_accept_accum    int;
  v_reject_rate     float;
  v_dup             boolean;
  v_dedupe          text;
  v_kw_progress     jsonb;
  v_kw_obj          jsonb;
  v_incomplete      int;
  v_response        jsonb;
begin
  -- M4（2026-10-06）：全局熔断收口网页通道（插件由 fetch_tasks 下发 safety.pause，网页 RPC 直查）
  if coalesce((select value::boolean from public.crowd_config where key='global_pause'), false) then
    return jsonb_build_object('ok', false, 'reason', 'global_paused');
  end if;
  -- ⓪ submission_id（契约 v3 起新客户端必传，uuid）：
  --    有 → 走 crowd_submissions 幂等回执链路；
  --    无（旧 v3.2.3 插件）→ 服务端生成内部 uuid 占位（legacy 模式），
  --    处理流程一致，幂等兜底改由 proofs 的 unique 四元组承担（见 ⑥）。
  begin
    v_submission_id := nullif(p_envelope->>'submission_id', '')::uuid;
  exception when others then
    v_submission_id := null;
  end;
  if v_submission_id is null then
    v_submission_id := gen_random_uuid();
    v_legacy_submit := true;
  end if;

  -- ⓪b 幂等重放：该 submission_id 已处理过 → 原样返回存储的原始回执，不重算不重计
  --    （legacy 模式服务端现生成 uuid，不会命中本分支；其重试由 ⑥ 的四元组兜底）
  --    v3.4.4：quota_exceeded 是时效性拒绝而非内容裁决——缓存回执会永久毒化该
  --    submission_id（配额重置后重试仍返回旧拒绝，队列卡死）。命中时删除旧回执，
  --    继续走正常裁决链路；任务闸门行锁与 proofs 唯一四元组兜底并发与重复。
  select response into v_existing
    from public.crowd_submissions
   where submission_id = v_submission_id;
  if found then
    -- v3.4.4：quota_exceeded 是时效性拒绝而非裁决——配额重置后允许重新裁决
    -- v3.4.5：条目级配额拒收同理（ok:true 但部分条目 item_quota_exceeded 的回执
    --    同样会被客户端带原 submission_id 重试，不删旧回执则这些条目永不入库）
    if coalesce(v_existing->>'reason', '') = 'quota_exceeded'
       or exists (select 1
                    from jsonb_array_elements_text(
                           coalesce(v_existing->'rejected', '[]'::jsonb)) r
                   where r like 'item_quota_exceeded:%') then
      delete from public.crowd_submissions where submission_id = v_submission_id;
    else
      return v_existing;
    end if;
  end if;

  -- ⓪c 占位行：并发同一 submission_id 在此串行化（唯一约束等待前者提交/回滚）。
  --     冲突即另一事务已处理 → 回其原始回执。
  begin
    insert into public.crowd_submissions
      (submission_id, participant_id, task_id, sync_version, item_count, accepted_count, response)
    values
      (v_submission_id, p_participant_id, null, null, 0, 0,
       '{"ok":false,"reason":"processing"}'::jsonb);
  exception
    when unique_violation then
      select response into v_existing
        from public.crowd_submissions
       where submission_id = v_submission_id;
      return coalesce(v_existing,
        jsonb_build_object('ok', false, 'reason', 'submission_in_progress'));
  end;

  -- （kw_progress 列实测必然存在、存量恒 {}，形状由本文件固定为 {关键词: accepted}，
  --   不再做列存在性探测——见文件头执行前提）

  -- ① 参与者管控闸门（H3 防枚举语义保留：编号不存在/暂停/拉黑/驳回统一
  --    participant_unavailable）+ R8 行锁串行化同参与者并发回传
  select status into v_status
    from public.crowd_participants
   where participant_id = p_participant_id
   for update;

  -- ② 信封解析（垃圾类型不让整函数 500：统一落 envelope_parse_error 回执）
  begin
    v_task_id  := nullif(p_envelope->>'task_id', '')::bigint;
    v_seq      := nullif(p_envelope->>'proof_seq', '')::int;
    v_sync     := coalesce(nullif(p_envelope->>'sync_version', '')::int, 0);
    v_captured := coalesce(nullif(p_envelope->>'captured_at', '')::timestamptz, now());
    v_items    := coalesce(p_envelope->'items', '[]'::jsonb);
    if jsonb_typeof(v_items) is distinct from 'array' then
      v_items := '[]'::jsonb;
      v_parse_error := true;
    end if;
  exception when others then
    v_parse_error := true;
    v_items := '[]'::jsonb;
  end;

  -- ③ 信封级裁决链（任何分支只赋值 v_response，尾部统一持久化回执）
  if v_status is null or v_status in ('suspended', 'blacklisted', 'rejected') then
    v_response := jsonb_build_object('ok', false, 'reason', 'participant_unavailable',
                                     'submission_id', v_submission_id);
  elsif v_parse_error then
    v_response := jsonb_build_object('ok', false, 'reason', 'envelope_parse_error',
                                     'submission_id', v_submission_id);
  elsif v_sync < 2 then
    -- reconcile 口径：sync_version >= 2 即接受（线上 v3.2.3 插件仍为 2）；<2 拒 stale_client
    v_response := jsonb_build_object('ok', false, 'reason', 'stale_client',
                                     'expected_min', 2, 'got', v_sync,
                                     'submission_id', v_submission_id);
  elsif v_task_id is null or v_seq is null then
    v_response := jsonb_build_object('ok', false, 'reason', 'envelope_missing_task_or_seq',
                                     'submission_id', v_submission_id);
  elsif coalesce(p_envelope->>'participant_id', '') <> p_participant_id then
    -- 防跨参与者污染他人记录（外层编号=信封编号是格式校验，不是身份认证；
    -- 真正的身份绑定属下一阶段，见文件尾路线图）
    v_response := jsonb_build_object('ok', false, 'reason', 'participant_id_mismatch',
                                     'submission_id', v_submission_id);
  elsif v_captured > now() + interval '10 minutes' then
    v_response := jsonb_build_object('ok', false, 'reason', 'captured_at_future',
                                     'captured_at', v_captured, 'server_now', now(),
                                     'submission_id', v_submission_id);
  elsif v_captured < now() - interval '7 days' then
    v_response := jsonb_build_object('ok', false, 'reason', 'captured_at_too_old',
                                     'submission_id', v_submission_id);
  else
    -- ④ 任务闸门（入口）：行锁任务行，串行化同任务并发提交的进度判定与认领竞争。
    --    口径与逐条循环内完全一致：open 或 (in_progress 且 claimed_by = 本人)
    select status, pack, kpi_min, claimed_by
      into v_task_status, v_pack, v_kpi_min, v_claimed_by
      from public.crowd_tasks
     where task_id = v_task_id
     for update;
    if v_task_status is null
       or not (v_task_status = 'open'
               or (v_task_status = 'in_progress' and v_claimed_by = p_participant_id)) then
      v_response := jsonb_build_object('ok', false, 'reason', 'task_not_open',
                                       'submission_id', v_submission_id);
    else
      -- ⑤ 日配额批前快速失败
      select quota_day into v_quota
        from public.crowd_participants
       where participant_id = p_participant_id;
      -- v3.4.11 方案 C：近 48h 风控信号 ≥2 → 有效配额自动降 30%（调研 #8 连续 2 天信号降额兜底；
      -- 信号消失 48h 后自然恢复全额，无需人工干预）
      if (select count(*) from public.crowd_risk_log
          where participant_id = p_participant_id
            and created_at > now() - interval '48 hours') >= 2 then
        v_quota := greatest(1, floor(v_quota * 0.7)::int);
      end if;
      select count(*) into v_today_used
        from public.crowd_proofs
       where participant_id = p_participant_id
         and gate_status = 'accepted'
         and created_at >= date_trunc('day', now());
      if coalesce(v_quota, 0) > 0 and v_today_used >= v_quota then
        -- v3.4.4：附 reset_at（配额日界=数据库时区 UTC 的下一零点），客户端据此精确排队
        v_response := jsonb_build_object('ok', false, 'reason', 'quota_exceeded',
                                         'quota_day', v_quota, 'used_today', v_today_used,
                                         'reset_at', date_trunc('day', now()) + interval '1 day',
                                         'submission_id', v_submission_id);
      else
        -- ⑥ 逐条校验 + 裁决落库
        for v_item, v_idx in
          select e.value, (e.ord - 1)::int
            from jsonb_array_elements(v_items) with ordinality as e(value, ord)
        loop
          -- 任务闸门（循环内，与入口同口径；v3.2 根因即此处漏改 claimed_by 分支）：
          --   任务中途关闭/被他人认领（本批前面条目使其 fulfilled）→ 后续条目记 task
          --   类拒收，不计参与者拒收率（任务失效不是参与者作弊）
          select status, claimed_by
            into v_task_status, v_claimed_by
            from public.crowd_tasks
           where task_id = v_task_id;
          if not (v_task_status = 'open'
                  or (v_task_status = 'in_progress' and v_claimed_by = p_participant_id)) then
            v_rejected := v_rejected || format('item_task_fulfilled:%s', coalesce(v_item->>'note_id', '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_item->>'note_id',
               'rejected', 'item_task_fulfilled', 'task', false);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_item->>'note_id', ''),
                                                       'gate', 'rejected', 'reason', 'item_task_fulfilled');
            continue;
          end if;

          -- 条目解析（单条垃圾数字不炸整批）
          v_item_parse_err := false;
          begin
            v_kind          := v_item->>'kind';
            v_platform      := lower(coalesce(nullif(v_item->>'platform', ''), 'xiaohongshu'));
            v_note_id       := nullif(v_item->>'note_id', '');
            v_note_url      := nullif(v_item->>'note_url', '');
            v_title         := left(coalesce(v_item->>'title', ''), 100);
            v_excerpt       := left(coalesce(v_item->>'excerpt', ''), 200);
            v_author        := left(coalesce(v_item->>'author', ''), 50);
            v_rating        := nullif(v_item->>'rating', '')::numeric;
            v_rating_reason := left(coalesce(v_item->>'rating_reason', ''), 200);
            v_matched       := left(coalesce(v_item->>'matched_store', ''), 100);
            v_anchor        := nullif(v_item->>'anchor_score', '')::float;
            v_keyword       := nullif(v_item->>'raw_query', '');   -- 参与 pack 匹配用全文，不截断
            v_raw           := left(coalesce(v_item->>'raw_query', ''), 50);
            v_quality       := '{}'::jsonb;  -- 每条重置质量标记
          exception when others then
            v_item_parse_err := true;
          end;
          if v_item_parse_err then
            v_rejected := v_rejected || format('item_parse_error:%s', coalesce(v_item->>'note_id', '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_item->>'note_id',
               'rejected', 'item_parse_error', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_item->>'note_id', ''),
                                                       'gate', 'rejected', 'reason', 'item_parse_error');
            continue;
          end if;

          -- kind 枚举
          if v_kind not in ('note', 'rating') then
            v_rejected := v_rejected || format('item_kind_invalid:%s', coalesce(v_note_id, '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_kind_invalid', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_note_id, ''),
                                                       'gate', 'rejected', 'reason', 'item_kind_invalid');
            continue;
          end if;

          -- note_id / note_url 必填
          if v_note_id is null or v_note_url is null then
            v_rejected := v_rejected || format('item_missing_note:%s', coalesce(v_note_id, '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_missing_note', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_note_id, ''),
                                                       'gate', 'rejected', 'reason', 'item_missing_note');
            continue;
          end if;

          -- 平台白名单（当前仅小红书；新增平台时需同步扩展 URL 规则与去重口径）
          if v_platform <> 'xiaohongshu' then
            v_rejected := v_rejected || format('item_platform_unsupported:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_platform_unsupported', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_platform_unsupported');
            continue;
          end if;

          -- R2 URL 严格正则：host 精确 www.xiaohongshu.com，路径 /explore/<24hex> 或 /discovery/item/<24hex>
          if v_note_url !~ '^https://www\.xiaohongshu\.com/explore/[0-9a-f]{24}(\?.*)?$'
             and v_note_url !~ '^https://www\.xiaohongshu\.com/discovery/item/[0-9a-f]{24}(\?.*)?$' then
            v_rejected := v_rejected || format('item_url_invalid:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_url_invalid', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_url_invalid');
            continue;
          end if;

          -- R3 note_id 必须 24 位十六进制
          if v_note_id !~ '^[0-9a-f]{24}$' then
            v_rejected := v_rejected || format('item_note_id_invalid:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_note_id_invalid', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_note_id_invalid');
            continue;
          end if;

          -- URL 内嵌 ID 必须等于 note_id（纯静态校验，不访问外网）：
          --   只分别检查 URL 形状和 note_id 形状会让"真 URL + 假 ID"蒙混入库
          v_url_id := (regexp_match(v_note_url, '(?:explore|discovery/item)/([0-9a-f]{24})'))[1];
          if v_url_id is null or v_url_id <> v_note_id then
            v_rejected := v_rejected || format('item_url_note_id_mismatch:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_url_note_id_mismatch', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_url_note_id_mismatch');
            continue;
          end if;

          -- raw_query 必须等于任务包 pack 中某一项（pack 实测为 jsonb 标准数组）。
          --   防御：jsonb_typeof='array' 才当数组处理；历史脏行（非数组/null）无法判定
          --   关键词归属 → 拒收原因 pack_mismatch（task 类，任务数据问题，不计参与者拒收率）；
          --   数组内无此成员 → item_keyword_not_in_pack（质量类，计入拒收率）——
          --   服务端只认词包成员，客户端标错关键词的条目直接拒收
          if jsonb_typeof(v_pack) is distinct from 'array' then
            v_rejected := v_rejected || format('pack_mismatch:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'pack_mismatch', 'task', false);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'pack_mismatch');
            continue;
          end if;
          v_kw_ok := v_keyword is not null and (v_pack ? v_keyword);
          if v_kw_ok is not true then
            v_rejected := v_rejected || format('item_keyword_not_in_pack:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_keyword_not_in_pack', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_keyword_not_in_pack');
            continue;
          end if;

          -- R3 标题实质内容（v3.4.2 软化：手机人工提交通道常缺标题——身份由
          --   note_id+URL 一致性保证，空标题只记质量标记 no_title 待复核，不拒收不计拒收率；
          --   标题与正文皆空 = 内容全空，仍拒收（item_content_empty，防垃圾灌库，计拒收率））
          if coalesce(length(regexp_replace(v_title, '[\s[:punct:]]', '', 'g')), 0) < 2 then
            if coalesce(length(regexp_replace(v_excerpt, '[\s[:punct:]]', '', 'g')), 0) < 10 then
              v_rejected := v_rejected || format('item_content_empty:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_content_empty', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_content_empty');
              continue;
            end if;
            v_quality := '["no_title"]'::jsonb;
          end if;

          -- R6 rating 类：分值范围 / 理由质量 / 锚定同 platform+note_id 已收录笔记
          if v_kind = 'rating' then
            if v_rating is null or v_rating < 1 or v_rating > 5 then
              v_rejected := v_rejected || format('item_rating_out_of_range:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_rating_out_of_range', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_rating_out_of_range');
              continue;
            end if;
            if coalesce(length(regexp_replace(v_rating_reason, '[\s[:punct:]]', '', 'g')), 0) < 8 then
              v_rejected := v_rejected || format('item_rating_reason_too_short:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_rating_reason_too_short', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_rating_reason_too_short');
              continue;
            end if;
            select exists (
              select 1 from public.crowd_proofs
               where gate_status = 'accepted'
                 and kind = 'note'
                 and platform = v_platform
                 and note_id = v_note_id
            ) into v_kw_ok;
            if v_kw_ok is not true then
              v_rejected := v_rejected || format('item_rating_no_anchor:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_rating_no_anchor', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_rating_no_anchor');
              continue;
            end if;
          end if;

          -- 逐条配额限流（行锁保证计数一致）：超限属限流而非造假证据，不计拒收率
          if coalesce(v_quota, 0) > 0 and (v_today_used + v_accepted) >= v_quota then
            v_rejected := v_rejected || format('item_quota_exceeded:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_quota_exceeded', 'quota', false);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_quota_exceeded');
            continue;
          end if;

          -- 去重口径 platform+note_id：note 全局唯一；
          --   rating 每参与者每笔记唯一（跨参与者可并存）
          if v_kind = 'rating' then
            v_dedupe := v_platform || ':' || v_note_id || ':rating:' || p_participant_id;
          else
            v_dedupe := v_platform || ':' || v_note_id;
          end if;
          select exists (
            select 1 from public.crowd_proofs
             where gate_status = 'accepted' and dedupe_key = v_dedupe
          ) into v_dup;
          if v_dup then
            -- 重复不计拒收率（可能源于调度冲突/重试，与造假分开）
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'duplicate', 'duplicate_note', 'duplicate', false);
            v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate');
            continue;
          end if;

          -- 落库：accepted 进 crowd_proofs。
          --   · unique(participant_id, task_id, proof_seq, note_id) 四元组冲突
          --     → on conflict do nothing，判 duplicate_skipped（legacy 无 submission_id
          --     重试的兜底幂等，与回执链路互不冲突）；
          --   · dedupe 部分唯一索引并发冲突 → unique_violation 捕获，判 duplicate_skipped
          --     （线上 v3.2 既有口径保留）；
          --   · 其他异常记 error（system，不计拒收率、不进 proofs）
          begin
            insert into public.crowd_proofs
              (participant_id, task_id, proof_seq, captured_at, sync_version,
               kind, platform, note_id, note_url, title, excerpt, author,
               rating, rating_reason, matched_store, anchor_score, raw_query, client_ip_salt,
               gate_status, gate_reason, dedupe_key, submission_id, quality_flags)
            values
              (p_participant_id, v_task_id, v_seq, v_captured, v_sync,
               v_kind, v_platform, v_note_id, v_note_url, v_title, v_excerpt, v_author,
               v_rating, v_rating_reason, v_matched, v_anchor, v_raw, v_item->>'client_ip_salt',
               'accepted', null, v_dedupe, v_submission_id, v_quality)
            on conflict (participant_id, task_id, proof_seq, note_id) do nothing;
            if found then
              v_accepted := v_accepted + 1;
              -- 关键词进度累计（crowd_task_keyword_progress 表始终维护；
              --   on conflict 行锁保证并发安全，原子增量）
              insert into public.crowd_task_keyword_progress (task_id, keyword, accepted, updated_at)
              values (v_task_id, v_keyword, 1, now())
              on conflict (task_id, keyword) do update
                set accepted = crowd_task_keyword_progress.accepted + 1,
                    updated_at = now();
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'accepted', null, 'none', false);
              v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'accepted');
            else
              -- 四元组冲突：legacy 重试/断网重传的兜底幂等（duplicate_skipped，不计拒收率）
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'duplicate', 'duplicate_seq_replay', 'duplicate', false);
              v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
            end if;
          exception
            when unique_violation then
              -- dedupe 唯一索引并发冲突（线上 v3.2 口径：捕获为 duplicate_skipped）
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'duplicate', 'duplicate_note', 'duplicate', false);
              v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
            when others then
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject, detail)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'error', 'item_insert_error', 'system', false, SQLERRM);
              v_result := v_result || jsonb_build_object('note_id', coalesce(v_note_id, ''),
                                                         'gate', 'error', 'reason', 'item_insert_error');
          end;
        end loop;

        -- ⑦ 回写任务总进度 / 认领（含租约）/ kw_progress 双写 / 参与者累计
        --    （只在有新增 accepted 时）
        if v_accepted > 0 then
          -- v3.2 并发安全口径：SELECT ... FOR UPDATE 锁任务行重读
          -- （行锁自入口任务闸门持有，此处重读最新 status/pack/kpi_min/progress）
          select status, pack, kpi_min, progress
            into v_task_status, v_pack, v_kpi_min, v_new_progress
            from public.crowd_tasks
           where task_id = v_task_id
           for update;

          -- progress 原子增量 + open 任务首个 accepted 提交认领（行锁保证只有一个
          --   事务完成认领）：置 in_progress / claimed_by=本人 / claimed_at=now() /
          --   lease_until=now()+lease_duration_min 分钟（实测默认 1440）。
          --   租约过期回收（到期自动回 open）属下一阶段，本文件不实现。
          update public.crowd_tasks
             set progress     = progress + v_accepted,
                 status       = case when status = 'open' then 'in_progress' else status end,
                 claimed_by   = case when status = 'open' then p_participant_id else claimed_by end,
                 claimed_at   = case when status = 'open' then now() else claimed_at end,
                 lease_until  = case when status = 'open'
                                     then now() + make_interval(mins => coalesce(lease_duration_min, 1440))
                                     else lease_until end,
                 updated_at   = now()
           where task_id = v_task_id;

          -- kw_progress 双写之一：tasks.kw_progress jsonb（列实测必然存在；
          --   固定形状 {关键词: accepted}，覆盖 pack 全部关键词含 0 进度。
          --   pack 为 jsonb 标准数组；jsonb_typeof 防御历史脏行（非数组按空包处理）
          select coalesce(jsonb_object_agg(kw, coalesce(p.accepted, 0)), '{}'::jsonb)
            into v_kw_obj
            from (select kw
                    from jsonb_array_elements_text(
                           case when jsonb_typeof(v_pack) = 'array'
                                then v_pack else '[]'::jsonb end) kw) kws
            left join public.crowd_task_keyword_progress p
              on p.task_id = v_task_id and p.keyword = kws.kw;
          update public.crowd_tasks
             set kw_progress = v_kw_obj,
                 updated_at   = now()
           where task_id = v_task_id;

          update public.crowd_participants
             set total_effective = total_effective + v_accepted,
                 last_active_at = now()
           where participant_id = p_participant_id;

          -- 完成标准统一：包内每个关键词 accepted >= kpi_min 才 fulfilled
          --   （旧逻辑整包累计达标即关单，与客户端"每词达标"不一致）
          select count(*)
            into v_incomplete
            from (select kw
                    from jsonb_array_elements_text(
                           case when jsonb_typeof(v_pack) = 'array'
                                then v_pack else '[]'::jsonb end) kw) kws
            left join public.crowd_task_keyword_progress p
              on p.task_id = v_task_id and p.keyword = kws.kw
           where coalesce(p.accepted, 0) < v_kpi_min;
          if v_incomplete = 0 then
            update public.crowd_tasks
               set status = 'fulfilled',
                   updated_at = now()
             where task_id = v_task_id
               and status in ('open', 'in_progress');
          end if;
        end if;

        -- ⑧ 拒收率风控：从 crowd_proof_verdicts 事实表计算；
        --    仅 quality 类计入分子分母，duplicate/task/quota/system 一律不算参与者责任
        select coalesce(sum(case when verdict = 'accepted' then 1 else 0 end), 0),
               coalesce(sum(case when counts_for_reject then 1 else 0 end), 0)
          into v_accept_accum, v_reject_accum
          from public.crowd_proof_verdicts
         where participant_id = p_participant_id;
        if (v_accept_accum + v_reject_accum) > 20 then
          v_reject_rate := v_reject_accum::float / (v_accept_accum + v_reject_accum);
          if v_reject_rate > 0.6 then
            update public.crowd_participants
               set status = 'suspended',
                   review_note = 'auto_suspend: reject_rate ' || round(v_reject_rate::numeric, 2)
             where participant_id = p_participant_id;
          else
            update public.crowd_participants
               set reject_rate = v_reject_rate
             where participant_id = p_participant_id;
          end if;
        end if;

        select progress into v_new_progress
          from public.crowd_tasks
         where task_id = v_task_id;

        -- keyword_progress：客户端据此同步每词进度（覆盖 pack 全部关键词含 0 进度；
        --   pack 为 jsonb 标准数组；jsonb_typeof 防御历史脏行，非数组返回空数组）
        select coalesce(
                 jsonb_agg(
                   jsonb_build_object('keyword', kws.kw, 'accepted', coalesce(p.accepted, 0))
                   order by kws.kw),
                 '[]'::jsonb)
          into v_kw_progress
          from (select kw
                  from jsonb_array_elements_text(
                         case when jsonb_typeof(v_pack) = 'array'
                              then v_pack else '[]'::jsonb end) kw) kws
          left join public.crowd_task_keyword_progress p
            on p.task_id = v_task_id and p.keyword = kws.kw;

        v_response := jsonb_build_object(
          'ok', true,
          'submission_id', v_submission_id,
          'accepted', v_accepted,
          'rejected', v_rejected,
          'results', v_result,
          'new_progress', coalesce(v_new_progress, 0),
          'keyword_progress', v_kw_progress
        );
      end if;
    end if;
  end if;

  -- ⑨ 回执统一持久化（成功与业务失败都落库，供幂等重放与申诉核查；
  --    legacy 模式同样落库，response 内 submission_id 可供申诉定位；
  --    未捕获的系统异常会让整个事务回滚，占位行一并消失，重试重新执行——
  --    系统故障不产生假回执）
  update public.crowd_submissions
     set participant_id = p_participant_id,
         task_id        = v_task_id,
         sync_version   = v_sync,
         item_count     = jsonb_array_length(v_items),
         accepted_count = v_accepted,
         response       = v_response
   where submission_id = v_submission_id;

  return v_response;
end;
$function$

