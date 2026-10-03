-- ============================================================
-- CROWD MIGRATION v3.2 · 03 任务租约与名额预留（外部审计 #14）
-- 目标：多人并发领取时任务名额与预算不超发——
--   领取即原子占用（lease），提交校验认领归属；任务剩余名额明确。
-- 幂等：可重复执行。
-- ============================================================

-- ------------------------------------------------------------
-- 1) crowd_tasks 增加租约字段
-- ------------------------------------------------------------
alter table public.crowd_tasks add column if not exists claimed_by text;
alter table public.crowd_tasks add column if not exists claimed_at timestamptz;
alter table public.crowd_tasks add column if not exists lease_until timestamptz;
-- 租约有效期（默认 24h；到期未完成释放给他人）
alter table public.crowd_tasks add column if not exists lease_duration_min int not null default 1440;

-- ------------------------------------------------------------
-- 2) 领取 RPC：原子领取（防两个参与者同时通过 open 检查）
--    领取条件：status='open' 且（无人认领 或 租约过期）且未达 KPI
--    领取动作：认领人 + 租约时间 → 名额预留
-- ------------------------------------------------------------
create or replace function public.crowd_fetch_tasks(
  p_participant_id text,
  p_exclude_task_ids bigint[] default '{}'
) returns jsonb
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
declare
  v_status text;
  v_row record;
  v_tasks jsonb := '[]'::jsonb;
  v_lease_min int;
begin
  select status into v_status from public.crowd_participants
   where participant_id = p_participant_id;
  if v_status is null or v_status not in ('approved', 'pending') then
    return jsonb_build_object('ok', false, 'reason', 'participant_unavailable');
  end if;

  -- 原子领取：一条 SQL 完成"条件检查 + 认领"，行锁保证并发安全
  -- （未领取/租约过期 → 本人认领；本人已认领 → 续领进度）
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
    return jsonb_build_object('ok', false, 'reason', 'no_open_task');
  end if;

  v_tasks := jsonb_build_array(jsonb_build_object(
    'task_id', v_row.task_id,
    'pack_type', v_row.pack_type,
    'pack', v_row.pack,
    'target', v_row.target,
    'kpi_min', v_row.kpi_min,
    'quota_day', v_row.quota_day,
    'progress', v_row.progress,
    'claimed_until', v_row.lease_until
  ));

  return jsonb_build_object('ok', true, 'tasks', v_tasks);
end;
$function$;

-- 权限：security definer 自动以 owner 执行；确认 anon 可调用（RPC 自身做身份校验）
revoke all on function public.crowd_fetch_tasks(text, bigint[]) from public;
grant execute on function public.crowd_fetch_tasks(text, bigint[]) to anon, authenticated;

-- ------------------------------------------------------------
-- 3) 提交侧校验已含在迁移01函数中（claimed_by 归属 + 任务 open）
--    此处补充：任务进入 in_progress 后非认领人提交直接拒绝（已实现于迁移01第14项校验）
-- ------------------------------------------------------------

-- ============================================================
-- 验证：
--  1) 两个参与者并发领最后一个名额：UPDATE ... WHERE ... LIMIT 1 FOR UPDATE SKIP LOCKED
--     保证只有一人领到（另一人 no_open_task）
--  2) 认领人租约内提交通过；非认领人提交 → task_claimed_by_other
--  3) 租约过期后任务释放给他人
-- 回滚：
--  drop function public.crowd_fetch_tasks;
--  alter table crowd_tasks drop column claimed_by, drop column claimed_at,
--                          drop column lease_until, drop column lease_duration_min;
-- ============================================================
