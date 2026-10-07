-- crowd_fix_v3412_envelope12.sql
-- 信封榨取率：crowd_fetch_tasks 随任务下发 known_note_ids（该包关键词已收录 note_id ≤500）
-- 客户端据此预过滤 + 信封 6→12（v3.4.12 配套，生产已执行 2026-10-07）
-- 幂等：CREATE OR REPLACE

create or replace function public.crowd_fetch_tasks(p_participant_id text, p_exclude_task_ids bigint[] default '{}'::bigint[])
returns jsonb
language plpgsql
security definer
set search_path to 'public'
as $$
declare
  v_status text;
  v_row record;
  v_tasks jsonb := '[]'::jsonb;
  v_safety jsonb;
begin
  -- 全局暂停开关 + 远程限速配置（随响应下发，插件只紧不松）
  select jsonb_build_object(
           'pause',  coalesce((select (value#>>'{}')::boolean from public.crowd_config where key='global_pause'), false),
           'limits', coalesce((select value from public.crowd_config where key='safety_limits'), '{}'::jsonb)
         ) into v_safety;

  select status into v_status from public.crowd_participants
   where participant_id = p_participant_id;
  if v_status is null or v_status not in ('approved', 'pending') then
    return jsonb_build_object('ok', false, 'reason', 'participant_unavailable', 'safety', v_safety);
  end if;

  update public.crowd_tasks t
     set claimed_by = p_participant_id,
         claimed_at = now(),
         lease_until = now() + make_interval(mins => t.lease_duration_min),
         status = case when status = 'open' then 'in_progress' else status end
   where t.task_id = (
         select t2.task_id from public.crowd_tasks t2
          where t2.status in ('open','in_progress')
            and (t2.claimed_by is null
                 or t2.claimed_by = p_participant_id
                 or t2.lease_until is null
                 or t2.lease_until < now())
            and t2.progress < t2.kpi_min
            and not (t2.task_id = any(p_exclude_task_ids))
          order by t2.created_at asc
          limit 1
          for update skip locked)
  returning * into v_row;

  if v_row.task_id is null then
    return jsonb_build_object('ok', false, 'reason', 'no_open_task', 'safety', v_safety);
  end if;

  -- v3.4.12 信封榨取率提升：随任务下发"已见库"（该包各关键词已收录的 note_id，上限 500），
  -- 客户端预过滤跳过重复，把 12 个信封槽位留给新笔记——同页多榨 2-3 倍，浏览量零增加
  v_tasks := jsonb_build_array(jsonb_build_object(
    'task_id', v_row.task_id,
    'pack_type', v_row.pack_type,
    'pack', v_row.pack,
    'target', v_row.target,
    'kpi_min', v_row.kpi_min,
    'quota_day', v_row.quota_day,
    'progress', v_row.progress,
    'claimed_until', v_row.lease_until,
    'known_note_ids', (
      select coalesce(jsonb_agg(distinct pr.note_id), '[]'::jsonb)
        from (select note_id from public.crowd_proofs
               where gate_status = 'accepted'
                 and raw_query = any(select jsonb_array_elements_text(v_row.pack))
               limit 500) pr
    )
  ));

  return jsonb_build_object('ok', true, 'tasks', v_tasks, 'safety', v_safety);
end;
$$;
