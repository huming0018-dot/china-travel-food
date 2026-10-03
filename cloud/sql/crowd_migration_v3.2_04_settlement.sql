-- ============================================================
-- 众包美食家 · 结算闭环（审阅#13）
-- 迁移 v3.2.4：crowd_settle 周期结算 RPC + 结算状态 + 幂等唯一
-- 执行：备份后整体单次提交（Management API / database/query）
-- 计酬规则（默认单价，可随时 UPDATE crowd_settlements 调整下周期）：
--   note   = 1 条有效收录证据 → unit_note   （默认 ¥2.00/条）
--   rating = 1 条有效口味评分   → unit_rating（默认 ¥1.00/条）
-- 结算周期：自然周（周一 00:00 起算），period 用周一日期 YYYY-MM-DD 标识
-- ============================================================

-- 0) 幂等唯一：同一参与者同一周期只保留一条结算行
create unique index if not exists uq_crowd_settlements_pid_period
  on public.crowd_settlements (participant_id, period);

-- 1) 结算状态列（NULL=未结算 / pending=已生成待支付 / paid=已支付）
alter table public.crowd_settlements
  add column if not exists status text not null default 'pending';
alter table public.crowd_settlements
  add column if not exists period_start date;
alter table public.crowd_settlements
  add column if not exists period_end date;

-- 2) 结算函数：按周期聚合 accepted 证据 → upsert 结算行
--    调用：select * from crowd_settle('2026-09-28');   -- 指定周期
--          select * from crowd_settle(null);           -- 本周（默认）
create or replace function public.crowd_settle(p_period text default null)
returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_period_start date;
  v_period_end   date;
  v_result       jsonb;
begin
  -- 周期窗口：null → 本周一00:00 至今
  if p_period is null or p_period = '' then
    v_period_start := date_trunc('week', now())::date;
  else
    v_period_start := p_period::date;
  end if;
  v_period_end := (v_period_start + interval '7 days')::date;
  if v_period_end > now()::date then
    v_period_end := now()::date + 1;  -- 未满整周按今日截止
  end if;

  -- 聚合 accepted 证据（只算真实落地：note 按唯一 note_id、rating 按参与者去重已由索引保证）
  with agg as (
    select
      p.participant_id,
      count(*) filter (where p.kind = 'note')    as eff_notes,
      count(*) filter (where p.kind = 'rating')  as eff_ratings
    from public.crowd_proofs p
    where p.gate_status = 'accepted'
      and p.accepted_at >= v_period_start
      and p.accepted_at <  v_period_end
    group by p.participant_id
    having count(*) > 0
  ),
  ups as (
    insert into public.crowd_settlements
      (participant_id, period, period_start, period_end,
       effective_notes, effective_ratings,
       unit_note, unit_rating, amount, status, settled_at)
    select
      a.participant_id,
      to_char(v_period_start, 'YYYY-MM-DD'),
      v_period_start, v_period_end,
      a.eff_notes, a.eff_ratings,
      coalesce((select unit_note   from public.crowd_settlements s
                where s.participant_id = a.participant_id order by s.settled_at desc nulls last limit 1), 2.00),
      coalesce((select unit_rating from public.crowd_settlements s
                where s.participant_id = a.participant_id order by s.settled_at desc nulls last limit 1), 1.00),
      a.eff_notes * 2.00 + a.eff_ratings * 1.00,
      'pending', now()
    from agg a
    on conflict (participant_id, period) do update set
      effective_notes  = excluded.effective_notes,
      effective_ratings = excluded.effective_ratings,
      amount           = excluded.amount,
      settled_at       = now(),
      status           = case when crowd_settlements.status = 'paid' then 'paid' else 'pending' end
    returning participant_id, period, effective_notes, effective_ratings, amount, status
  )
  select coalesce(jsonb_agg(to_jsonb(u) order by u.participant_id), '[]'::jsonb)
    into v_result
  from ups u;

  return jsonb_build_object('ok', true, 'period', to_char(v_period_start,'YYYY-MM-DD'),
                            'settled', v_result);
end;
$$;

-- 3) 权限：service_role 可执行（PM/调度脚本用）；anon 不开放
revoke execute on function public.crowd_settle(text) from anon, authenticated;
grant  execute on function public.crowd_settle(text) to service_role;

-- 4) 回执列：服务端记录 accepted_at（结算聚合按此窗口）
alter table public.crowd_proofs
  add column if not exists accepted_at timestamptz;
update public.crowd_proofs
   set accepted_at = coalesce(accepted_at, created_at)
 where accepted_at is null;

-- 验收
select 'settlement migration ok' as r;
