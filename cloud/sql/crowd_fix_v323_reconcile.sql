-- ============================================================
-- crowd_fix_v323_reconcile.sql — v3.2.3  reconcile 服务端修复迁移
-- PM 窗口 · 2026-10-03 · 在 Supabase SQL Editor / Management API 执行
-- 线上项目：bdwrhshgdeghgyzwpxnl（已有真实参与者在使用，如 P-B269XL1K，task#10 已 fulfilled）
--
-- 【与上一版（已删除的 crowd_fix_v311.sql）的根本区别】
--   v311 假设可以新建一个 _v3 后缀的提交函数并吊销旧函数授权；v3.2.3 交接确认
--   线上已应用 crowd_migration_v3.2_01_evidence.sql（本仓库缺该文件，只有行为描述），
--   且真实插件正在以 RPC 名 crowd_submit_proof 持续调用。因此本文件：
--     - 保持 RPC 函数名 crowd_submit_proof(p_participant_id text, p_envelope jsonb) 不变，
--       用 CREATE OR REPLACE 原地合并升级，不吊销、不改名、不新建后缀函数；
--     - 不 revoke crowd_submit_proof 的任何现有授权（详见 S6 注释）；
--     - 全部语句幂等可重复执行（IF EXISTS / IF NOT EXISTS / DO 块守卫 / 确定性回灌）。
--
-- 【执行前提】以下事实已经 service_role 只读查询实测（2026-10-03 20:50），
--   本文件对实测 schema 全部兼容，只做守卫式补齐：
--   v3.1.0 四个 SQL（建表/权限/红队/提交函数 v2，同上一版所列）已应用；
--   v3.2 迁移 crowd_migration_v3.2_01_evidence.sql（本仓库缺）已应用，实测结果：
--     · crowd_tasks 已含 claimed_at / claimed_by / lease_duration_min(=1440) /
--       lease_until / kw_progress(jsonb) 列——租约列已存在，认领写 lease 见 S5；
--     · crowd_tasks.pack 是 jsonb 标准数组（双引号），如
--       ["源深路烧烤", "福和面馆（...）", ...]——2026-10-03 pg_typeof + pack::text
--       实测证伪了此前"repr 单引号串"的误判（那是终端 Python 打印 json 数组的
--       显示假象）。所有 pack 读操作一律用 jsonb 数组运算（? 成员校验 /
--       jsonb_array_elements_text 枚举），并以 jsonb_typeof='array' 防御历史脏行；
--     · crowd_tasks.kw_progress 存量恒为 {}（连 fulfilled 的 task#10 也是空对象），
--       线上函数实际未维护——形状由本文件定义：{关键词: accepted数} jsonb 对象；
--     · crowd_proofs.dedupe_key 存量为 32 位 MD5（旧标题哈希），S2 回灌适用；
--       smoke 行 note_id 以 aaaa/bbbb 开头，属测试数据，照常回灌；
--     · 线上已有 crowd_bind_participant 函数（v3.2.3 旧插件注册入口）——本文件
--       不触碰；v3.2.3 旧插件走 bind、v3.3.0 新插件走 crowd_register_participant，
--       两者产出编号格式并存兼容（bind 产出的 P-B269XL1K 为 8 位大写）；
--     · 存量参与者编号含连字符测试行（P-RED-*/P-RACE-*/P-TEST-*），说明线上对
--       participant_id 无 CHECK 约束——本文件不为编号加任何 CHECK，以免误伤存量行；
--     · crowd_store_evidence / crowd_store_candidates / crowd_settle 一律不触碰。
--
-- 【回滚纲要】见文件尾注释（不自动执行）。核心：本文件全部 CREATE OR REPLACE /
--   IF NOT EXISTS，回滚 = 用执行前备份的函数定义覆盖回去；新增表/列按需保留或删除。
--   ★ 执行前必做备份（v3.2 迁移文件本仓库缺失，函数定义只能从线上现取）：
--     select pg_get_functiondef('public.crowd_submit_proof(text,jsonb)'::regprocedure);
--     select pg_get_functiondef('public.crowd_bind_participant'::regprocedure);  -- 旧插件入口，备份备查
--     select pg_get_functiondef('public.crowd_register_participant(text,text,text,text)'::regprocedure); -- 若已存在
--   将输出存档后再执行本文件。
-- ============================================================


-- ------------------------------------------------------------
-- S0) claimed_by 防御式补列
--     实测（2026-10-03）crowd_tasks 已含 claimed_by / claimed_at /
--     lease_duration_min / lease_until / kw_progress——本块预期命中"跳过"分支；
--     保留 DO 块守卫是为了本文件在缺列的纯 v3.1.0 基线环境也能自保。
--     不加外键：存量 claimed_by 值无法逐一核对，加 FK 可能直接失败；
--     引用完整性留给下一阶段任务租约回收（见文件尾路线图）。
-- ------------------------------------------------------------
do $$
begin
  if not exists (select 1
                   from information_schema.columns
                  where table_schema = 'public'
                    and table_name   = 'crowd_tasks'
                    and column_name  = 'claimed_by') then
    alter table public.crowd_tasks add column claimed_by text;
    raise notice 'crowd_fix_v323: crowd_tasks.claimed_by added';
  else
    raise notice 'crowd_fix_v323: crowd_tasks.claimed_by already exists, skipped';
  end if;
end $$;


-- ------------------------------------------------------------
-- S1) crowd_register_participant —— 编号生成对齐线上惯例 + device_salt 幂等恢复
--     变更点（相对仓库内上一版设计）：
--       - 编号改为 'P-' + 8 位大写字母数字（对齐线上真实编号 P-B269XL1K 的惯例；
--         契约校验口径放宽为 6–12 位，见 CROWD_CONTRACT.md）；
--       - 签名 (p_display_name text default null, p_contact text default null,
--                p_device_salt text, p_source text default 'extension')：
--         display_name/contact 改为可选（插件内「我要加入」一键报名场景）；
--       - device_salt 幂等恢复：同设备已有 pending/approved 参与者时不报错，
--         直接返回 {ok:true, participant_id:<已有>, reused:true}
--         （解决重装/换浏览器恢复编号）；新注册返回 reused:false；
--       - 撤销 anon 对 crowd_participants 直接 INSERT 的逻辑保留（下方 drop policy /
--         revoke 与上一版一致，幂等）。
-- ------------------------------------------------------------
create or replace function public.crowd_register_participant(
  p_display_name text default null,
  p_contact      text default null,
  p_device_salt  text default null,
  p_source       text default 'extension'
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id              text;
  v_source          text;
  v_constraint      text;
  v_attempt         int;
  v_existing_id     text;
  v_existing_status text;
  v_display         text;
  v_contact         text;
begin
  -- device_salt 必填（R1 一机一号辅助风控信号；只是辅助信号，
  -- 不构成设备/账号唯一性证明，主要控制留给身份与审核流程）
  if p_device_salt is null or p_device_salt !~ '^[A-Za-z0-9\-]{8,64}$' then
    return jsonb_build_object('ok', false, 'reason', 'device_salt_invalid');
  end if;

  -- display_name / contact 可选；提供时沿用注入字符与长度校验
  if p_display_name is not null
     and (length(p_display_name) > 20
          or position('<' in p_display_name) > 0
          or position('>' in p_display_name) > 0) then
    return jsonb_build_object('ok', false, 'reason', 'display_name_invalid');
  end if;
  if p_contact is not null
     and (length(p_contact) > 100
          or position('<' in p_contact) > 0
          or position('>' in p_contact) > 0) then
    return jsonb_build_object('ok', false, 'reason', 'contact_invalid');
  end if;

  -- device_salt 幂等恢复（先于编号生成）：同设备已有 active 参与者 → 返还原编号。
  -- 与 idx_crowd_participants_salt_active 部分唯一索引同口径（pending/approved）。
  select participant_id, status
    into v_existing_id, v_existing_status
    from public.crowd_participants
   where device_salt = p_device_salt
     and status in ('pending', 'approved')
   order by applied_at
   limit 1;
  if v_existing_id is not null then
    return jsonb_build_object(
      'ok', true,
      'participant_id', v_existing_id,
      'reused', true,
      'status', v_existing_status
    );
  end if;

  -- source 白名单外一律收敛为服务端默认值（客户端传入的管理语义字段不采纳）
  v_source := case
                when p_source in ('extension', 'public', 'referral', 'crew')
                  then p_source
                else 'extension'
              end;
  v_display := nullif(btrim(coalesce(p_display_name, '')), '');
  v_contact := coalesce(nullif(btrim(coalesce(p_contact, '')), ''), '');

  -- 服务端生成编号：P- + 8 位大写字母数字；主键撞号重试，最多 20 次
  for v_attempt in 1..20 loop
    v_id := 'P-' || (
      select string_agg(
               substr('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                      (floor(random() * 36) + 1)::int, 1), '')
        from generate_series(1, 8)
    );
    begin
      insert into public.crowd_participants
        (participant_id, display_name, contact, device_salt, source)
      values
        (v_id, coalesce(v_display, v_id), v_contact, p_device_salt, v_source);
      -- status/quota_day 等由列默认值落定（pending / 20），此处不显式赋值
      return jsonb_build_object(
        'ok', true,
        'participant_id', v_id,
        'reused', false,
        'status', 'pending',
        'quota_day', 20
      );
    exception
      when unique_violation then
        get stacked diagnostics v_constraint = constraint_name;
        -- 并发下同设备抢先注册成功（R1 部分唯一索引）→ 按幂等恢复口径返回已有编号
        if v_constraint = 'idx_crowd_participants_salt_active' then
          select participant_id, status
            into v_existing_id, v_existing_status
            from public.crowd_participants
           where device_salt = p_device_salt
             and status in ('pending', 'approved')
           order by applied_at
           limit 1;
          if v_existing_id is not null then
            return jsonb_build_object(
              'ok', true,
              'participant_id', v_existing_id,
              'reused', true,
              'status', v_existing_status
            );
          end if;
          return jsonb_build_object('ok', false, 'reason', 'device_already_registered');
        end if;
        -- 其余唯一冲突即编号撞号（crowd_participants_pkey）→ 继续重试
    end;
  end loop;
  return jsonb_build_object('ok', false, 'reason', 'id_generation_retry_exhausted');
end;
$$;

revoke all on function public.crowd_register_participant(text, text, text, text) from public;
grant execute on function public.crowd_register_participant(text, text, text, text)
  to anon, authenticated, service_role;

-- 撤销 anon 对 crowd_participants 的直接 INSERT 策略（保留上一版结论：
-- 报名必须走 crowd_register_participant，客户端不得直写编号与管理字段）。
drop policy if exists "crowd_apply_anon_insert" on public.crowd_participants;
revoke insert on public.crowd_participants from anon;


-- ------------------------------------------------------------
-- S2) 笔记唯一身份 = platform + note_id（沿用上一版 S2 设计，守卫式补齐）
--     - crowd_proofs 补 platform / gate_reason / submission_id / quality_flags 列
--     - 重建 gate_status CHECK（允许 accepted/rejected/duplicate/duplicate_skipped/error；
--       线上 v3.2 已把 unique 冲突捕获为 duplicate_skipped，约束必须容纳该值）
--     - dedupe_key 口径迁移：note → platform:note_id；
--       rating → platform:note_id:rating:participant_id（保留每人每笔记一评）
--     - 存量 accepted 冲突行降级为 duplicate 后，再建新的部分唯一索引
--     幂等：回灌与降级均为确定性更新，重复执行收敛不变。
--     注意：线上 proofs 含 smoke 测试数据（note_id 以 aaaa/bbbb 开头），
--     回灌只改 dedupe_key 口径，不删除、不改 gate_status（无冲突行时降级语句自然空转）。
-- ------------------------------------------------------------
alter table public.crowd_proofs add column if not exists platform text not null default 'xiaohongshu';
alter table public.crowd_proofs add column if not exists gate_reason text;
alter table public.crowd_proofs add column if not exists submission_id uuid;
alter table public.crowd_proofs add column if not exists quality_flags jsonb not null default '{}'::jsonb;

-- 存量归一化（2026-10-03 实测：线上有 9 行 gate_status='task_closed'，新 CHECK 不含它）。
-- 凡不在新枚举内的存量值一律归到 rejected，原值保留进 gate_reason 以便追溯。
-- 语义：task_closed 本质是"任务已关闭导致的拒收"，归 rejected 与 v3 裁决口径一致。
update public.crowd_proofs
   set gate_reason = coalesce(gate_reason, '') || case when gate_reason is null then '' else ';' end
                     || 'legacy:' || gate_status,
       gate_status = 'rejected'
 where gate_status not in ('accepted', 'rejected', 'duplicate', 'duplicate_skipped', 'error');

-- gate_status CHECK 重建（DO 块先查再删：凡涉及 gate_status 的 CHECK 一律清掉，
-- 再建唯一权威定义；重复执行时删掉自己上次建的约束再重建，终态一致）
do $$
declare r record;
begin
  for r in select oid, conname
             from pg_constraint
            where conrelid = 'public.crowd_proofs'::regclass
              and contype = 'check'
              and pg_get_constraintdef(oid) ilike '%gate_status%'
  loop
    execute format('alter table public.crowd_proofs drop constraint %I', r.conname);
  end loop;
end $$;
alter table public.crowd_proofs
  add constraint crowd_proofs_gate_status_check
  check (gate_status in ('accepted', 'rejected', 'duplicate', 'duplicate_skipped', 'error'));

-- 存量 dedupe_key 迁移到新口径（确定性回灌，重复执行结果不变）
update public.crowd_proofs
   set dedupe_key = case
                      when kind = 'rating'
                        then platform || ':' || note_id || ':rating:' || participant_id
                      else platform || ':' || note_id
                    end;

-- 存量 accepted 去重冲突降级：同 platform+note_id 的 note 只保留最早一条；
-- 同参与者同 platform+note_id 的 rating 只保留最早一条（幂等：再执行无可降级行）
update public.crowd_proofs p
   set gate_status = 'duplicate', gate_reason = 'v323_backfill_dedupe'
 where p.gate_status = 'accepted'
   and p.kind = 'note'
   and exists (select 1
                 from public.crowd_proofs q
                where q.kind = 'note'
                  and q.gate_status = 'accepted'
                  and q.platform = p.platform
                  and q.note_id = p.note_id
                  and q.id < p.id);
update public.crowd_proofs p
   set gate_status = 'duplicate', gate_reason = 'v323_backfill_dedupe'
 where p.gate_status = 'accepted'
   and p.kind = 'rating'
   and exists (select 1
                 from public.crowd_proofs q
                where q.kind = 'rating'
                  and q.gate_status = 'accepted'
                  and q.platform = p.platform
                  and q.note_id = p.note_id
                  and q.participant_id = p.participant_id
                  and q.id < p.id);

-- 旧口径去重索引清理（凡建在 dedupe_key 上的唯一索引一律移除，新口径索引除外）
do $$
declare r record;
begin
  for r in select indexname
             from pg_indexes
            where schemaname = 'public'
              and tablename = 'crowd_proofs'
              and indexdef ilike '%unique%'
              and indexdef ilike '%dedupe_key%'
              and indexname <> 'idx_crowd_proofs_dedupe_note'
  loop
    execute format('drop index if exists public.%I', r.indexname);
  end loop;
end $$;
drop index if exists idx_crowd_proofs_dedupe;
drop index if exists idx_crowd_proofs_dedupe_title;

-- 新唯一索引：accepted 态 dedupe_key 唯一（并发绕过由唯一索引兜底 → duplicate_skipped）
create unique index if not exists idx_crowd_proofs_dedupe_note
  on public.crowd_proofs(dedupe_key) where gate_status = 'accepted';
-- 锚定/查重辅助索引
create index if not exists idx_crowd_proofs_platform_note
  on public.crowd_proofs(platform, note_id);


-- ------------------------------------------------------------
-- S3) 提交幂等回执表 crowd_submissions（守卫式创建）
--     每个 submission_id 处理一次，原始响应整份落库；重试/断网重传直接重放。
--     participant_id 不设外键：闸门失败（未知编号）也必须能落回执。
--     线上若已被 v3.2 迁移建过同名同构表，create if not exists 自然跳过。
-- ------------------------------------------------------------
create table if not exists public.crowd_submissions (
  submission_id  uuid primary key,
  participant_id text not null,
  task_id        bigint,
  sync_version   int,
  item_count     int  not null default 0,
  accepted_count int  not null default 0,
  response       jsonb not null,
  created_at     timestamptz not null default now()
);
alter table public.crowd_submissions enable row level security;
revoke all on public.crowd_submissions from anon, authenticated;


-- ------------------------------------------------------------
-- S4) 逐条裁决事实表 / 关键词进度表（守卫式创建 + 存量回灌）
--     crowd_proof_verdicts：每条 proof 的裁决事实，拒收率统计唯一数据源；
--       reason_category 区分 duplicate/quality/task/quota/system，
--       仅 quality 计入参与者拒收率（系统原因不计）。
--     crowd_task_keyword_progress：任务 × 关键词 accepted 累计，
--       完成标准（每关键词 >= kpi_min）与 keyword_progress 响应的数据源。
-- ------------------------------------------------------------
create table if not exists public.crowd_proof_verdicts (
  id                bigint generated always as identity primary key,
  submission_id     uuid not null references public.crowd_submissions(submission_id),
  participant_id    text not null,
  task_id           bigint,
  item_index        int  not null,
  note_id           text,
  verdict           text not null
                    check (verdict in ('accepted', 'duplicate', 'rejected', 'error')),
  reason            text,
  reason_category   text not null default 'none'
                    check (reason_category in ('none', 'duplicate', 'quality', 'task', 'quota', 'system')),
  counts_for_reject boolean not null default false,
  detail            text,
  created_at        timestamptz not null default now(),
  unique (submission_id, item_index)
);
create index if not exists idx_crowd_verdicts_pid on public.crowd_proof_verdicts(participant_id);
alter table public.crowd_proof_verdicts enable row level security;
revoke all on public.crowd_proof_verdicts from anon, authenticated;

create table if not exists public.crowd_task_keyword_progress (
  task_id    bigint not null references public.crowd_tasks(task_id),
  keyword    text not null,
  accepted   int  not null default 0,
  updated_at timestamptz not null default now(),
  primary key (task_id, keyword)
);
alter table public.crowd_task_keyword_progress enable row level security;
revoke all on public.crowd_task_keyword_progress from anon, authenticated;

-- 存量回灌：用历史 accepted 行的 raw_query 回填关键词进度
-- （pack 实测为 jsonb 标准数组（双引号）：成员判定用 ? 运算符，并以
--   jsonb_typeof='array' 防御历史脏行（非数组行不回灌）。
--   幂等：on conflict do nothing，只补缺、不覆盖现值；此前文本匹配版本
--   导致回灌空转，重新执行本文件即可正确补齐）
insert into public.crowd_task_keyword_progress (task_id, keyword, accepted)
select p.task_id, p.raw_query, count(*)
  from public.crowd_proofs p
  join public.crowd_tasks t on t.task_id = p.task_id
 where p.gate_status = 'accepted'
   and p.raw_query is not null
   and p.raw_query <> ''
   and jsonb_typeof(t.pack) = 'array'
   and t.pack ? p.raw_query
 group by p.task_id, p.raw_query
on conflict (task_id, keyword) do nothing;


-- ------------------------------------------------------------
-- S5) CREATE OR REPLACE crowd_submit_proof —— 原地合并升级（本文件核心）
--     函数名与参数名 p_participant_id / p_envelope 保持不变（线上 v3.2.3 插件
--     按此调用）；v311 的"新建后缀函数 + 吊销旧函数"方案废弃。
--
--     合并口径（已按线上实测 schema 修订）：
--       保留线上 v3.2 已修复行为：
--         · 任务闸门：open 或 (in_progress 且 claimed_by=本人)，函数入口与逐条循环内
--           同一口径（v3.2 根因即循环内漏改，此处两处都写全）
--         · open 任务首个 accepted 提交认领：status='in_progress'、claimed_by=本人、
--           claimed_at=now()、lease_until=now()+make_interval(mins=>coalesce(
--           lease_duration_min,1440))——租约列线上实测已存在；lease 过期回收
--           （到期自动回 open）属下一阶段，本文件不实现，见文件尾路线图
--         · kw_progress 并发安全：逐条裁决后 SELECT ... FOR UPDATE 锁任务行重读
--         · progress = progress + n 原子增量
--         · unique 索引冲突捕获为 duplicate_skipped
--       并入 v311 设计：
--         · submission_id 幂等回执（crowd_submissions）——改为可选：信封带 submission_id
--           才走回执链路；不带（旧 v3.2.3 插件）由服务端生成内部 uuid 占位，
--           幂等兜底退回 unique(participant_id, task_id, proof_seq, note_id)
--           → on conflict do nothing 判 duplicate_skipped；两条链路互不冲突
--         · sync_version 接受 >= 2（线上 v3.2.3 插件仍为 2；<2 才拒 stale_client）
--         · 逐条 verdict 落 crowd_proof_verdicts；拒收率从 verdicts 算（系统原因不计）
--         · URL 内嵌 ID 与 note_id 一致性静态校验；platform+note_id 去重
--         · 每词达标关单（包内每个关键词 accepted >= kpi_min → fulfilled）
--         · 参与者行锁（for update）串行化同参与者并发回传
--       实测适配：
--         · pack 为 jsonb 标准数组（双引号，pg_typeof 实测）：成员校验用 ? 运算符，
--           关键词枚举用 jsonb_array_elements_text，全部以 jsonb_typeof='array'
--           防御历史脏行（提交侧非数组拒收 pack_mismatch，脏行不炸函数）
--         · tasks.kw_progress 列实测必然存在且存量恒 {}——形状由本文件定义为
--           {关键词: accepted数} jsonb 对象，固定双写，不再做存在性探测分支
--
--     处理顺序：submission_id（可选）→ 幂等重放 → 占位行 → 参与者闸门（行锁）
--       → 信封解析 → sync_version>=2 → 任务闸门（行锁，含 claimed_by 口径）
--       → 配额 → 逐条校验裁决落库 → 锁任务行重读 → 进度/认领/kw_progress/关单
--       → 拒收率回写 → 回执持久化。
-- ------------------------------------------------------------
create or replace function public.crowd_submit_proof(p_participant_id text, p_envelope jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_submission_id   uuid;
  v_legacy_submit   boolean := false;
  v_existing        jsonb;
  v_parse_error     boolean := false;
  v_status          text;
  v_task_id         bigint;
  v_seq             int;
  v_sync            int;
  v_items           jsonb;
  v_captured        timestamptz;
  v_item            jsonb;
  v_idx             int;
  v_item_parse_err  boolean;
  v_kind            text;
  v_platform        text;
  v_note_id         text;
  v_note_url        text;
  v_url_id          text;
  v_title           text;
  v_quality         jsonb;   -- v3.4.2：质量标记（如 no_title），随 accepted 入库待复核
  v_excerpt         text;
  v_author          text;
  v_rating          numeric;
  v_rating_reason   text;
  v_matched         text;
  v_anchor          float;
  v_raw             text;
  v_keyword         text;
  v_kw_ok           boolean;
  v_result          jsonb := '[]'::jsonb;
  v_accepted        int := 0;
  v_rejected        text[] := '{}';
  v_task_status     text;
  v_claimed_by      text;
  v_pack            jsonb;         -- 实测为 jsonb 标准数组；用前以 jsonb_typeof='array' 防御
  v_kpi_min         int;
  v_new_progress    int;
  v_quota           int;
  v_today_used      int;
  v_reject_accum    int;
  v_accept_accum    int;
  v_reject_rate     float;
  v_dup             boolean;
  v_dedupe          text;
  v_kw_progress     jsonb;
  v_kw_obj          jsonb;
  v_incomplete      int;
  v_response        jsonb;
begin
  -- ⓪ submission_id（契约 v3 起新客户端必传，uuid）：
  --    有 → 走 crowd_submissions 幂等回执链路；
  --    无（旧 v3.2.3 插件）→ 服务端生成内部 uuid 占位（legacy 模式），
  --    处理流程一致，幂等兜底改由 proofs 的 unique 四元组承担（见 ⑥）。
  begin
    v_submission_id := nullif(p_envelope->>'submission_id', '')::uuid;
  exception when others then
    v_submission_id := null;
  end;
  if v_submission_id is null then
    v_submission_id := gen_random_uuid();
    v_legacy_submit := true;
  end if;

  -- ⓪b 幂等重放：该 submission_id 已处理过 → 原样返回存储的原始回执，不重算不重计
  --    （legacy 模式服务端现生成 uuid，不会命中本分支；其重试由 ⑥ 的四元组兜底）
  select response into v_existing
    from public.crowd_submissions
   where submission_id = v_submission_id;
  if found then
    return v_existing;
  end if;

  -- ⓪c 占位行：并发同一 submission_id 在此串行化（唯一约束等待前者提交/回滚）。
  --     冲突即另一事务已处理 → 回其原始回执。
  begin
    insert into public.crowd_submissions
      (submission_id, participant_id, task_id, sync_version, item_count, accepted_count, response)
    values
      (v_submission_id, p_participant_id, null, null, 0, 0,
       '{"ok":false,"reason":"processing"}'::jsonb);
  exception
    when unique_violation then
      select response into v_existing
        from public.crowd_submissions
       where submission_id = v_submission_id;
      return coalesce(v_existing,
        jsonb_build_object('ok', false, 'reason', 'submission_in_progress'));
  end;

  -- （kw_progress 列实测必然存在、存量恒 {}，形状由本文件固定为 {关键词: accepted}，
  --   不再做列存在性探测——见文件头执行前提）

  -- ① 参与者管控闸门（H3 防枚举语义保留：编号不存在/暂停/拉黑/驳回统一
  --    participant_unavailable）+ R8 行锁串行化同参与者并发回传
  select status into v_status
    from public.crowd_participants
   where participant_id = p_participant_id
   for update;

  -- ② 信封解析（垃圾类型不让整函数 500：统一落 envelope_parse_error 回执）
  begin
    v_task_id  := nullif(p_envelope->>'task_id', '')::bigint;
    v_seq      := nullif(p_envelope->>'proof_seq', '')::int;
    v_sync     := coalesce(nullif(p_envelope->>'sync_version', '')::int, 0);
    v_captured := coalesce(nullif(p_envelope->>'captured_at', '')::timestamptz, now());
    v_items    := coalesce(p_envelope->'items', '[]'::jsonb);
    if jsonb_typeof(v_items) is distinct from 'array' then
      v_items := '[]'::jsonb;
      v_parse_error := true;
    end if;
  exception when others then
    v_parse_error := true;
    v_items := '[]'::jsonb;
  end;

  -- ③ 信封级裁决链（任何分支只赋值 v_response，尾部统一持久化回执）
  if v_status is null or v_status in ('suspended', 'blacklisted', 'rejected') then
    v_response := jsonb_build_object('ok', false, 'reason', 'participant_unavailable',
                                     'submission_id', v_submission_id);
  elsif v_parse_error then
    v_response := jsonb_build_object('ok', false, 'reason', 'envelope_parse_error',
                                     'submission_id', v_submission_id);
  elsif v_sync < 2 then
    -- reconcile 口径：sync_version >= 2 即接受（线上 v3.2.3 插件仍为 2）；<2 拒 stale_client
    v_response := jsonb_build_object('ok', false, 'reason', 'stale_client',
                                     'expected_min', 2, 'got', v_sync,
                                     'submission_id', v_submission_id);
  elsif v_task_id is null or v_seq is null then
    v_response := jsonb_build_object('ok', false, 'reason', 'envelope_missing_task_or_seq',
                                     'submission_id', v_submission_id);
  elsif coalesce(p_envelope->>'participant_id', '') <> p_participant_id then
    -- 防跨参与者污染他人记录（外层编号=信封编号是格式校验，不是身份认证；
    -- 真正的身份绑定属下一阶段，见文件尾路线图）
    v_response := jsonb_build_object('ok', false, 'reason', 'participant_id_mismatch',
                                     'submission_id', v_submission_id);
  elsif v_captured > now() + interval '10 minutes' then
    v_response := jsonb_build_object('ok', false, 'reason', 'captured_at_future',
                                     'captured_at', v_captured, 'server_now', now(),
                                     'submission_id', v_submission_id);
  elsif v_captured < now() - interval '7 days' then
    v_response := jsonb_build_object('ok', false, 'reason', 'captured_at_too_old',
                                     'submission_id', v_submission_id);
  else
    -- ④ 任务闸门（入口）：行锁任务行，串行化同任务并发提交的进度判定与认领竞争。
    --    口径与逐条循环内完全一致：open 或 (in_progress 且 claimed_by = 本人)
    select status, pack, kpi_min, claimed_by
      into v_task_status, v_pack, v_kpi_min, v_claimed_by
      from public.crowd_tasks
     where task_id = v_task_id
     for update;
    if v_task_status is null
       or not (v_task_status = 'open'
               or (v_task_status = 'in_progress' and v_claimed_by = p_participant_id)) then
      v_response := jsonb_build_object('ok', false, 'reason', 'task_not_open',
                                       'submission_id', v_submission_id);
    else
      -- ⑤ 日配额批前快速失败
      select quota_day into v_quota
        from public.crowd_participants
       where participant_id = p_participant_id;
      select count(*) into v_today_used
        from public.crowd_proofs
       where participant_id = p_participant_id
         and gate_status = 'accepted'
         and created_at >= date_trunc('day', now());
      if coalesce(v_quota, 0) > 0 and v_today_used >= v_quota then
        v_response := jsonb_build_object('ok', false, 'reason', 'quota_exceeded',
                                         'quota_day', v_quota, 'used_today', v_today_used,
                                         'submission_id', v_submission_id);
      else
        -- ⑥ 逐条校验 + 裁决落库
        for v_item, v_idx in
          select e.value, (e.ord - 1)::int
            from jsonb_array_elements(v_items) with ordinality as e(value, ord)
        loop
          -- 任务闸门（循环内，与入口同口径；v3.2 根因即此处漏改 claimed_by 分支）：
          --   任务中途关闭/被他人认领（本批前面条目使其 fulfilled）→ 后续条目记 task
          --   类拒收，不计参与者拒收率（任务失效不是参与者作弊）
          select status, claimed_by
            into v_task_status, v_claimed_by
            from public.crowd_tasks
           where task_id = v_task_id;
          if not (v_task_status = 'open'
                  or (v_task_status = 'in_progress' and v_claimed_by = p_participant_id)) then
            v_rejected := v_rejected || format('item_task_fulfilled:%s', coalesce(v_item->>'note_id', '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_item->>'note_id',
               'rejected', 'item_task_fulfilled', 'task', false);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_item->>'note_id', ''),
                                                       'gate', 'rejected', 'reason', 'item_task_fulfilled');
            continue;
          end if;

          -- 条目解析（单条垃圾数字不炸整批）
          v_item_parse_err := false;
          begin
            v_kind          := v_item->>'kind';
            v_platform      := lower(coalesce(nullif(v_item->>'platform', ''), 'xiaohongshu'));
            v_note_id       := nullif(v_item->>'note_id', '');
            v_note_url      := nullif(v_item->>'note_url', '');
            v_title         := left(coalesce(v_item->>'title', ''), 100);
            v_excerpt       := left(coalesce(v_item->>'excerpt', ''), 200);
            v_author        := left(coalesce(v_item->>'author', ''), 50);
            v_rating        := nullif(v_item->>'rating', '')::numeric;
            v_rating_reason := left(coalesce(v_item->>'rating_reason', ''), 200);
            v_matched       := left(coalesce(v_item->>'matched_store', ''), 100);
            v_anchor        := nullif(v_item->>'anchor_score', '')::float;
            v_keyword       := nullif(v_item->>'raw_query', '');   -- 参与 pack 匹配用全文，不截断
            v_raw           := left(coalesce(v_item->>'raw_query', ''), 50);
            v_quality       := '{}'::jsonb;  -- 每条重置质量标记
          exception when others then
            v_item_parse_err := true;
          end;
          if v_item_parse_err then
            v_rejected := v_rejected || format('item_parse_error:%s', coalesce(v_item->>'note_id', '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_item->>'note_id',
               'rejected', 'item_parse_error', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_item->>'note_id', ''),
                                                       'gate', 'rejected', 'reason', 'item_parse_error');
            continue;
          end if;

          -- kind 枚举
          if v_kind not in ('note', 'rating') then
            v_rejected := v_rejected || format('item_kind_invalid:%s', coalesce(v_note_id, '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_kind_invalid', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_note_id, ''),
                                                       'gate', 'rejected', 'reason', 'item_kind_invalid');
            continue;
          end if;

          -- note_id / note_url 必填
          if v_note_id is null or v_note_url is null then
            v_rejected := v_rejected || format('item_missing_note:%s', coalesce(v_note_id, '?'));
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_missing_note', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', coalesce(v_note_id, ''),
                                                       'gate', 'rejected', 'reason', 'item_missing_note');
            continue;
          end if;

          -- 平台白名单（当前仅小红书；新增平台时需同步扩展 URL 规则与去重口径）
          if v_platform <> 'xiaohongshu' then
            v_rejected := v_rejected || format('item_platform_unsupported:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_platform_unsupported', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_platform_unsupported');
            continue;
          end if;

          -- R2 URL 严格正则：host 精确 www.xiaohongshu.com，路径 /explore/<24hex> 或 /discovery/item/<24hex>
          if v_note_url !~ '^https://www\.xiaohongshu\.com/explore/[0-9a-f]{24}(\?.*)?$'
             and v_note_url !~ '^https://www\.xiaohongshu\.com/discovery/item/[0-9a-f]{24}(\?.*)?$' then
            v_rejected := v_rejected || format('item_url_invalid:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_url_invalid', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_url_invalid');
            continue;
          end if;

          -- R3 note_id 必须 24 位十六进制
          if v_note_id !~ '^[0-9a-f]{24}$' then
            v_rejected := v_rejected || format('item_note_id_invalid:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_note_id_invalid', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_note_id_invalid');
            continue;
          end if;

          -- URL 内嵌 ID 必须等于 note_id（纯静态校验，不访问外网）：
          --   只分别检查 URL 形状和 note_id 形状会让"真 URL + 假 ID"蒙混入库
          v_url_id := (regexp_match(v_note_url, '(?:explore|discovery/item)/([0-9a-f]{24})'))[1];
          if v_url_id is null or v_url_id <> v_note_id then
            v_rejected := v_rejected || format('item_url_note_id_mismatch:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_url_note_id_mismatch', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_url_note_id_mismatch');
            continue;
          end if;

          -- raw_query 必须等于任务包 pack 中某一项（pack 实测为 jsonb 标准数组）。
          --   防御：jsonb_typeof='array' 才当数组处理；历史脏行（非数组/null）无法判定
          --   关键词归属 → 拒收原因 pack_mismatch（task 类，任务数据问题，不计参与者拒收率）；
          --   数组内无此成员 → item_keyword_not_in_pack（质量类，计入拒收率）——
          --   服务端只认词包成员，客户端标错关键词的条目直接拒收
          if jsonb_typeof(v_pack) is distinct from 'array' then
            v_rejected := v_rejected || format('pack_mismatch:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'pack_mismatch', 'task', false);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'pack_mismatch');
            continue;
          end if;
          v_kw_ok := v_keyword is not null and (v_pack ? v_keyword);
          if v_kw_ok is not true then
            v_rejected := v_rejected || format('item_keyword_not_in_pack:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_keyword_not_in_pack', 'quality', true);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_keyword_not_in_pack');
            continue;
          end if;

          -- R3 标题实质内容（v3.4.2 软化：手机人工提交通道常缺标题——身份由
          --   note_id+URL 一致性保证，空标题只记质量标记 no_title 待复核，不拒收不计拒收率；
          --   标题与正文皆空 = 内容全空，仍拒收（item_content_empty，防垃圾灌库，计拒收率））
          if coalesce(length(regexp_replace(v_title, '[\s[:punct:]]', '', 'g')), 0) < 2 then
            if coalesce(length(regexp_replace(v_excerpt, '[\s[:punct:]]', '', 'g')), 0) < 10 then
              v_rejected := v_rejected || format('item_content_empty:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_content_empty', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_content_empty');
              continue;
            end if;
            v_quality := '["no_title"]'::jsonb;
          end if;

          -- R6 rating 类：分值范围 / 理由质量 / 锚定同 platform+note_id 已收录笔记
          if v_kind = 'rating' then
            if v_rating is null or v_rating < 1 or v_rating > 5 then
              v_rejected := v_rejected || format('item_rating_out_of_range:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_rating_out_of_range', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_rating_out_of_range');
              continue;
            end if;
            if coalesce(length(regexp_replace(v_rating_reason, '[\s[:punct:]]', '', 'g')), 0) < 8 then
              v_rejected := v_rejected || format('item_rating_reason_too_short:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_rating_reason_too_short', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_rating_reason_too_short');
              continue;
            end if;
            select exists (
              select 1 from public.crowd_proofs
               where gate_status = 'accepted'
                 and kind = 'note'
                 and platform = v_platform
                 and note_id = v_note_id
            ) into v_kw_ok;
            if v_kw_ok is not true then
              v_rejected := v_rejected || format('item_rating_no_anchor:%s', v_note_id);
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'rejected', 'item_rating_no_anchor', 'quality', true);
              v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                         'gate', 'rejected', 'reason', 'item_rating_no_anchor');
              continue;
            end if;
          end if;

          -- 逐条配额限流（行锁保证计数一致）：超限属限流而非造假证据，不计拒收率
          if coalesce(v_quota, 0) > 0 and (v_today_used + v_accepted) >= v_quota then
            v_rejected := v_rejected || format('item_quota_exceeded:%s', v_note_id);
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'rejected', 'item_quota_exceeded', 'quota', false);
            v_result := v_result || jsonb_build_object('note_id', v_note_id,
                                                       'gate', 'rejected', 'reason', 'item_quota_exceeded');
            continue;
          end if;

          -- 去重口径 platform+note_id：note 全局唯一；
          --   rating 每参与者每笔记唯一（跨参与者可并存）
          if v_kind = 'rating' then
            v_dedupe := v_platform || ':' || v_note_id || ':rating:' || p_participant_id;
          else
            v_dedupe := v_platform || ':' || v_note_id;
          end if;
          select exists (
            select 1 from public.crowd_proofs
             where gate_status = 'accepted' and dedupe_key = v_dedupe
          ) into v_dup;
          if v_dup then
            -- 重复不计拒收率（可能源于调度冲突/重试，与造假分开）
            insert into public.crowd_proof_verdicts
              (submission_id, participant_id, task_id, item_index, note_id,
               verdict, reason, reason_category, counts_for_reject)
            values
              (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
               'duplicate', 'duplicate_note', 'duplicate', false);
            v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate');
            continue;
          end if;

          -- 落库：accepted 进 crowd_proofs。
          --   · unique(participant_id, task_id, proof_seq, note_id) 四元组冲突
          --     → on conflict do nothing，判 duplicate_skipped（legacy 无 submission_id
          --     重试的兜底幂等，与回执链路互不冲突）；
          --   · dedupe 部分唯一索引并发冲突 → unique_violation 捕获，判 duplicate_skipped
          --     （线上 v3.2 既有口径保留）；
          --   · 其他异常记 error（system，不计拒收率、不进 proofs）
          begin
            insert into public.crowd_proofs
              (participant_id, task_id, proof_seq, captured_at, sync_version,
               kind, platform, note_id, note_url, title, excerpt, author,
               rating, rating_reason, matched_store, anchor_score, raw_query, client_ip_salt,
               gate_status, gate_reason, dedupe_key, submission_id, quality_flags)
            values
              (p_participant_id, v_task_id, v_seq, v_captured, v_sync,
               v_kind, v_platform, v_note_id, v_note_url, v_title, v_excerpt, v_author,
               v_rating, v_rating_reason, v_matched, v_anchor, v_raw, v_item->>'client_ip_salt',
               'accepted', null, v_dedupe, v_submission_id, v_quality)
            on conflict (participant_id, task_id, proof_seq, note_id) do nothing;
            if found then
              v_accepted := v_accepted + 1;
              -- 关键词进度累计（crowd_task_keyword_progress 表始终维护；
              --   on conflict 行锁保证并发安全，原子增量）
              insert into public.crowd_task_keyword_progress (task_id, keyword, accepted, updated_at)
              values (v_task_id, v_keyword, 1, now())
              on conflict (task_id, keyword) do update
                set accepted = crowd_task_keyword_progress.accepted + 1,
                    updated_at = now();
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'accepted', null, 'none', false);
              v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'accepted');
            else
              -- 四元组冲突：legacy 重试/断网重传的兜底幂等（duplicate_skipped，不计拒收率）
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'duplicate', 'duplicate_seq_replay', 'duplicate', false);
              v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
            end if;
          exception
            when unique_violation then
              -- dedupe 唯一索引并发冲突（线上 v3.2 口径：捕获为 duplicate_skipped）
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'duplicate', 'duplicate_note', 'duplicate', false);
              v_result := v_result || jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
            when others then
              insert into public.crowd_proof_verdicts
                (submission_id, participant_id, task_id, item_index, note_id,
                 verdict, reason, reason_category, counts_for_reject, detail)
              values
                (v_submission_id, p_participant_id, v_task_id, v_idx, v_note_id,
                 'error', 'item_insert_error', 'system', false, SQLERRM);
              v_result := v_result || jsonb_build_object('note_id', coalesce(v_note_id, ''),
                                                         'gate', 'error', 'reason', 'item_insert_error');
          end;
        end loop;

        -- ⑦ 回写任务总进度 / 认领（含租约）/ kw_progress 双写 / 参与者累计
        --    （只在有新增 accepted 时）
        if v_accepted > 0 then
          -- v3.2 并发安全口径：SELECT ... FOR UPDATE 锁任务行重读
          -- （行锁自入口任务闸门持有，此处重读最新 status/pack/kpi_min/progress）
          select status, pack, kpi_min, progress
            into v_task_status, v_pack, v_kpi_min, v_new_progress
            from public.crowd_tasks
           where task_id = v_task_id
           for update;

          -- progress 原子增量 + open 任务首个 accepted 提交认领（行锁保证只有一个
          --   事务完成认领）：置 in_progress / claimed_by=本人 / claimed_at=now() /
          --   lease_until=now()+lease_duration_min 分钟（实测默认 1440）。
          --   租约过期回收（到期自动回 open）属下一阶段，本文件不实现。
          update public.crowd_tasks
             set progress     = progress + v_accepted,
                 status       = case when status = 'open' then 'in_progress' else status end,
                 claimed_by   = case when status = 'open' then p_participant_id else claimed_by end,
                 claimed_at   = case when status = 'open' then now() else claimed_at end,
                 lease_until  = case when status = 'open'
                                     then now() + make_interval(mins => coalesce(lease_duration_min, 1440))
                                     else lease_until end,
                 updated_at   = now()
           where task_id = v_task_id;

          -- kw_progress 双写之一：tasks.kw_progress jsonb（列实测必然存在；
          --   固定形状 {关键词: accepted}，覆盖 pack 全部关键词含 0 进度。
          --   pack 为 jsonb 标准数组；jsonb_typeof 防御历史脏行（非数组按空包处理）
          select coalesce(jsonb_object_agg(kw, coalesce(p.accepted, 0)), '{}'::jsonb)
            into v_kw_obj
            from (select kw
                    from jsonb_array_elements_text(
                           case when jsonb_typeof(v_pack) = 'array'
                                then v_pack else '[]'::jsonb end) kw) kws
            left join public.crowd_task_keyword_progress p
              on p.task_id = v_task_id and p.keyword = kws.kw;
          update public.crowd_tasks
             set kw_progress = v_kw_obj,
                 updated_at   = now()
           where task_id = v_task_id;

          update public.crowd_participants
             set total_effective = total_effective + v_accepted,
                 last_active_at = now()
           where participant_id = p_participant_id;

          -- 完成标准统一：包内每个关键词 accepted >= kpi_min 才 fulfilled
          --   （旧逻辑整包累计达标即关单，与客户端"每词达标"不一致）
          select count(*)
            into v_incomplete
            from (select kw
                    from jsonb_array_elements_text(
                           case when jsonb_typeof(v_pack) = 'array'
                                then v_pack else '[]'::jsonb end) kw) kws
            left join public.crowd_task_keyword_progress p
              on p.task_id = v_task_id and p.keyword = kws.kw
           where coalesce(p.accepted, 0) < v_kpi_min;
          if v_incomplete = 0 then
            update public.crowd_tasks
               set status = 'fulfilled',
                   updated_at = now()
             where task_id = v_task_id
               and status in ('open', 'in_progress');
          end if;
        end if;

        -- ⑧ 拒收率风控：从 crowd_proof_verdicts 事实表计算；
        --    仅 quality 类计入分子分母，duplicate/task/quota/system 一律不算参与者责任
        select coalesce(sum(case when verdict = 'accepted' then 1 else 0 end), 0),
               coalesce(sum(case when counts_for_reject then 1 else 0 end), 0)
          into v_accept_accum, v_reject_accum
          from public.crowd_proof_verdicts
         where participant_id = p_participant_id;
        if (v_accept_accum + v_reject_accum) > 20 then
          v_reject_rate := v_reject_accum::float / (v_accept_accum + v_reject_accum);
          if v_reject_rate > 0.6 then
            update public.crowd_participants
               set status = 'suspended',
                   review_note = 'auto_suspend: reject_rate ' || round(v_reject_rate::numeric, 2)
             where participant_id = p_participant_id;
          else
            update public.crowd_participants
               set reject_rate = v_reject_rate
             where participant_id = p_participant_id;
          end if;
        end if;

        select progress into v_new_progress
          from public.crowd_tasks
         where task_id = v_task_id;

        -- keyword_progress：客户端据此同步每词进度（覆盖 pack 全部关键词含 0 进度；
        --   pack 为 jsonb 标准数组；jsonb_typeof 防御历史脏行，非数组返回空数组）
        select coalesce(
                 jsonb_agg(
                   jsonb_build_object('keyword', kws.kw, 'accepted', coalesce(p.accepted, 0))
                   order by kws.kw),
                 '[]'::jsonb)
          into v_kw_progress
          from (select kw
                  from jsonb_array_elements_text(
                         case when jsonb_typeof(v_pack) = 'array'
                              then v_pack else '[]'::jsonb end) kw) kws
          left join public.crowd_task_keyword_progress p
            on p.task_id = v_task_id and p.keyword = kws.kw;

        v_response := jsonb_build_object(
          'ok', true,
          'submission_id', v_submission_id,
          'accepted', v_accepted,
          'rejected', v_rejected,
          'results', v_result,
          'new_progress', coalesce(v_new_progress, 0),
          'keyword_progress', v_kw_progress
        );
      end if;
    end if;
  end if;

  -- ⑨ 回执统一持久化（成功与业务失败都落库，供幂等重放与申诉核查；
  --    legacy 模式同样落库，response 内 submission_id 可供申诉定位；
  --    未捕获的系统异常会让整个事务回滚，占位行一并消失，重试重新执行——
  --    系统故障不产生假回执）
  update public.crowd_submissions
     set participant_id = p_participant_id,
         task_id        = v_task_id,
         sync_version   = v_sync,
         item_count     = jsonb_array_length(v_items),
         accepted_count = v_accepted,
         response       = v_response
   where submission_id = v_submission_id;

  return v_response;
end;
$$;


-- ------------------------------------------------------------
-- S6) 授权说明 —— 明确不吊销 crowd_submit_proof 的任何现有授权
--     与 v311 设计相反：v311 计划收回旧函数 anon/authenticated 执行权、强切新函数；
--     本 reconcile 版在同一函数上原地升级，线上 v3.2.3 插件以 crowd_submit_proof
--     持续调用，吊销授权等于当场断服。因此：
--       - 不执行任何 revoke ... on function public.crowd_submit_proof；
--       - 仅幂等确保 execute 授权存在（grant 重复执行无副作用）；
--       - anon/authenticated 执行业务提交的安全边界维持现状（H3 闸门在函数内），
--         收窄到 Supabase Auth 可信身份属下一阶段（见文件尾路线图），届时统一调整。
-- ------------------------------------------------------------
grant execute on function public.crowd_submit_proof(text, jsonb)
  to anon, authenticated, service_role;


-- ------------------------------------------------------------
-- 验证提示（迁移后人工核查；详细 checklist 见文件尾）：
--   select public.crowd_register_participant(null, null, 'salt-abcdefgh');
--     -- 期望 {"ok":true,"participant_id":"P-XXXXXXXX","reused":false,...}（8 位）
--   select public.crowd_register_participant(null, null, 'salt-abcdefgh');
--     -- 同 salt 再调，期望 {"ok":true,"participant_id":<同上>,"reused":true}
--   select public.crowd_submit_proof('P-B269XL1K', jsonb_build_object(
--     'participant_id','P-B269XL1K','task_id',15,'proof_seq',0,'sync_version',2,
--     'captured_at', now(), 'items', '[]'::jsonb));
--     -- task#15 为 open：items 为空时不触发认领（accepted=0）；带一条合规 note
--     -- 再提交一次，期望 ok:true 且 task#15 置 in_progress / claimed_by=P-B269XL1K /
--     -- claimed_at 非空 / lease_until ≈ now()+1440min
--   select public.crowd_submit_proof('P-B269XL1K', jsonb_build_object(
--     'participant_id','P-B269XL1K','task_id',10,'proof_seq',99,'sync_version',2,
--     'captured_at', now(), 'items', '[]'::jsonb));
--     -- task#10 已 fulfilled：期望 {ok:false, reason:task_not_open}
--   select verdict, reason, reason_category, counts_for_reject
--     from crowd_proof_verdicts order by id desc limit 10;
--   select keyword, accepted from crowd_task_keyword_progress where task_id = 15;
-- ============================================================


-- ============================================================
-- 【执行前 checklist】（按序执行）
--   0) 备份函数定义（v3.2 迁移文件本仓库缺失，回滚只能靠备份）：
--        select pg_get_functiondef('public.crowd_submit_proof(text,jsonb)'::regprocedure);
--        select pg_get_functiondef('public.crowd_bind_participant'::regprocedure);
--      -- crowd_bind_participant 是 v3.2.3 旧插件注册入口，本迁移不动它，
--      -- 备份仅作并存关系备查；输出全部存档后再执行本文件。
--   1) 执行本文件（可重复执行，幂等）。
--
-- 【执行后冒烟】（真库逐一核对）
--   2) P-B269XL1K 对 task#15（open）提交含一条合规 note 的信封 → ok:true，
--      且 task#15 置 in_progress / claimed_by=P-B269XL1K / claimed_at 非空 /
--      lease_until ≈ now() + 1440min；crowd_task_keyword_progress 对应词 +1，
--      crowd_tasks.kw_progress 为 {关键词: accepted} 对象且计数一致。
--   3) P-B269XL1K 对 task#10（fulfilled）提交 → {ok:false, reason:task_not_open}；
--      带 items 时后续条目在循环内同样拒 item_task_fulfilled（task 类，不计拒收率）。
--   4) 同一 submission_id 重投 → 逐字节重放原始回执；无 submission_id（legacy）
--      重投同 proof_seq+note_id → duplicate_skipped，proofs 不增行。
--   5) 存量 smoke 行（note_id 以 aaaa/bbbb 开头）dedupe_key 已回灌为
--      platform:note_id 口径，gate_status 未被误降级（无冲突行时降级语句空转）。
--   6) 线上 crowd_submissions / crowd_proof_verdicts / crowd_task_keyword_progress
--      若已被 v3.2 建过且列定义与本文件 S3/S4 不同（create if not exists 会跳过），
--      需要人工 diff 后决定是否 alter 补列；本文件假设同构。
--   7) 线上 crowd_register_participant 若已存在且参数类型签名不同，
--      CREATE OR REPLACE 会产生重载而非替换——执行后检查：
--        select proname, pg_get_function_identity_arguments(oid)
--          from pg_proc where proname in ('crowd_register_participant', 'crowd_bind_participant');
--      register 应只有 (text, text, text, text) 一个；bind 应保持原样。
--   8) crowd_store_evidence / crowd_store_candidates / crowd_settle /
--      crowd_bind_participant 本文件未触碰，执行后确认其定义与数据零变化
--      （pg_get_functiondef 对比 + count 对比）。
--
-- 【下一阶段路线图】（本次明确不做）
--   1) Supabase Auth 绑定：participant ↔ auth 用户；RPC 从 auth.uid() 取身份并校验
--      ownership；届时收回 anon 对业务提交/报名的执行权。
--   2) 任务租约回收：认领与 lease 写入已落地（本文件 S5：claimed_at/lease_until），
--      补 lease 过期自动回 open 的回收逻辑，杜绝参与者失联占死任务。
--   3) 预算预留：认领时锁定单价版本并做 budget 预留，结算按预留核销，防超预算计酬。
--   4) 结算：线上已有 crowd_settle RPC（note ¥2 / rating ¥1，周一 09:00 launchd
--      触发），本仓库缺其定义，待回收后纳入版本管理并与 verdicts 事实表对账。
--   5) crowd_store_ingest 证据入库：代码在服务器（本仓库缺），待回收；
--      crowd_store_evidence / crowd_store_candidates 维持现状不动。
--
-- 【回滚纲要】（手动执行，非自动）
--   0) 前置：执行前的 pg_get_functiondef 备份（见上方 checklist 第 0 步）是唯一能
--      还原 v3.2 函数体的依据——没有备份不要回滚。
--   1) 用备份的 CREATE OR REPLACE 语句覆盖还原 public.crowd_submit_proof
--      与 public.crowd_register_participant（若线上原先没有后者则
--      drop function public.crowd_register_participant(text, text, text, text)）。
--      crowd_bind_participant 本文件未触碰，无需回滚。
--   2) 本文件新建对象（仅当确认是本文件首次创建、且已备份数据后才可删）：
--        drop table if exists public.crowd_proof_verdicts;
--        drop table if exists public.crowd_submissions;
--        drop table if exists public.crowd_task_keyword_progress;
--      crowd_proofs 新增列（platform/gate_reason/submission_id/quality_flags）：
--      线上实测 crowd_tasks 租约列与 kw_progress 均为 v3.2 既有，不在回滚范围；
--      proofs 四列确为本文件新增且确认无依赖才可 drop column。
--   3) dedupe_key 新口径与 idx_crowd_proofs_dedupe_note 一般无需回滚
--      （线上 v3.2 已按 platform+note_id 语义运行）；确需回旧口径时参考
--      git 历史中已删除的 crowd_fix_v311.sql 文件尾纲要。
--   4) 授权无需回滚：本文件未吊销任何授权，grant 与线上现状一致。
-- ============================================================
