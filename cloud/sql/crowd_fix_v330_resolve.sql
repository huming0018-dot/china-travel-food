-- crowd_fix_v330_resolve.sql — 短链服务端解析（2026-10-04）
-- 目的：手机端傻瓜式提交。参与者直接粘贴小红书分享文本/短链（xhslink.com），
--       服务端解析出规范 URL 与 note_id，客户端不再需要"先在浏览器打开"。
-- 安全：仅白名单域名（xhslink.com / xiaohongshu.com），防 SSRF 滥用。
-- 依赖：pg_net（Supabase 官方扩展）。幂等可重复执行。

create extension if not exists pg_net;

create or replace function public.crowd_resolve_link(p_input text)
returns jsonb
language plpgsql
security definer
set search_path to 'public'
set statement_timeout to '35s'  -- pg_net 跨境请求最多等 ~13s，函数级放宽（anon 角色默认太短）
as $$
declare
  v_url  text;
  v_id   text;
  v_req  bigint;
  v_res  record;
  v_loc  text;
  v_try  int;
  v_got  boolean := false;
begin
  -- 从任意粘贴文本中提取第一个 URL
  v_url := substring(p_input from 'https?://[^\s，。；、"''<>）)]+');
  if v_url is null then
    return jsonb_build_object('ok', false, 'reason', 'no_url');
  end if;

  -- 已是完整笔记链接：直接提取，不发请求
  v_id := substring(v_url from 'xiaohongshu\.com/(?:explore|discovery/item)/([0-9a-zA-Z]+)');
  if v_id is not null then
    return jsonb_build_object('ok', true, 'note_id', v_id, 'canonical_url', v_url, 'resolved', false);
  end if;

  -- 短链：仅放行 xhslink.com（白名单，防被当开放代理）
  if v_url !~ '^https?://(www\.)?xhslink\.(com|cn)/' then  -- v3.4.1：小红书 App 实际分享域名为 xhslink.cn
    return jsonb_build_object('ok', false, 'reason', 'unsupported_host');
  end if;

  -- pg_net 默认不跟随 302：拿 Location 头即为规范链接
  select net.http_get(v_url, '{}'::jsonb, '{}'::jsonb, 6000) into v_req;
  -- 注意：不能用 FOUND 判断（perform pg_sleep 会污染 FOUND），用显式布尔标志
  for v_try in 1..40 loop  -- 10s 上限：短链走 JS 挑战时等再久也没用，快速失败让客户端降级
    select status_code, headers into v_res from net._http_response where id = v_req;
    if found then v_got := true; exit; end if;
    perform pg_sleep(0.25);
  end loop;
  if not v_got then
    return jsonb_build_object('ok', false, 'reason', 'resolve_timeout');
  end if;

  v_loc := coalesce(v_res.headers->>'location', v_res.headers->>'Location');
  if v_loc is null then
    return jsonb_build_object('ok', false, 'reason', 'no_redirect', 'http_status', v_res.status_code);
  end if;

  v_id := substring(v_loc from '(?:explore|discovery/item)/([0-9a-zA-Z]+)');
  if v_id is null then
    return jsonb_build_object('ok', false, 'reason', 'no_note_id', 'final_url', left(v_loc, 200));
  end if;

  return jsonb_build_object('ok', true, 'note_id', v_id, 'canonical_url', v_loc, 'resolved', true);
end;
$$;

revoke all on function public.crowd_resolve_link(text) from public;
grant execute on function public.crowd_resolve_link(text) to anon, authenticated;
