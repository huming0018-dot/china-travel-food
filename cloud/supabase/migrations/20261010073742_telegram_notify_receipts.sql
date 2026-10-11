-- Notification-only capability; reuses the existing crowd_notify_tg relay.
-- Provision tg_notify_secret separately, never in source. Existing application
-- ops_secret remains compatible, but must not be copied to the watchdog.
begin;
create table if not exists public.telegram_notify_requests (
  request_id bigint primary key,
  created_at timestamptz not null default now()
);
alter table public.telegram_notify_requests enable row level security;
revoke all on public.telegram_notify_requests from public, anon, authenticated;

create or replace function public.telegram_notify_enqueue(p_text text, p_secret text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_secret text; v_ops text; v_result jsonb; v_id bigint;
begin
  select value into v_secret from public.crowd_private_config where key='tg_notify_secret';
  select value into v_ops from public.crowd_private_config where key='ops_secret';
  if coalesce(p_secret,'') = '' or
     (p_secret is distinct from v_secret and p_secret is distinct from v_ops) then
    return jsonb_build_object('ok',false,'reason','forbidden');
  end if;
  v_result := public.crowd_notify_tg(p_text, v_ops);
  if v_result->>'ok' = 'true' and v_result->>'request_id' is not null then
    v_id := (v_result->>'request_id')::bigint;
    insert into public.telegram_notify_requests(request_id) values(v_id);
    delete from public.telegram_notify_requests where created_at < now()-interval '1 day';
    return jsonb_build_object('ok',true,'request_id',v_id,'delivered',false);
  end if;
  return jsonb_build_object('ok',false,'reason','relay_rejected');
end $$;

create or replace function public.telegram_notify_receipt(p_request_id bigint, p_secret text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_secret text; v_ops text; v_response record; v_body jsonb;
begin
  select value into v_secret from public.crowd_private_config where key='tg_notify_secret';
  select value into v_ops from public.crowd_private_config where key='ops_secret';
  if coalesce(p_secret,'') = '' or
     (p_secret is distinct from v_secret and p_secret is distinct from v_ops) then
    return jsonb_build_object('delivered',false,'pending',false,'reason','forbidden');
  end if;
  if not exists(select 1 from public.telegram_notify_requests
                where request_id=p_request_id and created_at > now()-interval '1 day') then
    return jsonb_build_object('delivered',false,'pending',false,'reason','unknown_request');
  end if;
  select status_code, content, timed_out, error_msg into v_response
    from net._http_response where id=p_request_id;
  if not found then
    return jsonb_build_object('delivered',false,'pending',true);
  end if;
  if v_response.status_code=200 and not coalesce(v_response.timed_out,false)
     and v_response.error_msg is null then
    begin
      v_body := v_response.content::jsonb;
      return jsonb_build_object('delivered',coalesce(v_body->'ok'='true'::jsonb,false),
                               'pending',false);
    exception when invalid_text_representation then
      null;
    end;
  end if;
  return jsonb_build_object('delivered',false,'pending',false);
end $$;
revoke all on function public.telegram_notify_enqueue(text,text) from public;
revoke all on function public.telegram_notify_receipt(bigint,text) from public;
grant execute on function public.telegram_notify_enqueue(text,text) to anon, authenticated, service_role;
grant execute on function public.telegram_notify_receipt(bigint,text) to anon, authenticated, service_role;
commit;
