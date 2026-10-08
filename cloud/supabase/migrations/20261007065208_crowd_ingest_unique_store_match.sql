-- Fix SQLSTATE 21000 from duplicate normalized restaurant names.
-- Ambiguous matches stay candidates; ingestion is a service-only operation.
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
  -- 每个归一化店名只产生一行；重名时留给人工核对，不猜测餐厅 ID。
  left join (
    select public.norm_store_name(name) as name_key,
           case when count(*) = 1 then min(id) end as id
    from public.restaurants
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
revoke execute on function public.crowd_ingest_stores(boolean) from public, anon, authenticated;
grant  execute on function public.crowd_ingest_stores(boolean) to service_role;

