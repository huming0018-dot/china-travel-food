begin;
-- One private invitation admits a bounded cohort; installation identity is pseudonymous.
create table crowd_v4.invites (
 token_hash text primary key check(token_hash ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz not null, max_people int not null check(max_people between 1 and 500),
 quota_day int not null default 20 check(quota_day between 1 and 60), revoked boolean not null default false,
 created_at timestamptz not null default now()
);
create table crowd_v4.enrollments (
 device_hash text primary key check(device_hash ~ '^[a-f0-9]{64}$'),
 invite_hash text not null references crowd_v4.invites(token_hash),
 user_id uuid not null unique default gen_random_uuid(),
 platform text not null check(platform in ('android','ios','harmony','windows','macos','linux')),
 completed_at timestamptz, created_at timestamptz not null default now()
);
create index crowd_v4_enrollments_invite on crowd_v4.enrollments(invite_hash);
alter table crowd_v4.invites enable row level security;
alter table crowd_v4.enrollments enable row level security;
revoke all on crowd_v4.invites,crowd_v4.enrollments from public,anon,authenticated;

create function public.crowd_v4_invite(p_action text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare invitation crowd_v4.invites; enrollment crowd_v4.enrollments; result jsonb; people int;
begin
 if auth.role() is distinct from 'service_role' then raise exception 'service_only' using errcode='42501'; end if;
 if jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'invalid_payload'; end if;
 if p_action='list' then
  select coalesce(jsonb_agg(to_jsonb(invite_row) - 'token_hash'),'[]') into result from
   (select * from crowd_v4.invites order by created_at desc limit 100) invite_row;
  return result;
 end if;
 if coalesce(p_payload->>'token_hash','') !~ '^[a-f0-9]{64}$' then raise exception 'invalid_invite'; end if;
 if p_action='create' then
  if (p_payload->>'expires_at')::timestamptz is null or (p_payload->>'expires_at')::timestamptz<=now()
   or (p_payload->>'expires_at')::timestamptz>now()+interval '90 days' then raise exception 'invalid_expiry'; end if;
  insert into crowd_v4.invites(token_hash,expires_at,max_people,quota_day) values(p_payload->>'token_hash',
   (p_payload->>'expires_at')::timestamptz,(p_payload->>'max_people')::int,coalesce((p_payload->>'quota_day')::int,20));
  insert into crowd_v4.audit(action,payload) values('invite_create',p_payload-'token_hash');
  return jsonb_build_object('created',true);
 end if;
 select * into invitation from crowd_v4.invites where token_hash=p_payload->>'token_hash' for update;
 if not found then raise exception 'invalid_invite'; end if;
 if p_action='revoke' then
  update crowd_v4.invites set revoked=true where token_hash=invitation.token_hash;
  insert into crowd_v4.audit(action,payload) values('invite_revoke',jsonb_build_object('created_at',invitation.created_at));
  return jsonb_build_object('revoked',true);
 end if;
 if invitation.revoked or invitation.expires_at<=now() then raise exception 'invite_expired'; end if;
 select count(*) into people from crowd_v4.enrollments where invite_hash=invitation.token_hash;
 if p_action='check' then return jsonb_build_object('valid',true,'full',people>=invitation.max_people); end if;
 if coalesce(p_payload->>'device_hash','') !~ '^[a-f0-9]{64}$' then raise exception 'invalid_device'; end if;
 select * into enrollment from crowd_v4.enrollments where device_hash=p_payload->>'device_hash' for update;
 if found and enrollment.invite_hash<>invitation.token_hash then raise exception 'installation_already_joined'; end if;
 if p_action='reserve' then
  if enrollment.device_hash is null then
   if people>=invitation.max_people then raise exception 'invite_full'; end if;
   insert into crowd_v4.enrollments(device_hash,invite_hash,platform) values(p_payload->>'device_hash',invitation.token_hash,p_payload->>'platform') returning * into enrollment;
  end if;
  return jsonb_build_object('user_id',enrollment.user_id,'completed',enrollment.completed_at is not null);
 elsif p_action='complete' then
  if enrollment.device_hash is null or coalesce(p_payload->>'consent','')<>'crowd-public-v4' then raise exception 'consent_required'; end if;
  if not exists(select 1 from auth.users where id=enrollment.user_id) then raise exception 'account_not_ready'; end if;
  -- Replays never unsuspend a participant or reset reward balances.
  insert into crowd_v4.participants(user_id,status,consent,quota_day) values(enrollment.user_id,'approved','crowd-public-v4',invitation.quota_day) on conflict(user_id) do nothing;
  update crowd_v4.enrollments set completed_at=coalesce(completed_at,now()) where device_hash=enrollment.device_hash;
  return jsonb_build_object('joined',true,'user_id',enrollment.user_id);
 end if;
 raise exception 'unknown_action';
end $$;
revoke all on function public.crowd_v4_invite(text,jsonb) from public,anon,authenticated;
grant execute on function public.crowd_v4_invite(text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
