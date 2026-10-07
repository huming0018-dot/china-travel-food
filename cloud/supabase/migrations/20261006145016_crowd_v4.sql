begin;
-- v4 is isolated: old proofs/settlements are historical, never repriced.
create schema if not exists crowd_v4;
revoke all on schema crowd_v4 from public, anon, authenticated;
create table crowd_v4.participants (
 user_id uuid primary key references auth.users(id), status text not null default 'pending' check(status in ('pending','approved','suspended')),
 consent text not null check(consent='crowd-public-v4'), joined_at timestamptz not null default now(), quota_day int not null default 20 check(quota_day between 1 and 100),
 verified_count int not null default 0 check(verified_count>=0)
);
create table crowd_v4.tasks (
 id bigint generated always as identity primary key, source_key text not null unique, query text not null check(length(query) between 2 and 120),
 store_name text, restaurant_id bigint, anchor_terms jsonb not null check(jsonb_typeof(anchor_terms)='array' and jsonb_array_length(anchor_terms) between 1 and 10),
 target int not null default 5 check(target between 1 and 20), received int not null default 0,
 status text not null default 'open' check(status in ('open','leased','complete','exhausted','closed')),
 claimed_by uuid references crowd_v4.participants(user_id), lease_token uuid, lease_until timestamptz, created_at timestamptz not null default now()
);
create index crowd_v4_tasks_claim on crowd_v4.tasks(status, lease_until, id);
create index crowd_v4_tasks_owner on crowd_v4.tasks(claimed_by) where status='leased';
create table crowd_v4.proofs (
 id bigint generated always as identity primary key, note_id text not null unique check(note_id ~ '^[a-f0-9]{24}$'),
 user_id uuid not null references crowd_v4.participants(user_id), task_id bigint not null references crowd_v4.tasks(id),
 record jsonb not null, status text not null default 'received' check(status in ('received','verified','rejected')),
 received_at timestamptz not null default now(), reviewed_at timestamptz, review_note text, verified_quote text,
 source_checked_at timestamptz, exported_at timestamptz
);
create index crowd_v4_proofs_user_time on crowd_v4.proofs(user_id, received_at);
create index crowd_v4_proofs_review on crowd_v4.proofs(status, id);
create table crowd_v4.receipts (
 user_id uuid not null references crowd_v4.participants(user_id), request uuid not null,
 payload jsonb not null, result jsonb not null, created_at timestamptz not null default now(), primary key(user_id, request)
);
create table crowd_v4.rewards (
 user_id uuid not null references crowd_v4.participants(user_id), batch_no int not null check(batch_no>0),
 valid_notes int not null default 100 check(valid_notes=100), amount_fen int not null default 10 check(amount_fen=10),
 created_at timestamptz not null default now(), paid_at timestamptz, payment_reference text,
 primary key(user_id,batch_no), check((paid_at is null)=(payment_reference is null))
);
create table crowd_v4.audit (
 id bigint generated always as identity primary key, action text not null, payload jsonb not null, created_at timestamptz not null default now()
);
alter table crowd_v4.participants enable row level security;
alter table crowd_v4.tasks enable row level security;
alter table crowd_v4.proofs enable row level security;
alter table crowd_v4.receipts enable row level security;
alter table crowd_v4.rewards enable row level security;
alter table crowd_v4.audit enable row level security;
revoke all on all tables in schema crowd_v4 from public, anon, authenticated;
revoke all on all sequences in schema crowd_v4 from public, anon, authenticated;

create function public.crowd_v4_register(p_consent text) returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid := auth.uid();
begin
 if u is null then raise exception 'login_required' using errcode='42501'; end if;
 if p_consent is distinct from 'crowd-public-v4' then raise exception 'consent_required'; end if;
 insert into crowd_v4.participants(user_id,consent) values(u,p_consent) on conflict(user_id) do nothing;
 return jsonb_build_object('participant',(select to_jsonb(p) - 'user_id' from crowd_v4.participants p where user_id=u));
end $$;
create function public.crowd_v4_status() returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid := auth.uid(); p crowd_v4.participants; n int;
begin
 if u is null then raise exception 'login_required' using errcode='42501'; end if;
 select * into p from crowd_v4.participants where user_id=u;
 select count(*) into n from crowd_v4.proofs where user_id=u;
 return jsonb_build_object('participant',case when p.user_id is null then null else to_jsonb(p)-'user_id' end,
 'received',n,'verified',coalesce(p.verified_count,0),'remainder',coalesce(p.verified_count,0)%100,
 'reward_fen',(select coalesce(sum(amount_fen),0) from crowd_v4.rewards where user_id=u),
 'paid_fen',(select coalesce(sum(amount_fen),0) from crowd_v4.rewards where user_id=u and paid_at is not null));
end $$;
create function public.crowd_v4_claim(p_task bigint default null) returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid := auth.uid(); p crowd_v4.participants; t crowd_v4.tasks; n int;
begin
 if u is null then raise exception 'login_required' using errcode='42501'; end if;
 select * into p from crowd_v4.participants where user_id=u for update;
 if p.status is distinct from 'approved' then raise exception 'approval_required' using errcode='42501'; end if;
 if p.consent is distinct from 'crowd-public-v4' then raise exception 'consent_required'; end if;
 select count(*) into n from crowd_v4.proofs where user_id=u and received_at>=date_trunc('day',now() at time zone 'Asia/Shanghai') at time zone 'Asia/Shanghai';
 if n>=p.quota_day then return jsonb_build_object('error','daily_quota'); end if;
 -- Same owner renews an existing lease before receiving another task.
 select * into t from crowd_v4.tasks where claimed_by=u and status='leased' and (p_task is null or id=p_task) order by id limit 1 for update;
 if t.id is null then
  if p_task is not null then return jsonb_build_object('task',null); end if;
  select * into t from crowd_v4.tasks where status='open' or (status='leased' and lease_until<now()) order by id limit 1 for update skip locked;
 end if;
 if t.id is null then return jsonb_build_object('task',null); end if;
 update crowd_v4.tasks set status='leased',claimed_by=u,lease_token=case when claimed_by=u then coalesce(lease_token,gen_random_uuid()) else gen_random_uuid() end,
 lease_until=now()+interval '20 minutes' where id=t.id returning * into t;
 return jsonb_build_object('task',(to_jsonb(t)-'claimed_by'-'source_key')||jsonb_build_object('remaining_today',p.quota_day-n));
end $$;
create function public.crowd_v4_submit(p_request uuid,p_task bigint,p_lease uuid,p_record jsonb) returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid := auth.uid(); p crowd_v4.participants; t crowd_v4.tasks; old crowd_v4.receipts; n int; inserted_id bigint; s jsonb; e jsonb; result jsonb; capture timestamptz; payload jsonb;
begin
 if u is null then raise exception 'login_required' using errcode='42501'; end if;
 if p_request is null or p_task is null or p_lease is null then return jsonb_build_object('error','invalid_envelope'); end if;
 select * into p from crowd_v4.participants where user_id=u for update;
 if p.user_id is null then raise exception 'approval_required' using errcode='42501'; end if;
 payload:=jsonb_build_object('task',p_task,'record',p_record);
 select * into old from crowd_v4.receipts where user_id=u and request=p_request;
 -- Replays return the EXACT receipt, even after task completion/expiry/suspension.
 if old.request is not null then
  if old.payload is distinct from payload then return jsonb_build_object('error','request_reused'); end if;
  return old.result;
 end if;
 if p.status<>'approved' or p.consent<>'crowd-public-v4' then raise exception 'approval_required' using errcode='42501'; end if;
 select * into t from crowd_v4.tasks where id=p_task for update;
 if t.id is null or t.claimed_by is distinct from u or t.lease_token is distinct from p_lease or t.status<>'leased' then return jsonb_build_object('error','lease_lost'); end if;
 if t.lease_until<now() then return jsonb_build_object('error','lease_expired'); end if;
 if t.received>=t.target then return jsonb_build_object('error','task_full'); end if;
 s:=p_record->'standard'; e:=p_record->'evidence';
 if jsonb_typeof(p_record) is distinct from 'object' or p_record->>'schema_version' is distinct from '4'
 or jsonb_typeof(s) is distinct from 'object' or jsonb_typeof(e) is distinct from 'object' or jsonb_typeof(p_record->'extra') is distinct from 'object'
 or octet_length(p_record::text)>180000 or s->>'platform' is distinct from 'xiaohongshu'
 or coalesce(s->>'note_id','') !~ '^[a-f0-9]{24}$' or s->>'url' is distinct from ('https://www.xiaohongshu.com/explore/'||(s->>'note_id'))
 or jsonb_typeof(s->'title') is distinct from 'string' or length(s->>'title')>300
 or jsonb_typeof(e->'text') is distinct from 'string' or length(e->>'text') not between 8 and 24000
 or e->>'source' is distinct from 'rendered_public_dom' then return jsonb_build_object('error','invalid_record'); end if;
 if not (s ?& array['platform','note_id','url','title','captured_at','published_at','author_display','like_count','collect_count','comment_count'])
 or jsonb_typeof(s->'author_display') not in ('string','null') or length(s->>'author_display')>100
 or jsonb_typeof(s->'published_at') not in ('string','null')
 or (s->>'published_at' is not null and s->>'published_at' !~ '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$')
 or e->>'parser_version' is null or e->>'parser_version' !~ '^4\.[0-9]+\.[0-9]+$'
 or jsonb_typeof(e->'original_length') is distinct from 'number' or coalesce(e->>'original_length','') !~ '^[0-9]{1,8}$'
 or jsonb_typeof(e->'truncated') is distinct from 'boolean'
 or jsonb_typeof(p_record->'extra'->'author_opinion_quotes') is distinct from 'array'
 then return jsonb_build_object('error','invalid_record'); end if;
 if (e->>'original_length')::int<length(e->>'text') or jsonb_array_length(p_record->'extra'->'author_opinion_quotes')>30
 or exists(select 1 from jsonb_array_elements(p_record->'extra'->'author_opinion_quotes') q where jsonb_typeof(q)<>'string' or strpos(e->>'text',q#>>'{}')=0)
 or exists(select 1 from jsonb_each(s) a(key,value) where key in ('like_count','collect_count','comment_count') and
   (jsonb_typeof(value) not in ('null','number') or (value<>'null'::jsonb and value::text !~ '^[0-9]{1,10}$')))
 then return jsonb_build_object('error','invalid_record'); end if;
 if exists(select 1 from jsonb_each(s) a(key,value) where key in ('like_count','collect_count','comment_count') and value<>'null'::jsonb and value::text::numeric>2147483647)
 then return jsonb_build_object('error','invalid_record'); end if;
 begin perform (s->>'published_at')::date; exception when others then return jsonb_build_object('error','invalid_published_date'); end;
 begin capture:=(s->>'captured_at')::timestamptz; exception when others then return jsonb_build_object('error','invalid_timestamp'); end;
 if capture is null or capture>now()+interval '5 minutes' or capture<now()-interval '24 hours' then return jsonb_build_object('error','invalid_timestamp'); end if;
 if not exists(select 1 from jsonb_array_elements_text(t.anchor_terms) a(term) where length(term)>=2 and
 strpos(lower(regexp_replace((s->>'title')||' '||(e->>'text'),'[[:space:][:punct:]]','','g')),lower(regexp_replace(term,'[[:space:][:punct:]]','','g')))>0)
 then return jsonb_build_object('error','unrelated_note'); end if;
 select count(*) into n from crowd_v4.proofs where user_id=u and received_at>=date_trunc('day',now() at time zone 'Asia/Shanghai') at time zone 'Asia/Shanghai';
 if n>=p.quota_day then return jsonb_build_object('error','daily_quota'); end if;
 insert into crowd_v4.proofs(note_id,user_id,task_id,record) values(s->>'note_id',u,p_task,p_record) on conflict(note_id) do nothing returning id into inserted_id;
 if inserted_id is not null then update crowd_v4.tasks set received=received+1 where id=p_task returning * into t; end if;
 result:=jsonb_build_object('inserted',inserted_id is not null,'duplicate',inserted_id is null,'task_received',t.received,'request',p_request,'gate','received');
 insert into crowd_v4.receipts(user_id,request,payload,result) values(u,p_request,payload,result);
 return result;
end $$;
create function public.crowd_v4_finish(p_task bigint,p_lease uuid) returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid:=auth.uid(); t crowd_v4.tasks;
begin
 if u is null then raise exception 'login_required' using errcode='42501'; end if;
 perform 1 from crowd_v4.participants where user_id=u and status='approved' for update;
 if not found then raise exception 'approval_required' using errcode='42501'; end if;
 select * into t from crowd_v4.tasks where id=p_task for update;
 if t.claimed_by is distinct from u or t.lease_token is distinct from p_lease or t.lease_until<now() then return jsonb_build_object('error','lease_lost'); end if;
 if t.status='leased' then update crowd_v4.tasks set status=case when received>=target then 'complete' else 'exhausted' end where id=p_task returning * into t; end if;
 return jsonb_build_object('status',t.status,'received',t.received);
end $$;
-- Service-only administrative control. All actions are audited; payments never rewritten.
create function public.crowd_v4_admin(p_action text,p_payload jsonb default '{}'::jsonb) returns jsonb language plpgsql security definer set search_path='' as $$
declare t crowd_v4.tasks; f crowd_v4.proofs; u uuid; n int; result jsonb; quote text; decision text;
begin
 if auth.role() is distinct from 'service_role' then raise exception 'service_only' using errcode='42501'; end if;
 if jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'invalid_payload'; end if;
 if p_action='publish' then
  if jsonb_array_length(p_payload->'anchor_terms')<1 or exists(select 1 from jsonb_array_elements_text(p_payload->'anchor_terms') a(term) where length(term) not between 2 and 120) then raise exception 'invalid_anchors'; end if;
  insert into crowd_v4.tasks(source_key,query,store_name,restaurant_id,anchor_terms,target) values(p_payload->>'source_key',p_payload->>'query',p_payload->>'store_name',
   (p_payload->>'restaurant_id')::bigint,p_payload->'anchor_terms',coalesce((p_payload->>'target')::int,5)) on conflict(source_key) do nothing;
  select * into t from crowd_v4.tasks where source_key=p_payload->>'source_key';
  if t.query is distinct from p_payload->>'query' or t.anchor_terms is distinct from p_payload->'anchor_terms' then raise exception 'source_key_reused'; end if;
  result:=to_jsonb(t);
 elsif p_action in ('approve','suspend') then
  update crowd_v4.participants set status=case when p_action='approve' then 'approved' else 'suspended' end,
   quota_day=coalesce((p_payload->>'quota_day')::int,quota_day) where user_id=(p_payload->>'user_id')::uuid;
  if not found then raise exception 'participant_not_found'; end if;
  result:=jsonb_build_object('updated',true);
 elsif p_action='review' then
  -- Lock order is participant -> proof, shared with submit/reward accounting.
  select user_id into u from crowd_v4.proofs where id=(p_payload->>'proof_id')::bigint;
  if u is null then raise exception 'proof_not_found'; end if;
  perform 1 from crowd_v4.participants where user_id=u for update;
  select * into f from crowd_v4.proofs where id=(p_payload->>'proof_id')::bigint for update;
  decision:=p_payload->>'decision'; quote:=p_payload->>'quote';
  if decision not in ('verified','rejected') or decision is null or length(coalesce(p_payload->>'reason',''))<8 then raise exception 'review_reason_required'; end if;
  if f.status<>'received' then
   if f.status<>decision then raise exception 'review_is_final'; end if;
   return jsonb_build_object('status',f.status,'replayed',true);
  end if;
  if decision='verified' and (p_payload->>'public_visible' is distinct from 'true' or p_payload->>'relevant' is distinct from 'true'
   or p_payload->>'personal_experience' is distinct from 'true' or length(coalesce(quote,''))<8 or strpos(f.record->'evidence'->>'text',quote)=0
   or (p_payload->>'source_checked_at')::timestamptz is null or (p_payload->>'source_checked_at')::timestamptz>now()+interval '5 minutes'
   or (p_payload->>'source_checked_at')::timestamptz<f.received_at-interval '5 minutes') then raise exception 'strict_evidence_gate'; end if;
  update crowd_v4.proofs set status=decision,reviewed_at=now(),review_note=p_payload->>'reason',verified_quote=case when decision='verified' then quote end,
   source_checked_at=case when decision='verified' then (p_payload->>'source_checked_at')::timestamptz end where id=f.id;
  if decision='verified' then
   update crowd_v4.participants set verified_count=verified_count+1 where user_id=u returning verified_count into n;
   if n%100=0 then insert into crowd_v4.rewards(user_id,batch_no) values(u,n/100) on conflict do nothing; end if;
  end if;
  result:=jsonb_build_object('status',decision);
 elsif p_action='pay' then
  if length(coalesce(p_payload->>'reference',''))<4 then raise exception 'payment_reference_required'; end if;
  update crowd_v4.rewards set paid_at=now(),payment_reference=p_payload->>'reference' where user_id=(p_payload->>'user_id')::uuid and batch_no=(p_payload->>'batch_no')::int and paid_at is null;
  if not found then
   if not exists(select 1 from crowd_v4.rewards where user_id=(p_payload->>'user_id')::uuid and batch_no=(p_payload->>'batch_no')::int and payment_reference=p_payload->>'reference') then raise exception 'payment_not_found_or_conflict'; end if;
  end if;
  result:=jsonb_build_object('paid',true);
 elsif p_action='list' then
  if p_payload->>'kind'='participants' then select coalesce(jsonb_agg(to_jsonb(p)),'[]') into result from (select * from crowd_v4.participants order by joined_at limit 200) p;
  elsif p_payload->>'kind'='rewards' then select coalesce(jsonb_agg(to_jsonb(r)),'[]') into result from (select * from crowd_v4.rewards where paid_at is null order by created_at limit 200) r;
  else select coalesce(jsonb_agg(to_jsonb(proof_row)),'[]') into result from (select * from crowd_v4.proofs where status='received' order by id limit 100) proof_row; end if;
 elsif p_action='export' then
  select coalesce(jsonb_agg(jsonb_build_object('proof_id',proof_row.id,'note_id',proof_row.note_id,'record',proof_row.record,'verified_quote',proof_row.verified_quote,
   'source_checked_at',proof_row.source_checked_at,'store_name',task_row.store_name,'restaurant_id',task_row.restaurant_id,'query',task_row.query)),'[]') into result
   from (select * from crowd_v4.proofs where status='verified' and id>coalesce((p_payload->>'after_id')::bigint,0)
    and id<=coalesce((p_payload->>'through_id')::bigint,9223372036854775807) order by id limit 200) proof_row
   join crowd_v4.tasks task_row on task_row.id=proof_row.task_id;
 else raise exception 'unknown_action';
 end if;
 if p_action not in ('list','export') then insert into crowd_v4.audit(action,payload) values(p_action,p_payload); end if;
 return result;
end $$;
revoke all on function public.crowd_v4_register(text), public.crowd_v4_status(), public.crowd_v4_claim(bigint), public.crowd_v4_submit(uuid,bigint,uuid,jsonb), public.crowd_v4_finish(bigint,uuid), public.crowd_v4_admin(text,jsonb) from public,anon,authenticated;
grant execute on function public.crowd_v4_register(text), public.crowd_v4_status(), public.crowd_v4_claim(bigint), public.crowd_v4_submit(uuid,bigint,uuid,jsonb), public.crowd_v4_finish(bigint,uuid) to authenticated;
grant execute on function public.crowd_v4_admin(text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
