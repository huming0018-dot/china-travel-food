begin;
-- Backward-compatible, optional navigation diagnostics. No new data access.
create or replace function public.crowd_v4_diagnostics(p_action text,p_revision bigint,p_state jsonb default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare u uuid:=auth.uid(); p crowd_v4.participants; d crowd_v4.diagnostics; stamp timestamptz:=now(); field text;
begin
 if u is null then raise exception 'login_required' using errcode='42501'; end if;
 select * into p from crowd_v4.participants where user_id=u for update;
 if p.user_id is null or p.consent<>'crowd-public-v4' then raise exception 'approval_required' using errcode='42501'; end if;
 if p_revision is null or p_revision<1 or p_revision>9007199254740991 or p_action is null or p_action not in ('enable','disable','report') then raise exception 'invalid_diagnostics'; end if;
 select * into d from crowd_v4.diagnostics where user_id=u;
 if p_action in ('enable','disable') then
  if p_state is not null then raise exception 'invalid_diagnostics'; end if;
  if p_action='enable' and p.status<>'approved' then raise exception 'approval_required' using errcode='42501'; end if;
  if d.user_id is not null and (p_revision<d.revision or (p_revision=d.revision and d.enabled is distinct from (p_action='enable'))) then raise exception 'stale_diagnostics'; end if;
  insert into crowd_v4.diagnostics(user_id,enabled,revision,state,updated_at) values(u,p_action='enable',p_revision,null,stamp)
  on conflict(user_id) do update set enabled=excluded.enabled,revision=excluded.revision,
    state=case when excluded.enabled then crowd_v4.diagnostics.state else null end,updated_at=stamp;
  return jsonb_build_object('enabled',p_action='enable','cleared',p_action='disable');
 end if;
 if d.user_id is null or not d.enabled or d.revision<>p_revision then raise exception 'stale_diagnostics'; end if;
 if p.status<>'approved' then raise exception 'approval_required' using errcode='42501'; end if;
 if jsonb_typeof(p_state) is distinct from 'object' or octet_length(p_state::text)>2048
 or not (p_state ?& array['version','enabled','phase','error','task_id','queued','rejected','page_kind','tab_status','document','gate','links','search_note_links','body_chars','visible'])
 or exists(select 1 from jsonb_object_keys(p_state) k where k<>all(array['version','enabled','phase','error','task_id','queued','rejected','page_kind','tab_status','document','gate','links','search_note_links','body_chars','visible','nav_stage','nav_error','nav_age_s','probe_status']))
 or jsonb_typeof(p_state->'version') is distinct from 'string' or coalesce(p_state->>'version','') !~ '^4\.[0-9]{1,3}\.[0-9]{1,3}$'
 or jsonb_typeof(p_state->'enabled') is distinct from 'boolean'
 or coalesce(p_state->>'phase','') not in ('idle','search','search_done','note','reopen_note')
 or coalesce(p_state->>'page_kind','') not in ('search','note','other','unknown','missing')
 or coalesce(p_state->>'tab_status','') not in ('loading','complete','discarded','missing','no_content')
 or coalesce(p_state->>'document','') not in ('loading','interactive','complete','unknown')
 or jsonb_typeof(p_state->'visible') not in ('boolean','null')
 or jsonb_typeof(p_state->'error') not in ('string','null')
 or (p_state->>'error' is not null and p_state->>'error' not in ('page_timeout','page_loading','content_unavailable','probe_timeout','page_mismatch','wrong_note','login_required','captcha','rate_limit','approval_required','consent_required','user_stopped','logged_out','system_suspended','lease_lost','daily_quota','review_local_rejections','backend_unavailable','unexpected_error'))
 or jsonb_typeof(p_state->'gate') not in ('string','null')
 or (p_state->>'gate' is not null and p_state->>'gate' not in ('login_required','captcha','rate_limit'))
 or jsonb_typeof(p_state->'task_id') not in ('number','null')
 or (p_state->>'task_id' is not null and coalesce(p_state->>'task_id','') !~ '^[1-9][0-9]{0,15}$')
 then raise exception 'invalid_diagnostics'; end if;
 if (p_state ? 'nav_stage' and (jsonb_typeof(p_state->'nav_stage') is distinct from 'string' or coalesce(p_state->>'nav_stage','') not in ('unknown','started','committed','dom_ready','complete','failed')))
 or (p_state ? 'probe_status' and (jsonb_typeof(p_state->'probe_status') is distinct from 'string' or coalesce(p_state->>'probe_status','') not in ('unknown','ok','no_receiver','timed_out')))
 or (p_state ? 'nav_error' and (jsonb_typeof(p_state->'nav_error') not in ('string','null') or (p_state->>'nav_error' is not null and p_state->>'nav_error' not in ('ERR_NAME_NOT_RESOLVED','ERR_INTERNET_DISCONNECTED','ERR_CONNECTION_TIMED_OUT','ERR_TIMED_OUT','ERR_CONNECTION_RESET','ERR_CONNECTION_REFUSED','ERR_CONNECTION_CLOSED','ERR_ADDRESS_UNREACHABLE','ERR_NETWORK_CHANGED','ERR_TUNNEL_CONNECTION_FAILED','ERR_PROXY_CONNECTION_FAILED','ERR_CERT_AUTHORITY_INVALID','ERR_CERT_DATE_INVALID','ERR_SSL_PROTOCOL_ERROR','ERR_BLOCKED_BY_CLIENT','ERR_BLOCKED_BY_ADMINISTRATOR','ERR_ABORTED','OTHER'))))
 or (p_state ? 'nav_age_s' and jsonb_typeof(p_state->'nav_age_s') <> 'null' and (jsonb_typeof(p_state->'nav_age_s') is distinct from 'number' or coalesce(p_state->>'nav_age_s','') !~ '^[0-9]{1,5}$'))
 then raise exception 'invalid_diagnostics'; end if;
 if p_state->>'nav_age_s' is not null and (p_state->>'nav_age_s')::int > 86400 then raise exception 'invalid_diagnostics'; end if;
 foreach field in array array['queued','rejected','links','search_note_links','body_chars'] loop
  if jsonb_typeof(p_state->field) is distinct from 'number' or coalesce(p_state->>field,'') !~ '^[0-9]{1,5}$' then raise exception 'invalid_diagnostics'; end if;
 end loop;
 if (p_state->>'links')::int>500 or (p_state->>'search_note_links')::int>500 or (p_state->>'body_chars')::int>24000 then raise exception 'invalid_diagnostics'; end if;
 update crowd_v4.diagnostics set state=p_state,updated_at=stamp where user_id=u;
 return jsonb_build_object('saved_at',stamp);
end $$;
revoke all on function public.crowd_v4_diagnostics(text,bigint,jsonb) from public, anon;
grant execute on function public.crowd_v4_diagnostics(text,bigint,jsonb) to authenticated;
commit;
