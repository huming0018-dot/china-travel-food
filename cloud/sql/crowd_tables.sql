-- ============================================================
-- crowd_tables.sql — 众包采集依赖表（CROWD-CONTRACT-001 §4）
-- PM 窗口提供 · 2026-10-02 · 在 Supabase SQL Editor 执行
-- 建表顺序：participants → tasks → proofs → reviews → settlements
-- 全部幂等（if not exists），可重复执行
-- ============================================================

-- ------------------------------------------------------------
-- 1) crowd_participants — 参与者报名与管控（灵活报名入口落点）
--    报名页(apply.html)匿名 INSERT(status=pending, participant_id=TMP-*)
--    PM 用 crowd_admin.py 审核 → 发放正式 P-XXXXXX + quota_day
--    status: pending(待审) / approved(生效) / suspended(暂停) /
--            blacklisted(拉黑) / rejected(驳回)
-- ------------------------------------------------------------
create table if not exists public.crowd_participants (
  participant_id   text primary key,              -- TMP-* 报名临时 / P-* 审核后正式
  display_name     text not null,                 -- 昵称（展示用）
  contact          text not null,                 -- 联系方式（回传前脱敏展示）
  status           text not null default 'pending'
                   check (status in ('pending','approved','suspended','blacklisted','rejected')),
  quota_day        int  not null default 20,      -- 日配额上限（审核时设定）
  device_salt      text,                          -- 一机一号，首次回传绑定，防多开
  source           text default 'public',         -- 招募渠道：public/referral/crew
  applied_at       timestamptz not null default now(),
  reviewed_at      timestamptz,
  review_note      text,                          -- 审核备注
  total_effective  int  not null default 0,       -- 累计有效条数（ingest 回写）
  reject_rate      float not null default 0,      -- 拒收率（风控自动挂起阈值）
  last_active_at   timestamptz
);

-- 报名开放匿名 INSERT（仅 pending 态可写入，防自封 approved）
create policy "crowd_apply_anon_insert" on public.crowd_participants
  for insert to anon with check (status = 'pending');
-- 报名者可查自己的 TMP 状态（按 participant_id 精确匹配，非全表开放）
create policy "crowd_apply_self_read" on public.crowd_participants
  for select to anon using (status = 'pending' or status = 'approved');

-- ------------------------------------------------------------
-- 2) crowd_tasks — 任务包（插件拉取源，status=open 为可领取）
-- ------------------------------------------------------------
create table if not exists public.crowd_tasks (
  task_id       bigint generated always as identity primary key,
  pack_type     text not null check (pack_type in ('store','keyword')),
  pack          jsonb not null,                    -- ["新荣记", ...] 或 ["外滩法餐", ...]
  target        text not null default 'both' check (target in ('notes','review','both')),
  kpi_min       int  not null default 5,           -- 达标条数（progress>=kpi 即 fulfilled）
  quota_day     int  not null default 20,          -- 单参与者日上限
  progress      int  not null default 0,           -- 已有效回传条数（ingest 回写）
  status        text not null default 'open'
                check (status in ('open','in_progress','fulfilled','closed')),
  source        text not null default 'qa',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists idx_crowd_tasks_status on public.crowd_tasks(status);

-- ------------------------------------------------------------
-- 3) crowd_proofs — 回传 proof 明细（幂等键 + gate_status 唯一权威）
-- ------------------------------------------------------------
create table if not exists public.crowd_proofs (
  id              bigint generated always as identity primary key,
  participant_id  text not null references public.crowd_participants(participant_id),
  task_id         bigint not null references public.crowd_tasks(task_id),
  proof_seq       int  not null,                   -- 参与者本地递增序号
  captured_at     timestamptz,
  sync_version    int  not null default 1,         -- 契约版本（不符拒收）
  kind            text not null check (kind in ('note','rating')),
  note_id         text not null,                   -- 小红书笔记ID
  note_url        text not null,                   -- 必须 xiaohongshu.com 域名
  title           text,
  excerpt         text,
  author          text,                            -- 入库已脱敏
  rating          numeric(2,1),
  rating_reason   text,                            -- rating 必填且≥8字
  matched_store   text,
  anchor_score    float,
  raw_query       text,
  client_ip_salt  text,
  gate_status     text not null default 'accepted'
                  check (gate_status in ('accepted','rejected')),
  dedupe_key      text,                            -- md5(cjk_norm(title)|note_id) 防同篇重复
  created_at      timestamptz not null default now(),
  unique (participant_id, task_id, proof_seq, note_id)      -- 幂等：信封级 seq + item级 note_id 双维度去重
);
create index if not exists idx_crowd_proofs_pid    on public.crowd_proofs(participant_id);
create index if not exists idx_crowd_proofs_task   on public.crowd_proofs(task_id);
create index if not exists idx_crowd_proofs_dedupe on public.crowd_proofs(dedupe_key)
  where gate_status = 'accepted';

-- ------------------------------------------------------------
-- 4) crowd_reviews — 真实口味评分（招募动机：增真实评价，非纯机器采集）
-- ------------------------------------------------------------
create table if not exists public.crowd_reviews (
  id              bigint generated always as identity primary key,
  participant_id  text references public.crowd_participants(participant_id),
  task_id         bigint references public.crowd_tasks(task_id),
  store_name      text not null,
  rating          numeric(2,1) not null check (rating between 1 and 5),
  rating_reason   text not null,
  note_id         text,
  captured_at     timestamptz,
  trust_level     text not null default 'crowd_single',
  created_at      timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 5) crowd_settlements — 结算流水（单价可配置，暂不锁死）
-- ------------------------------------------------------------
create table if not exists public.crowd_settlements (
  id               bigint generated always as identity primary key,
  participant_id   text not null references public.crowd_participants(participant_id),
  period           text not null,                  -- '2026-W40' 周 / '2026-10' 月
  effective_notes  int  not null default 0,        -- 有效笔记数
  effective_ratings int not null default 0,        -- 有效评分数
  unit_note        numeric(4,2) not null default 0.50,
  unit_rating      numeric(4,2) not null default 1.00,
  amount           numeric(10,2) not null default 0,
  settled_at       timestamptz default now(),
  unique (participant_id, period)
);

-- ------------------------------------------------------------
-- RLS：除报名表开放 anon insert/自查外，其余表仅 service_role
-- （插件回传走 service_role key；应用侧后续可再收窄）
-- ------------------------------------------------------------
alter table public.crowd_tasks       enable row level security;
alter table public.crowd_proofs      enable row level security;
alter table public.crowd_reviews     enable row level security;
alter table public.crowd_settlements enable row level security;
alter table public.crowd_participants enable row level security;

-- 执行后验证：select count(*) from crowd_tasks; 应返回 0（空表就绪）
