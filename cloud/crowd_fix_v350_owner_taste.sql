-- ============================================================================
-- crowd_fix_v350_owner_taste.sql
-- 口味评分体系重设计 v1 · 第一阶段（M0 owner 评价端 + S3 打分落表）
--
-- 内容：
--   1) crowd_private_config      兜底建表（已存在则 no-op；owner_secret 存这里）
--   2) crowd_owner_ratings       owner 到店评分/成对比较（设计稿 §3.1 主标尺证据）
--   3) crowd_taste_scores        S3 打分输出表（Beta 后验 + BT 排名 + CI + 锚状态）
--   4) RPC crowd_fetch_stores()  只读门店候选列表（owner-rate.html 下拉用，anon 可调）
--   5) RPC crowd_owner_rate(...) owner 评分写入（p_secret 校验，anon 可调、密钥收口）
--
-- 幂等：CREATE IF NOT EXISTS / CREATE OR REPLACE，可重复执行。
-- 部署后需手工注入 owner 密钥（值勿入库迁移文件，owner 私下提供）：
--   insert into public.crowd_private_config (key, value) values ('owner_secret', '<值>')
--   on conflict (key) do update set value = excluded.value;
-- ============================================================================

-- ------------------------------------------------------------ 1) 私有配置表兜底
create table if not exists public.crowd_private_config (
  key   text primary key,
  value text
);
-- 不对 anon 开放任何直读（owner_secret 等机密只经 security definer 函数内部使用）
alter table public.crowd_private_config enable row level security;

-- ------------------------------------------------------------ 2) owner 评分表
-- 设计稿 §3.1：owner 到店评分 m=25（主输入）；compare_to 非空表示一次成对比较
-- "store ≻ compare_to"（BT 全权重 η=1.0，m≈40 等效）。
create table if not exists public.crowd_owner_ratings (
  id          bigint generated always as identity primary key,
  store       text not null,
  score       int  not null check (score between 1 and 5),
  reason      text not null,
  compare_to  text,                    -- 可选：成对比较"本店优于哪家"（B 店名）
  created_at  timestamptz not null default now()
);
create index if not exists idx_crowd_owner_ratings_store on public.crowd_owner_ratings(store);
-- RLS 无任何 policy = anon 不可直读直写；只经 crowd_owner_rate RPC 写入
alter table public.crowd_owner_ratings enable row level security;

-- ------------------------------------------------------------ 3) S3 输出表
-- 设计稿 §4-§5：每 (store, cuisine_ctx, model_version) 一行；S3 全量确定性重算，
-- 同 model_version delete+insert（幂等重放），旧版本留档可审计。
create table if not exists public.crowd_taste_scores (
  id                      bigint generated always as identity primary key,
  model_version           text not null,           -- 参数版本 + 输入摘要哈希（同输入同输出）
  store                   text not null,
  cuisine_ctx             text not null default 'unknown',
  alpha                   float not null,          -- Beta 后验 α
  beta                    float not null,          -- Beta 后验 β
  post_mean               float not null,          -- 后验均值（1-5 分制）
  ci_lo                   float not null,          -- 95% CI 下界（Beta 分位数，1-5 分制）
  ci_hi                   float not null,          -- 95% CI 上界
  evidence_count          float not null,          -- 有效证据数 n_eff（加权折后）
  owner_evidence_share    float not null,          -- owner 证据占有效证据比例
  owner_anchor_sufficient boolean not null,        -- owner 占比 >= 1/3（§3.1 锚不足规则）
  gamma                   float,                   -- BT 潜变量（菜系 cell 内）
  rank_in_cuisine         int,                     -- 菜系 cell 内排名（shrinkage 混合秩）
  anchor_state            text not null default 'rank_only'
                          check (anchor_state in ('anchored','rank_only')),
  signals_used            jsonb not null default '{}'::jsonb,  -- 输入清单 + 参数留档（可复算）
  computed_at             timestamptz not null default now(),
  unique (model_version, store, cuisine_ctx)
);
-- 不对外公开（设计稿 §7：众包参与者永远看不到分数与排名）
alter table public.crowd_taste_scores enable row level security;

-- ------------------------------------------------------------ 4) 只读门店候选 RPC
-- owner-rate.html 下拉数据源：全部 store 型任务包的门店名（去重排序）。
-- 只读、无敏感列（店名本身即任务公开内容，status 页已公开最近提交的门店名）。
create or replace function public.crowd_fetch_stores()
returns json
language plpgsql
security definer
set search_path = public
as $$
begin
  return (
    select coalesce(json_agg(s order by s), '[]'::json)
      from (
        select distinct btrim(store) as s
          from public.crowd_tasks t,
               lateral jsonb_array_elements_text(t.pack) as store
         where t.pack_type = 'store'
      ) x
     where s <> ''
  );
end;
$$;
revoke all on function public.crowd_fetch_stores() from public;
grant execute on function public.crowd_fetch_stores() to anon, authenticated, service_role;

-- ------------------------------------------------------------ 5) owner 评分 RPC
-- 校验链：密钥 → 店名 → 分值 1-5 → 理由 ≥8 字（与 R6 同口径：去空白+ASCII标点）
--         → 成对比较不能自比。全部通过才落 crowd_owner_ratings。
create or replace function public.crowd_owner_rate(
  p_store      text,
  p_score      int,
  p_reason     text,
  p_compare_to text,
  p_secret     text
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_secret text;
begin
  select value into v_secret
    from public.crowd_private_config
   where key = 'owner_secret';
  if v_secret is null or v_secret = '' then
    return json_build_object('ok', false, 'reason', 'owner_secret_not_configured');
  end if;
  if coalesce(p_secret, '') = '' or p_secret <> v_secret then
    return json_build_object('ok', false, 'reason', 'forbidden');
  end if;
  if p_store is null or length(btrim(p_store)) < 2 then
    return json_build_object('ok', false, 'reason', 'store_invalid');
  end if;
  if p_score is null or p_score < 1 or p_score > 5 then
    return json_build_object('ok', false, 'reason', 'score_out_of_range');
  end if;
  if coalesce(length(regexp_replace(coalesce(p_reason, ''), '[\s[:punct:]]', '', 'g')), 0) < 8 then
    return json_build_object('ok', false, 'reason', 'reason_too_short');
  end if;
  if p_compare_to is not null and btrim(p_compare_to) <> '' and btrim(p_compare_to) = btrim(p_store) then
    return json_build_object('ok', false, 'reason', 'compare_same_store');
  end if;

  insert into public.crowd_owner_ratings (store, score, reason, compare_to)
  values (left(btrim(p_store), 100),
          p_score,
          left(p_reason, 500),
          nullif(left(btrim(coalesce(p_compare_to, '')), 100), ''));
  return json_build_object('ok', true);
end;
$$;
revoke all on function public.crowd_owner_rate(text, int, text, text, text) from public;
grant execute on function public.crowd_owner_rate(text, int, text, text, text) to anon, authenticated, service_role;
