-- crowd_fix_v346_gcal_cloud.sql：Gmail 日历云端提醒（不依赖 Mac 开机）
-- 架构：pg_cron 每小时 :07 → gcal_remind_tick() 处理上一轮抓取的 ICS → 2h 内事件推 TG → 发起新一轮抓取
create extension if not exists pg_cron;

insert into public.crowd_private_config (key, value) values
  ('gcal_ics_url', 'https://calendar.google.com/calendar/ical/huming0018%40gmail.com/private-67e6caa3d6f8524dbf05dc2c9ce4891b/basic.ics'),
  ('gcal_last_resp_id', '0')
on conflict (key) do nothing;

create table if not exists public.gcal_remind_state (
  event_key text primary key,
  notified_at timestamptz not null default now()
);

create or replace function public.gcal_remind_tick()
returns jsonb language plpgsql security definer set search_path to 'public' as $f$
declare
  v_ics text; v_token text; v_chat text; v_last bigint := 0;
  v_resp record; v_line text; v_logical text := '';
  v_uid text; v_summary text; v_dts text; v_start timestamptz;
  v_key text; v_sent int := 0; v_upcoming int := 0; v_new_req bigint;
  v_now timestamptz := now();
  v_clean text;
begin
  select value into v_ics   from public.crowd_private_config where key='gcal_ics_url';
  select value into v_token from public.crowd_private_config where key='tg_bot_token';
  select value into v_chat  from public.crowd_private_config where key='tg_chat_id';
  select coalesce(value,'0')::bigint into v_last from public.crowd_private_config where key='gcal_last_resp_id';
  if v_ics is null or v_token is null or v_chat is null then
    return jsonb_build_object('ok', false, 'reason', 'not_configured');
  end if;

  -- ① 处理上一轮抓到的 ICS（最新一条 VCALENDAR 响应）
  select id, content into v_resp from net._http_response
   where id > v_last and status_code = 200 and content like 'BEGIN:VCALENDAR%'
   order by id desc limit 1;

  if found then
    v_last := v_resp.id;
    v_clean := replace(v_resp.content, E'\r\n', E'\n');
    for v_line in select unnest(string_to_array(v_clean, E'\n')) loop
      if v_line like ' %' or v_line like E'\t%' then
        v_logical := v_logical || substr(v_line, 2);  -- 折叠行续接
        continue;
      end if;
      -- 处理上一条逻辑行
      if v_logical = 'BEGIN:VEVENT' then
        v_uid := null; v_summary := null; v_dts := null;
      elsif v_logical like 'UID:%' then
        v_uid := substr(v_logical, 5);
      elsif v_logical like 'SUMMARY:%' then
        v_summary := substr(v_logical, 9);
      elsif v_logical like 'DTSTART%' then
        v_dts := v_logical;
      elsif v_logical = 'END:VEVENT' and v_dts is not null then
        -- 解析 DTSTART 三种形态
        v_start := null;
        if v_dts ~ '^DTSTART:\d{8}T\d{6}Z$' then
          v_start := (substr(v_dts, 9, 4) || '-' || substr(v_dts, 13, 2) || '-' || substr(v_dts, 15, 2)
                      || ' ' || substr(v_dts, 18, 2) || ':' || substr(v_dts, 20, 2) || ':' || substr(v_dts, 22, 2) || '+00')::timestamptz;
        elsif v_dts ~ '^DTSTART;TZID=[^:]+:\d{8}T\d{6}$' then
          declare tz text := substring(v_dts, '^DTSTART;TZID=([^:]+):'); ds text := right(v_dts, 15);
              off text := case tz when 'Asia/Tokyo' then '+09' when 'Asia/Shanghai' then '+08' when 'Asia/Taipei' then '+08' else '+00' end;
          begin
            v_start := (substr(ds,1,4)||'-'||substr(ds,5,2)||'-'||substr(ds,7,2)||' '||substr(ds,10,2)||':'||substr(ds,12,2)||':'||substr(ds,14,2)||off)::timestamptz;
          end;
        elsif v_dts ~ '^DTSTART;VALUE=DATE:\d{8}$' then
          declare ds text := right(v_dts, 8); begin
            v_start := (substr(ds,1,4)||'-'||substr(ds,5,2)||'-'||substr(ds,7,2)||' 00:00:00+08')::timestamptz; -- 全天事件按本地零点
          end;
        end if;
        if v_start is not null and v_start >= v_now and v_start <= v_now + interval '125 minutes' then
          v_upcoming := v_upcoming + 1;
          v_key := coalesce(v_uid, '?') || '|' || v_start::text;
          if not exists (select 1 from public.gcal_remind_state where event_key = v_key) then
            declare
              mins int := greatest(0, extract(epoch from (v_start - v_now))::int / 60);
              daylabel text := case when v_start::date = v_now::date then '今天'
                                    when v_start::date = (v_now + interval '1 day')::date then '明天'
                                    else to_char(v_start, 'MM月DD日') end;
              msg text := '⏰ 日程提醒：' || coalesce(nullif(v_summary,''), '(无标题)') || E'\n📅 '
                          || daylabel || ' ' || to_char(v_start at time zone 'Asia/Shanghai', 'HH24:MI')
                          || ' 开始（约 ' || mins || ' 分钟后）· Gmail 日历';
            begin
              perform net.http_post(
                url := 'https://api.telegram.org/bot' || v_token || '/sendMessage',
                body := jsonb_build_object('chat_id', v_chat, 'text', msg, 'disable_web_page_preview', true),
                headers := '{"Content-Type":"application/json"}'::jsonb);
              insert into public.gcal_remind_state (event_key) values (v_key) on conflict do nothing;
              v_sent := v_sent + 1;
            end;
          end if;
        end if;
      end if;
      v_logical := v_line;
    end loop;
    -- 清理 3 天前的提醒记录
    delete from public.gcal_remind_state where notified_at < now() - interval '3 days';
  end if;

  -- ② 发起下一轮抓取
  select net.http_get(v_ics) into v_new_req;

  insert into public.crowd_private_config (key, value) values ('gcal_last_resp_id', v_last::text)
    on conflict (key) do update set value = excluded.value;

  return jsonb_build_object('ok', true, 'processed_resp', coalesce(v_resp.id, 0),
                            'upcoming', v_upcoming, 'sent', v_sent, 'next_fetch', v_new_req);
end $f$;

revoke all on function public.gcal_remind_tick() from public, anon, authenticated;

-- 每小时 :07 跑一次（错开整点）
select cron.schedule('gcal-remind-hourly', '7 * * * *', 'select public.gcal_remind_tick()');
notify pgrst, 'reload schema';
