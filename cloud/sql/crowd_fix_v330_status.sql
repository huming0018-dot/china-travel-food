-- crowd_fix_v330_status.sql — 手机端状态页只读聚合 RPC（2026-10-05）
-- 给 PM 状态页用的脱敏汇总：不含联系方式等 PII，仅计数与最近提交摘要。
create or replace function public.crowd_status_summary()
returns jsonb
language plpgsql
security definer
set search_path to 'public'
as $$
declare
  v_tasks jsonb;
  v_flow jsonb;
  v_parts jsonb;
  v_recent jsonb;
begin
  select jsonb_build_object(
           'open', count(*) filter (where status = 'open'),
           'in_progress', count(*) filter (where status = 'in_progress'),
           'fulfilled', count(*) filter (where status = 'fulfilled'),
           'closed', count(*) filter (where status = 'closed'),
           'total', count(*)
         ) into v_tasks
    from public.crowd_tasks;

  select jsonb_build_object(
           'accepted_total', count(*) filter (where gate_status = 'accepted'),
           'accepted_today', count(*) filter (where gate_status = 'accepted'
                                              and created_at >= date_trunc('day', now())),
           'rejected_total', count(*) filter (where gate_status = 'rejected'),
           'duplicate_total', count(*) filter (where gate_status in ('duplicate','duplicate_skipped')),
           'total', count(*)
         ) into v_flow
    from public.crowd_proofs;

  select jsonb_build_object(
           'total', count(*),
           'active_24h', (select count(distinct participant_id) from public.crowd_proofs
                           where created_at >= now() - interval '24 hours')
         ) into v_parts
    from public.crowd_participants;

  -- v3.4.1 修复：同批插入 created_at 相同导致"最新 N 条"乱序，改按自增 id 排序
  select coalesce(jsonb_agg(row_to_json(r) order by r.id desc), '[]'::jsonb) into v_recent
    from (select id, created_at, participant_id, matched_store, gate_status,
                 right(note_id, 6) as note_tail
            from public.crowd_proofs
           order by id desc
           limit 10) r;

  return jsonb_build_object(
    'ok', true,
    'generated_at', now(),
    'tasks', v_tasks,
    'flow', v_flow,
    'participants', v_parts,
    'recent', v_recent
  );
end;
$$;

revoke all on function public.crowd_status_summary() from public;
grant execute on function public.crowd_status_summary() to anon, authenticated;
