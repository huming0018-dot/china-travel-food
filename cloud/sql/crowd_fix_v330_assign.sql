-- crowd_fix_v330_assign.sql — 中枢分配（2026-10-04）
-- 原则：任务与采集目标由中枢分配，参与者不选择门店——参与者只提供账号、IP 与采集能力。
-- 新增：
--   · crowd_kw_assignments 表（参与者当前采集目标指针，含租约）
--   · crowd_next_target(p_participant_id, p_exclude) RPC：原子认领任务 + 分配第一个未达标关键词
-- 依赖：crowd_fix_v323_reconcile.sql 已执行（crowd_task_keyword_progress 存在）。
-- 幂等：可重复执行。

create table if not exists public.crowd_kw_assignments (
  participant_id text primary key references public.crowd_participants(participant_id) on delete cascade,
  task_id        bigint not null references public.crowd_tasks(task_id) on delete cascade,
  kw_index       int not null,           -- 0 基，与插件 pack[idx] 口径一致
  keyword        text not null,
  assigned_at    timestamptz not null default now(),
  lease_until    timestamptz not null
);
alter table public.crowd_kw_assignments enable row level security;
revoke all on public.crowd_kw_assignments from anon, authenticated;  -- 只经 RPC 访问

create or replace function public.crowd_next_target(p_participant_id text, p_exclude text[] default '{}'::text[])
returns jsonb
language plpgsql
security definer
set search_path to 'public'
as $$
declare
  v_status text;
  v_asg    record;
  v_task   record;
  v_kws    text[];
  v_acc    int;
  v_i      int;
  v_lease_min int;
begin
  -- 参与者闸门（与 crowd_fetch_tasks 同口径）
  select status into v_status from public.crowd_participants
   where participant_id = p_participant_id;
  if v_status is null or v_status not in ('approved','pending') then
    return jsonb_build_object('ok', false, 'reason', 'participant_unavailable');
  end if;

  -- ① 现有分配仍有效（租约未过期 + 任务可提交 + 该词未达标 + 未被参与者跳过）→ 直接复用
  select a.task_id, a.kw_index, a.keyword, a.lease_until,
         t.status as t_status, t.kpi_min
    into v_asg
    from public.crowd_kw_assignments a
    join public.crowd_tasks t on t.task_id = a.task_id
   where a.participant_id = p_participant_id
     and a.lease_until > now()
     and not (a.keyword = any(p_exclude));
  if v_asg is not null and v_asg.t_status in ('open','in_progress') then
    select kp.accepted into v_acc
      from public.crowd_task_keyword_progress kp
     where kp.task_id = v_asg.task_id and kp.keyword = v_asg.keyword;
    if coalesce(v_acc, 0) < v_asg.kpi_min then
      return jsonb_build_object('ok', true, 'task_id', v_asg.task_id, 'kw_index', v_asg.kw_index,
        'keyword', v_asg.keyword, 'kpi_min', v_asg.kpi_min, 'accepted', coalesce(v_acc, 0),
        'lease_until', v_asg.lease_until, 'reused', true);
    end if;
  end if;

  -- ② 重新分配：本人已认领的任务优先，其次未认领/租约过期；同优先级最老任务优先。
  --    行级 skip locked：并发参与者不会互相等待，也不会拿到同一行。
  for v_task in
    select t.* from public.crowd_tasks t
     where t.status in ('open','in_progress')
       and (t.claimed_by is null or t.claimed_by = p_participant_id
            or t.lease_until is null or t.lease_until < now())
     order by case when t.claimed_by = p_participant_id then 0 else 1 end,
              t.created_at asc
     for update skip locked
  loop
    -- pack 实测为 jsonb 标准数组（双引号，pg_typeof 证伪了"内嵌 repr 单引号串"的误判）。
    -- 防御：jsonb_typeof='array' 才当数组处理，历史脏行（非数组/null）跳过该任务，不炸函数
    if jsonb_typeof(v_task.pack) is distinct from 'array' then continue; end if;
    select array_agg(kw) into v_kws
      from jsonb_array_elements_text(v_task.pack) kw;
    if v_kws is null then continue; end if;

    for v_i in 1..array_length(v_kws, 1) loop
      if v_kws[v_i] = any(p_exclude) then continue; end if;  -- 参与者反馈"找不到"的词
      select coalesce((select kp.accepted from public.crowd_task_keyword_progress kp
                       where kp.task_id = v_task.task_id and kp.keyword = v_kws[v_i]), 0)
        into v_acc;
      if v_acc < v_task.kpi_min then
        v_lease_min := coalesce(v_task.lease_duration_min, 1440);
        -- 认领任务（本循环已持该任务行锁；与 crowd_fetch_tasks 同语义）
        update public.crowd_tasks
           set claimed_by = p_participant_id,
               claimed_at = now(),
               lease_until = now() + make_interval(mins => v_lease_min),
               status = case when status = 'open' then 'in_progress' else status end
         where task_id = v_task.task_id;
        -- 记录分配指针（覆盖旧分配）
        insert into public.crowd_kw_assignments
          (participant_id, task_id, kw_index, keyword, assigned_at, lease_until)
        values (p_participant_id, v_task.task_id, v_i - 1, v_kws[v_i], now(),
                now() + make_interval(mins => v_lease_min))
        on conflict (participant_id) do update
           set task_id = excluded.task_id, kw_index = excluded.kw_index,
               keyword = excluded.keyword, assigned_at = excluded.assigned_at,
               lease_until = excluded.lease_until;
        return jsonb_build_object('ok', true, 'task_id', v_task.task_id, 'kw_index', v_i - 1,
          'keyword', v_kws[v_i], 'kpi_min', v_task.kpi_min, 'accepted', v_acc,
          'lease_until', now() + make_interval(mins => v_lease_min), 'reused', false);
      end if;
    end loop;
    -- 该任务所有关键词均已达标（历史遗留未置 fulfilled）：跳过，继续看下一个任务
  end loop;

  -- 没有任何可分配目标：清理指针，明确返回
  delete from public.crowd_kw_assignments where participant_id = p_participant_id;
  return jsonb_build_object('ok', false, 'reason', 'no_open_task');
end;
$$;

revoke all on function public.crowd_next_target(text, text[]) from public;
grant execute on function public.crowd_next_target(text, text[]) to anon, authenticated;

-- 下一阶段（Phase 2）挂接点：
-- · crowd_submit_proof 校验提交与"当前分配指针"绑定（raw_query 必须等于分配 keyword）
-- · 任务粒度拆成 task_item（每店一行）后，本表即天然成为 per-store 分配表
