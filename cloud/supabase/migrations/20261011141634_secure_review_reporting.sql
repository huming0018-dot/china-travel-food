-- Preserve existing report_count values. No backfill or recount.
create schema if not exists report_private;
revoke all on schema report_private from public, anon;
grant usage on schema report_private to authenticated;
create table report_private.review_reports (
  review_id uuid not null references public.reviews(id) on delete cascade,
  reporter_id uuid not null,
  created_at timestamptz not null default now(),
  primary key (review_id, reporter_id)
);
create index review_reports_reporter_time on report_private.review_reports(reporter_id, created_at);
alter table report_private.review_reports enable row level security;
revoke all on report_private.review_reports from public, anon, authenticated;

-- Count is server-managed, including on INSERT; retain other existing column writes.
revoke insert, update on public.reviews from public, anon, authenticated;
revoke insert (report_count), update (report_count) on public.reviews from public, anon, authenticated;
do $$
declare cols text;
begin
  select string_agg(quote_ident(attname), ', ') into cols
  from pg_attribute where attrelid='public.reviews'::regclass
    and attnum>0 and not attisdropped and attname<>'report_count';
  execute format('grant insert (%s), update (%s) on public.reviews to authenticated', cols, cols);
end $$;

create function report_private.increment_report(review_id uuid)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare actor uuid := auth.uid(); total integer;
begin
  if actor is null or coalesce((auth.jwt()->>'is_anonymous')::boolean,false) then
    raise exception using errcode='42501', message='Sign in required';
  end if;
  -- Serializes each account's rate check, including requests to different reviews.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(actor::text, 728194));
  select coalesce(r.report_count,0) into total from public.reviews r
    where r.id=review_id and r.is_hidden=false for update;
  if not found then
    raise exception using errcode='P0002', message='Review unavailable';
  end if;
  if exists (select 1 from report_private.review_reports rr
             where rr.review_id=increment_report.review_id and rr.reporter_id=actor) then
    return jsonb_build_object('accepted',false,'report_count',total);
  end if;
  if (select count(*) from report_private.review_reports rr
      where rr.reporter_id=actor and rr.created_at>now()-interval '1 hour') >= 20 then
    raise exception using errcode='P0001', message='Report rate limit exceeded';
  end if;
  insert into report_private.review_reports(review_id,reporter_id) values(review_id,actor);
  update public.reviews r set report_count=coalesce(r.report_count,0)+1
    where r.id=review_id returning r.report_count into total;
  return jsonb_build_object('accepted',true,'report_count',total);
end $$;
revoke all on function report_private.increment_report(uuid) from public, anon;
grant execute on function report_private.increment_report(uuid) to authenticated;
-- Exposed wrapper has no elevated privileges. Private implementation checks caller identity.
create function public.increment_report(review_id uuid)
returns jsonb language sql security invoker set search_path = ''
as $$ select report_private.increment_report(review_id); $$;
revoke all on function public.increment_report(uuid) from public, anon;
grant execute on function public.increment_report(uuid) to authenticated;
notify pgrst, 'reload schema';

