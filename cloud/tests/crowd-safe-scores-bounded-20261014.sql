-- Bounded PostgreSQL regression: temporary fixtures only; production ingestion is never called.
-- Captured production function after 20261008134109; only function/table schemas remapped to pg_temp.
begin;
set local statement_timeout='15s';
create temp table restaurants(id integer primary key,name text,score_diner numeric);
create temp table crowd_proofs(matched_store text,kind text,rating numeric,participant_id text,created_at timestamptz default now(),note_id text,gate_status text);
create temp table crowd_store_evidence (like public.crowd_store_evidence including defaults including constraints including indexes);
create temp table crowd_store_candidates (like public.crowd_store_candidates including constraints including indexes);
alter table pg_temp.crowd_store_candidates alter id add generated always as identity;
alter table pg_temp.crowd_store_candidates alter status set default 'open';
alter table pg_temp.crowd_store_candidates alter created_at set default now();
insert into pg_temp.restaurants values(1,'唯一店',1),(2,'重名店（甲）',1),(3,'重名店（乙）',2),(4,'不足三条',1),(5,'别名店',2);
insert into pg_temp.crowd_proofs(matched_store,kind,rating,participant_id,note_id,gate_status)
select store,'rating',rating,'p'||n,'n'||n,'accepted' from (values('唯一店',4),('重名店',5),('别名店',3),('别名店（分店）',5)) v(store,rating),generate_series(1,3)n;
insert into pg_temp.crowd_proofs(matched_store,kind,rating,participant_id,note_id,gate_status)
values('不足三条','rating',5,'p1','t1','accepted'),('不足三条','rating',5,'p2','t2','accepted'),('唯一店','rating',1,'p4','reject','rejected');
CREATE OR REPLACE FUNCTION pg_temp.crowd_ingest_stores(p_dry_run boolean DEFAULT false)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    from pg_temp.crowd_proofs
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
  insert into pg_temp.crowd_store_evidence
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
  -- 每个归一化店名只产生一行；重名时留给人工核对，不猜测餐厅 ID。
  left join (
    select public.norm_store_name(name) as name_key,
           case when count(*) = 1 then min(id) end as id
    from pg_temp.restaurants
    group by 1
  ) r on r.name_key = public.norm_store_name(e.store_name)
  on conflict (store_name) do update set
    note_count        = excluded.note_count,
    rating_count      = excluded.rating_count,
    rating_avg        = excluded.rating_avg,
    participant_count = excluded.participant_count,
    last_seen         = excluded.last_seen,
    sample_note_ids   = excluded.sample_note_ids,
    matched_restaurant_id = excluded.matched_restaurant_id,
    sync_ts           = now();

  -- Only current accepted evidence with a current unique master match may write scores.
  -- Multiple raw aliases are withheld until an explicit aggregation policy exists.
  with current_scores as (
    select r.id, min(e.r_avg) as rating_avg
    from jsonb_to_recordset(v_evidence) as e(store_name text, n_ratings int, r_avg numeric)
    join (
      select public.norm_store_name(name) as name_key, min(id) as id
      from pg_temp.restaurants
      group by 1 having count(*) = 1
    ) r on r.name_key = public.norm_store_name(e.store_name)
    where r.name_key <> ''
    group by r.id
    having count(*) = 1 and min(e.n_ratings) >= 3 and min(e.r_avg) > 0
  )
  update pg_temp.restaurants r set score_diner = e.rating_avg
  from current_scores e
  where e.id = r.id and r.score_diner is distinct from e.rating_avg;
  get diagnostics v_updated = row_count;

  -- 3.4 无主库匹配 → 候选表（人工收录）
  insert into pg_temp.crowd_store_candidates
    (store_name, note_count, rating_count, rating_avg, first_seen, last_seen, sample_note_ids)
  select e.store_name, e.note_count, e.rating_count, e.rating_avg,
         e.first_seen, e.last_seen, e.sample_note_ids
  from pg_temp.crowd_store_evidence e
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
$function$
;
CREATE OR REPLACE FUNCTION pg_temp.crowd_ingest_stores(p_dry_run boolean DEFAULT false)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    from pg_temp.crowd_proofs
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
  insert into pg_temp.crowd_store_evidence
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
  -- 每个归一化店名只产生一行；重名时留给人工核对，不猜测餐厅 ID。
  left join (
    select public.norm_store_name(name) as name_key,
           case when count(*) = 1 then min(id) end as id
    from pg_temp.restaurants
    group by 1
  ) r on r.name_key = public.norm_store_name(e.store_name)
  on conflict (store_name) do update set
    note_count        = excluded.note_count,
    rating_count      = excluded.rating_count,
    rating_avg        = excluded.rating_avg,
    participant_count = excluded.participant_count,
    last_seen         = excluded.last_seen,
    sample_note_ids   = excluded.sample_note_ids,
    matched_restaurant_id = excluded.matched_restaurant_id,
    sync_ts           = now();

  -- Only current accepted evidence with a current unique master match may write scores.
  -- Multiple raw aliases are withheld until an explicit aggregation policy exists.
  with current_scores as (
    select r.id, min(e.r_avg) as rating_avg
    from jsonb_to_recordset(v_evidence) as e(store_name text, n_ratings int, r_avg numeric)
    join (
      select public.norm_store_name(name) as name_key, min(id) as id
      from pg_temp.restaurants
      group by 1 having count(*) = 1
    ) r on r.name_key = public.norm_store_name(e.store_name)
    where r.name_key <> ''
    group by r.id
    having count(*) = 1 and min(e.n_ratings) >= 3 and min(e.r_avg) > 0
  )
  update pg_temp.restaurants r set score_diner = e.rating_avg
  from current_scores e
  where e.id = r.id and r.score_diner is distinct from e.rating_avg;
  get diagnostics v_updated = row_count;

  -- 3.4 无主库匹配 → 候选表（人工收录）
  insert into pg_temp.crowd_store_candidates
    (store_name, note_count, rating_count, rating_avg, first_seen, last_seen, sample_note_ids)
  select e.store_name, e.note_count, e.rating_count, e.rating_avg,
         e.first_seen, e.last_seen, e.sample_note_ids
  from pg_temp.crowd_store_evidence e
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
$function$
;
do $test$ declare r jsonb; begin
r:=pg_temp.crowd_ingest_stores(true);
if (select count(*) from pg_temp.crowd_store_evidence)<>0 then raise exception 'dry run wrote'; end if;
r:=pg_temp.crowd_ingest_stores(false);
if (r->>'updated_restaurants')::int<>1 then raise exception 'unique update %',r;end if;
if (select array_agg(score_diner order by id) from pg_temp.restaurants)<>array[4,1,2,1,2]::numeric[] then raise exception 'scores failed';end if;
r:=pg_temp.crowd_ingest_stores(false);if (r->>'updated_restaurants')::int<>0 then raise exception 'replay failed';end if;
update pg_temp.crowd_proofs set gate_status='rejected' where matched_store='唯一店';
update pg_temp.restaurants set score_diner=2 where id=1;
r:=pg_temp.crowd_ingest_stores(false);
if (r->>'updated_restaurants')::int<>0 or (select score_diner from pg_temp.restaurants where id=1)<>2 then raise exception 'withdrawal failed';end if;
end $test$;
select 'PASS: dry-run, unique match, namesake ambiguity, alias conflict, threshold, rejected evidence, replay, withdrawal; temp fixtures only' result;
rollback;