-- crowd_fix_v349_install_telemetry.sql：安装器遥测（定位"装不上"不再靠截图接力）
create table if not exists public.crowd_install_log (
  id bigint generated always as identity primary key,
  run_id text, step text, msg text,
  created_at timestamptz not null default now()
);
create index if not exists idx_install_log_run on public.crowd_install_log(run_id);

create or replace function public.crowd_install_report(p_run_id text, p_step text, p_msg text)
returns jsonb language plpgsql security definer set search_path to 'public' as $$
begin
  if length(coalesce(p_run_id,'')) > 60 or length(coalesce(p_step,'')) > 60 or length(coalesce(p_msg,'')) > 400 then
    return jsonb_build_object('ok', false, 'reason', 'too_long');
  end if;
  insert into public.crowd_install_log (run_id, step, msg) values (p_run_id, p_step, p_msg);
  return jsonb_build_object('ok', true);
end $$;
revoke all on function public.crowd_install_report(text, text, text) from public;
grant execute on function public.crowd_install_report(text, text, text) to anon, authenticated;
