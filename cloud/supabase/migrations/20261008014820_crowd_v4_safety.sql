begin;
-- Private, server-clock admission. Attempts are charged BEFORE public-page actions.
create table crowd_v4.policy (
 singleton boolean primary key default true check(singleton), version bigint not null default 1,
 paused boolean not null default false, search_cap int not null default 30 check(search_cap between 1 and 30),
 detail_cap int not null default 60 check(detail_cap between 1 and 60),
 comment_cap int not null default 120 check(comment_cap between 1 and 120),
 scroll_cap int not null default 120 check(scroll_cap between 1 and 120),
 gap_seconds int not null default 30 check(gap_seconds between 30 and 3600)
);
insert into crowd_v4.policy(singleton) values(true);
create table crowd_v4.safety (
 user_id uuid primary key references crowd_v4.participants(user_id),
 day date not null default (now() at time zone 'Asia/Shanghai')::date,
 counts jsonb not null default '{"search":0,"detail":0,"comment":0,"scroll":0}',
 next_action timestamptz not null default now(), cooldown_until timestamptz not null default now(),
 cooldown_reason text, session_count int not null default 0,
 session_started timestamptz not null default now()
);
create table crowd_v4.note_reservations (
 note_id text primary key check(note_id ~ '^[a-f0-9]{24}$'),
 user_id uuid not null references crowd_v4.participants(user_id), expires_at timestamptz not null
);
alter table crowd_v4.policy enable row level security;
alter table crowd_v4.safety enable row level security;
alter table crowd_v4.note_reservations enable row level security;
revoke all on crowd_v4.policy,crowd_v4.safety,crowd_v4.note_reservations from public,anon,authenticated;
create index crowd_v4_reservations_expiry on crowd_v4.note_reservations(expires_at);

create function public.crowd_v4_guard(p_action text default 'control',p_task bigint default null,p_note text default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
 u uuid:=auth.uid(); p crowd_v4.participants; c crowd_v4.policy; s crowd_v4.safety;
 t timestamptz:=clock_timestamp(); d date; caps jsonb; factor numeric; reason text; wait_until timestamptz;
 admitted boolean:=false; owner uuid; result jsonb;
begin
 if u is null then raise exception 'login_required' using errcode='42501'; end if;
 if p_action is null or p_action not in ('control','search','detail','comment','scroll','captcha','rate_limit') then raise exception 'invalid_action'; end if;
 -- One identity's admission decisions serialize with its quota/lease operations.
 select * into p from crowd_v4.participants where user_id=u for update;
 if p.status is distinct from 'approved' or p.consent is distinct from 'crowd-public-v4' then raise exception 'approval_required' using errcode='42501'; end if;
 select * into c from crowd_v4.policy where singleton;
 if c.version is null then raise exception 'control_unavailable'; end if;
 insert into crowd_v4.safety(user_id) values(u) on conflict do nothing;
 select * into s from crowd_v4.safety where user_id=u for update;
 d:=(t at time zone 'Asia/Shanghai')::date;
 if d>s.day then s.day:=d; s.counts:='{"search":0,"detail":0,"comment":0,"scroll":0}'; end if;
 -- Server enrollment age, never a resettable client date. Future dates stay at 20%.
 factor:=least(1,0.2+greatest(0,floor(extract(epoch from t-p.joined_at)/86400))*0.8/6);
 caps:=jsonb_build_object('search',greatest(1,floor(c.search_cap*factor)),
 'detail',greatest(1,floor(c.detail_cap*factor)), 'comment',greatest(1,floor(c.comment_cap*factor)), 'scroll',greatest(1,floor(c.scroll_cap*factor)));
 if p_action in ('captcha','rate_limit') then
  s.cooldown_until:=greatest(s.cooldown_until,t+case p_action when 'rate_limit' then interval '24 hours' else interval '30 minutes' end);
  s.cooldown_reason:=p_action;
 end if;
 if s.cooldown_until>t then reason:=s.cooldown_reason; wait_until:=s.cooldown_until;
 elsif c.paused then reason:='global_pause'; wait_until:=t+interval '5 minutes';
 elsif s.next_action>t then reason:='action_gap'; wait_until:=s.next_action;
 end if;
 if p_action in ('search','detail','comment','scroll') and reason is null then
  if not exists(select from crowd_v4.tasks where id=p_task and claimed_by=u and status='leased' and lease_until>t) then
   return jsonb_build_object('error','lease_expired');
  end if;
  if (s.counts->>p_action)::int >= (caps->>p_action)::int then
   reason:='action_budget'; wait_until:=(d+1)::timestamp at time zone 'Asia/Shanghai';
  else
   if s.session_count>=20 or (s.session_count>0 and s.session_started+interval '20 minutes'<=t) then
    s.session_count:=0; s.session_started:=t+interval '30 minutes';
    s.cooldown_until:=s.session_started; s.cooldown_reason:='session_rest';
    reason:='session_rest'; wait_until:=s.cooldown_until;
   else
    if p_action='detail' then
     if p_note is null or p_note !~ '^[a-f0-9]{24}$' then raise exception 'invalid_note'; end if;
     if exists(select from crowd_v4.proofs where note_id=p_note and status<>'rejected') then
      reason:='known_note';
     else
      -- Only reserve one requested ID, never expose another participant or proof.
      insert into crowd_v4.note_reservations(note_id,user_id,expires_at) values(p_note,u,t+interval '10 minutes')
      on conflict(note_id) do update set user_id=u,expires_at=t+interval '10 minutes'
       where crowd_v4.note_reservations.expires_at<=t or crowd_v4.note_reservations.user_id=u
      returning user_id into owner;
      if owner is null then reason:='note_busy'; end if;
     end if;
    end if;
    if reason is null then
     if s.session_count=0 then s.session_started:=t; end if;
     s.session_count:=s.session_count+1;
     s.counts:=jsonb_set(s.counts,array[p_action],to_jsonb((s.counts->>p_action)::int+1));
     -- Sample ONCE per admitted action and persist; polling never redraws the wait.
     s.next_action:=t+make_interval(secs=>c.gap_seconds+floor(random()*16)::int);
     admitted:=true;
    end if;
   end if;
  end if;
 end if;
 update crowd_v4.safety set day=s.day,counts=s.counts,next_action=s.next_action,cooldown_until=s.cooldown_until,
 cooldown_reason=s.cooldown_reason,session_count=s.session_count,session_started=s.session_started where user_id=u;
 -- Expired reservations are not retained as a browsing history.
 delete from crowd_v4.note_reservations where expires_at<t-interval '1 day';
 result:=jsonb_build_object('version',c.version,'ttl_ms',600000,'paused',c.paused,'allowed',admitted,
 'reason',reason,'wait_ms',greatest(0,ceil(extract(epoch from (wait_until-t))*1000)),
 'gap_ms',c.gap_seconds*1000,'caps',caps,'counts',s.counts,'session_count',s.session_count);
 return result;
end $$;
revoke all on function public.crowd_v4_guard(text,bigint,text) from public,anon;
grant execute on function public.crowd_v4_guard(text,bigint,text) to authenticated;

-- Reuse the existing audited operator entry point; no new credential or backdoor.
do $patch$
declare definition text; needle text := 'begin' || chr(10); addition text := $body$
 if p_action='control' then
  if auth.role() is distinct from 'service_role' then raise exception 'operator_required' using errcode='42501'; end if;
  if jsonb_typeof(p_payload) is distinct from 'object' or (p_payload - array['paused','search_cap','detail_cap','comment_cap','scroll_cap','gap_seconds'])<>'{}'::jsonb
   or (p_payload ? 'paused' and jsonb_typeof(p_payload->'paused') is distinct from 'boolean') then raise exception 'invalid_control'; end if;
  if p_payload='{}'::jsonb then return (select to_jsonb(c)-'singleton' from crowd_v4.policy c where singleton); end if;
  update crowd_v4.policy set version=version+1,
   paused=coalesce((p_payload->>'paused')::boolean,paused),
   search_cap=coalesce((p_payload->>'search_cap')::int,search_cap), detail_cap=coalesce((p_payload->>'detail_cap')::int,detail_cap),
   comment_cap=coalesce((p_payload->>'comment_cap')::int,comment_cap), scroll_cap=coalesce((p_payload->>'scroll_cap')::int,scroll_cap),
   gap_seconds=coalesce((p_payload->>'gap_seconds')::int,gap_seconds) where singleton;
  insert into crowd_v4.audit(action,payload) values('control',p_payload);
  return (select to_jsonb(c)-'singleton' from crowd_v4.policy c where singleton);
 end if;
$body$;
begin
 definition:=pg_get_functiondef('public.crowd_v4_admin(text,jsonb)'::regprocedure);
 if position(needle in definition)=0 then raise exception 'admin_patch_anchor_missing'; end if;
 -- First outer BEGIN only: do not splice into nested blocks.
 definition:=overlay(definition placing needle||addition from position(needle in definition) for length(needle));
 execute definition;
end $patch$;
-- Extend the existing privacy-preserving diagnostic enum, not arbitrary text.
do $diag$
declare definition text; needle text := $enum$'backend_unavailable','unexpected_error'$enum$;
begin
 if to_regprocedure('public.crowd_v4_diagnostics(text,bigint,jsonb)') is not null then
  definition:=pg_get_functiondef('public.crowd_v4_diagnostics(text,bigint,jsonb)'::regprocedure);
  if position(needle in definition)=0 then raise exception 'diagnostics_patch_anchor_missing'; end if;
  execute replace(definition,needle,$enum$'backend_unavailable','control_unavailable','global_pause','action_budget','action_gap','session_rest','known_note','note_busy','unexpected_error'$enum$);
 end if;
end $diag$;
commit;
