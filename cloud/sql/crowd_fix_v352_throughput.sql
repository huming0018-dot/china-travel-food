-- crowd_fix_v352_throughput.sql
-- v3.5.2 轻量化提产（少搜多榨）服务端配额调整
--
-- 背景：客户端 v3.5.2 单页温和下划 2 屏 + 信封槽位 12→30，单 SERP 产出 1 条→2–4 条，
--      浏览/搜索节奏不变（搜索间隔仍 90s、风控冷却/hard_cap 不动）。原服务端日配额
--      participants=20–25、tasks=20 会先于新产能封顶，需上调。
--
-- 安全线：社区实测 300 条/号/日触发验证码；本调整 participants 上限 50（≈红线 1/6），
--        tasks 上限 40（一个 6 店×5KPI=30 条的包可一天采完 + 10 条余量）。
-- 幂等：所有 UPDATE 均为幂等条件更新，可重复执行；不触碰 fulfilled/closed 任务、
--      新号（eff<30）、高拒回率/近期风控设备，让它们继续走爬坡与观察。
--
-- 执行：Supabase SQL Editor（DDL ALTER 必须走 SQL；下方两条 UPDATE 也可由
--      容器内 service role 经 PostgREST PATCH 完成，逻辑等价）。

BEGIN;

-- 1) 新任务包默认日配额 20→40（对所有 publish 通道生效，含 crowd_v4_admin / edge publish）。
--    参与者表默认保持 20：新号仍需经 7 天爬坡与观察，不默认高配额。
ALTER TABLE crowd_tasks ALTER COLUMN quota_day SET DEFAULT 40;

-- 2) 现有未完成任务包（open/in_progress）日配额提到 40，当天即可采完一个 6 店包。
UPDATE crowd_tasks t
SET quota_day = 40
WHERE t.status IN ('open', 'in_progress')
  AND t.quota_day < 40;

-- 3) 活跃低风险参与者日配额提到 50（机制化条件，非点名）：
--    · 已通过审核或在审（pending/approved）
--    · 累计有效产出 ≥ 30（证明能稳定真实采）
--    · 拒回率 < 10%
--    · 近 48h 风控信号 < 2 条（与 v3.5.1 日配额降额口径一致：≥2 条降 30%）
--    已为 50 的不动；不满足的新号/高风险号继续爬坡。
UPDATE crowd_participants p
SET quota_day = 50
WHERE p.status IN ('pending', 'approved')
  AND COALESCE(p.total_effective, 0) >= 30
  AND COALESCE(p.reject_rate, 0) < 0.1
  AND (
    SELECT COUNT(*) FROM crowd_risk_log r
    WHERE r.participant_id = p.participant_id
      AND r.created_at >= now() - interval '48 hours'
  ) < 2
  AND p.quota_day < 50;

COMMIT;

-- ---- 回读验证（只读，不写入）----
-- 3.1 参与者配额分布
SELECT status, quota_day, COUNT(*) AS n,
       MIN(total_effective) AS min_eff, MAX(total_effective) AS max_eff
FROM crowd_participants
GROUP BY status, quota_day
ORDER BY status, quota_day;

-- 3.2 本轮命中提额的参与者（应为 eff≥30、rr<0.1、近期无风险的活跃号）
SELECT participant_id, status, quota_day, total_effective,
       ROUND(COALESCE(reject_rate, 0)::numeric, 3) AS reject_rate, last_active_at
FROM crowd_participants
WHERE quota_day = 50
ORDER BY total_effective DESC;

-- 3.3 未完成任务的配额（应全部为 40）
SELECT status, quota_day, COUNT(*) AS n
FROM crowd_tasks
WHERE status IN ('open', 'in_progress')
GROUP BY status, quota_day
ORDER BY status, quota_day;

-- 3.4 确认表默认值已变为 40
SELECT column_name, column_default
FROM information_schema.columns
WHERE table_name = 'crowd_tasks' AND column_name = 'quota_day';
