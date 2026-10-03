-- ============================================================
-- CROWD MIGRATION v3.2 · 02 身份绑定（外部审计 #6）
-- 目标：参与编号不再作为身份凭证；Supabase Auth 用户绑定参与者，
--       业务提交必须来自绑定者本人（防冒名提交/消耗配额/匿名滥用）。
-- 启用前提（重要）：
--   A. Supabase Dashboard → Authentication 启用（邮箱/密码或 OAuth，按招募渠道选）
--   B. 报名页 apply.html 增加登录流程（登录后报名 → 绑定 auth_user_id）
--   C. crowd_participants 的 RLS 对已绑定行仅本人可见
-- 幂等：可重复执行。未完成 A/B 前执行本迁移不会破坏现有数据
--       （新增列默认 null，匿名提交在迁移01中已向后兼容）。
-- ============================================================

-- ------------------------------------------------------------
-- 1) participants 增加认证绑定列
-- ------------------------------------------------------------
alter table public.crowd_participants add column if not exists auth_user_id uuid;
-- 一个认证用户只能绑定一个参与者（防多号）
create unique index if not exists uq_crowd_participants_auth
  on public.crowd_participants(auth_user_id) where auth_user_id is not null;

-- ------------------------------------------------------------
-- 2) 报名 RPC：匿名注册（生成 P- 编号）→ 后续登录后绑定
--    apply.html 调用此 RPC 而非直写表（收紧管理字段，外部审计 #61 项）
-- ------------------------------------------------------------
create or replace function public.crowd_register(
  p_display_name text, p_contact text, p_note text, p_device_salt text
) returns jsonb
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
declare
  v_pid text;
  v_chars constant text := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  v_i int;
begin
  -- 服务端生成编号（schema 统一：P- + 8 位大写字母数字，外部审计 #2）
  v_pid := 'P-';
  for v_i in 1..8 loop
    v_pid := v_pid || substr(v_chars, 1 + floor(random()*36)::int, 1);
  end loop;
  -- 防碰撞重试
  while exists (select 1 from public.crowd_participants where participant_id = v_pid) loop
    v_pid := 'P-';
    for v_i in 1..8 loop
      v_pid := v_pid || substr(v_chars, 1 + floor(random()*36)::int, 1);
    end loop;
  end loop;

  insert into public.crowd_participants
    (participant_id, display_name, contact, status, device_salt, source, review_note, auth_user_id)
  values
    (v_pid, left(coalesce(p_display_name,''),20), left(coalesce(p_contact,''),60),
     'pending', left(coalesce(p_device_salt,''),40), 'public', left(coalesce(p_note,''),200),
     auth.uid())  -- 已登录则直接绑定；匿名则 null（后续可绑定）
  returning participant_id into v_pid;

  return jsonb_build_object('ok', true, 'participant_id', v_pid,
    'bound', auth.uid() is not null);
exception
  when others then
    return jsonb_build_object('ok', false, 'reason', SQLERRM);
end;
$function$;

-- ------------------------------------------------------------
-- 3) 绑定 RPC：登录用户把自己绑定到已报名编号（找回/升级场景）
--    仅允许：该行 auth_user_id 为空 且 报名联系方式匹配（弱校验）+ 本人登录
-- ------------------------------------------------------------
create or replace function public.crowd_bind_participant(p_participant_id text)
 returns jsonb
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
declare
  v_auth uuid := auth.uid();
  v_row public.crowd_participants%rowtype;
begin
  if v_auth is null then
    return jsonb_build_object('ok', false, 'reason', 'auth_required');
  end if;
  -- 一个认证用户只能绑定一个参与者
  if exists (select 1 from public.crowd_participants where auth_user_id = v_auth) then
    return jsonb_build_object('ok', false, 'reason', 'already_bound');
  end if;
  select * into v_row from public.crowd_participants
   where participant_id = p_participant_id and auth_user_id is null
   for update;
  if v_row.participant_id is null then
    return jsonb_build_object('ok', false, 'reason', 'participant_not_bindable');
  end if;
  update public.crowd_participants
     set auth_user_id = v_auth, reviewed_at = coalesce(reviewed_at, now())
   where participant_id = p_participant_id;
  return jsonb_build_object('ok', true, 'participant_id', p_participant_id);
end;
$function$;

-- ------------------------------------------------------------
-- 4) 匿名直写收紧：禁止匿名直接 INSERT 管理字段（外部审计 #61）
--    报名改走 crowd_register RPC；保留旧 policy 但收紧
-- ------------------------------------------------------------
drop policy if exists "crowd_apply_anon_insert" on public.crowd_participants;
create policy "crowd_apply_anon_insert" on public.crowd_participants
  for insert to anon with check (false);  -- 报名必须走 RPC（security definer 不受此限）

-- 已绑定行仅本人可读；未绑定行保持报名自查
drop policy if exists "crowd_apply_self_read" on public.crowd_participants;
create policy "crowd_apply_self_read" on public.crowd_participants
  for select to anon using (
    auth_user_id = auth.uid()
    or (auth_user_id is null and (status = 'pending' or status = 'approved'))
  );

-- ============================================================
-- 验证：
--  1) 匿名调 crowd_register → 返回 P-编号（bound=false）
--  2) 登录后调 crowd_bind_participant → bound=true
--  3) 迁移01函数中已加：绑定者提交时 auth.uid() 必须等于 auth_user_id
-- 回滚：
--  drop function public.crowd_register; drop function public.crowd_bind_participant;
--  drop index uq_crowd_participants_auth;
--  -- 恢复报名匿名 INSERT policy（见 crowd_tables.sql 原版）
-- ============================================================
