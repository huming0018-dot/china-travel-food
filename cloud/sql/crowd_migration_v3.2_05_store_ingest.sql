-- ============================================================
-- 众包美食家 · 入库链路（审阅#13 收尾：证据 → 店铺聚合 → 主库对接）
-- 迁移 v3.2.5：store 证据聚合 + 候选收录 + score_diner 真实评分回写
-- 执行：备份后整体单次提交（Management API / database/query）
-- 链路：crowd_proofs(accepted) ─聚合─> crowd_store_evidence
--        └─ 匹配 restaurants ──> 更新 score_diner（≥3 条评分才动）
--        └─ 无匹配 ──> crowd_store_candidates（待人工收录）
-- ============================================================

-- 0) 证据聚合表（按店名聚合 accepted 证据，主库对接锚点）
create table if not exists public.crowd_store_evidence (
  store_name           text primary key,
  note_count           integer not null default 0,
  rating_count         integer not null default 0,
  rating_avg           numeric(3,2) not null default 0,
  participant_count    integer not null default 0,
  first_seen           timestamptz not null default now(),
  last_seen            timestamptz not null default now(),
  sample_note_ids      jsonb not null default '[]'::jsonb,
  matched_restaurant_id integer,
  sync_ts              timestamptz not null default now()
);

-- 1) 候选收录表（无主库匹配的新店，人工审核后收录）
create table if not exists public.crowd_store_candidates (
  id           bigint generated always as identity primary key,
  store_name   text not null,
  note_count   integer not null default 0,
  rating_count integer not null default 0,
  rating_avg   numeric(3,2) not null default 0,
  first_seen   timestamptz not null default now(),
  last_seen    timestamptz not null default now(),
  sample_note_ids jsonb not null default '[]'::jsonb,
  status       text not null default 'open',   -- open / adopted / ignored
  created_at   timestamptz not null default now()
);
create unique index if not exists uq_crowd_store_candidates_name_status
  on public.crowd_store_candidates (store_name, status);

-- 2) 名称归一化（匹配主库用：小写、去空格、去括号及括号内容）
create or replace function public.norm_store_name(p text)
returns text language sql immutable as $$
  select lower(regexp_replace(coalesce(p, ''), '\s+|（.*?）|\(.*?\)', '', 'g'));
$$;

-- 3) 入库 RPC：聚合 accepted 证据 → 证据表 + 主库 score_diner / 候选表
create or replace function public.crowd_ingest_stores(p_dry_run boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_evidence jsonb;
  v_updated  integer := 0;
  v_candidates integer := 0;
begin
  -- 3.1 聚合 accepted 证据（note 计入曝光、rating 计入评分）
  with agg as (
    select
      nullif(trim(coalesce(matched_store,'')),'') as store_name,
      count(*) filter (where kind = 'note')   as n_notes,
      count(*) filter (where kind = 'rating') as n_ratings,
      round(avg(rating) filter (where kind = 'rating'), 2) as r_avg,
      count(distinct participant_id) as n_parts,
      min(created_at) as first_ts,
      max(created_at) as last_ts,
      jsonb_agg(note_id) filter (where kind = 'note') as note_ids
    from public.crowd_proofs
    where gate_status = 'accepted'
    group by 1
  )
  select coalesce(jsonb_agg(x order by x.store_name), '[]'::jsonb) into v_evidence
  from (
    select a.* from agg a where a.store_name is not null
  ) x;

  if p_dry_run then
    return jsonb_build_object('ok', true, 'dry_run', true, 'evidence', v_evidence,
                              'updated_restaurants', 0, 'candidates', 0);
  end if;

  -- 3.2 upsert 证据表
  insert into public.crowd_store_evidence
    (store_name, note_count, rating_count, rating_avg, participant_count,
     first_seen, last_seen, sample_note_ids, matched_restaurant_id, sync_ts)
  select
    e.store_name, e.n_notes, e.n_ratings, coalesce(e.r_avg,0),
    e.n_parts, e.first_ts, e.last_ts,
    coalesce(e.note_ids, '[]'::jsonb),
    r.id,
    now()
  from jsonb_to_recordset(v_evidence) as e(
    store_name text, n_notes int, n_ratings int, r_avg numeric,
    n_parts int, first_ts timestamptz, last_ts timestamptz, note_ids jsonb)
  left join public.restaurants r
    on public.norm_store_name(r.name) = public.norm_store_name(e.store_name)
  on conflict (store_name) do update set
    note_count        = excluded.note_count,
    rating_count      = excluded.rating_count,
    rating_avg        = excluded.rating_avg,
    participant_count = excluded.participant_count,
    last_seen         = excluded.last_seen,
    sample_note_ids   = excluded.sample_note_ids,
    matched_restaurant_id = excluded.matched_restaurant_id,
    sync_ts           = now();

  -- 3.3 主库对接：≥3 条 accepted 评分才回写 score_diner（避免 1 条污染）
  update public.restaurants r set score_diner = e.rating_avg
  from public.crowd_store_evidence e
  where e.matched_restaurant_id = r.id
    and e.rating_count >= 3
    and e.rating_avg > 0
    and r.score_diner is distinct from e.rating_avg;
  get diagnostics v_updated = row_count;

  -- 3.4 无主库匹配 → 候选表（人工收录）
  insert into public.crowd_store_candidates
    (store_name, note_count, rating_count, rating_avg, first_seen, last_seen, sample_note_ids)
  select e.store_name, e.note_count, e.rating_count, e.rating_avg,
         e.first_seen, e.last_seen, e.sample_note_ids
  from public.crowd_store_evidence e
  where e.matched_restaurant_id is null
  on conflict (store_name, status) do update set
    note_count = excluded.note_count,
    rating_count = excluded.rating_count,
    rating_avg = excluded.rating_avg,
    last_seen = excluded.last_seen,
    sample_note_ids = excluded.sample_note_ids;
  get diagnostics v_candidates = row_count;

  return jsonb_build_object('ok', true, 'dry_run', false,
                            'evidence_count', jsonb_array_length(v_evidence),
                            'updated_restaurants', v_updated,
                            'candidates', v_candidates);
end;
$$;

-- 4) 权限：service_role 可执行
revoke execute on function public.crowd_ingest_stores(boolean) from anon, authenticated;
grant  execute on function public.crowd_ingest_stores(boolean) to service_role;

-- 验收
select 'store ingest migration ok' as r;
