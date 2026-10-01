-- =====================================================================
-- 024_prior_evidence_separation.sql — 启发式先验 vs 证据列 物理分离
-- ---------------------------------------------------------------------
-- 背景（2026-10-01 治理）：
--   restaurants.central_kitchen='疑似'(≈169 行)、premade_risk='低'(≈155 行) 中，
--   绝大多数是 chain_audit.py 按连锁档位（小型连锁/REGIONAL_HINT 词表）批量推的
--   【启发式先验】，无逐店 source_url。这些先验却被硬门/评分（reconcile.py、
--   curate_v4.py）当成「证据」消费，导致未取证门店被误罚/误移出精选。
--   而 central_kitchen='确认'(≈20)、premade_risk='高'(≈17) 是有 fact_claims
--   （同 type + source_url）背书的真实证据，绝不能动。
--
-- 方案：证据列值域不变（沿用 003 的 CHECK），另增「先验列」承载启发式猜测。
--   - 纯先验行：值搬到 *_prior 列（prior_provenance='heuristic', prior_confidence≈0.30），
--     证据列回置 '无'。
--   - 有证据行：证据列保留原值，不搬。
--   - 确认/高：脚本（cloud/prior_separate.py）永远跳过。
--
-- 【铁律 / 消费约定】
--   * 硬门（reconcile.py 精选移出、goalkeeper、发版审计）只消费【证据列】
--     central_kitchen / premade_risk，绝不消费 *_prior。
--   * *_prior 仅作评分模型（curate_score / curate_v4）的弱特征，不得参与硬闸门。
--
-- 本迁移只加列 + CHECK，不回写任何数据；回写由 cloud/prior_separate.py --apply 完成。
-- 幂等可重复执行。执行环境：Supabase -> SQL Editor，逐条提交（见文件底部说明）。
-- =====================================================================

-- ---------------------------------------------------------------------
-- BATCH 1 — 新增 4 列（幂等，均可空；不回填现有行）
-- ---------------------------------------------------------------------
ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS central_kitchen_prior text;          -- 启发式先验：无/疑似/确认
ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS premade_prior        text;          -- 启发式先验：无/低/疑似/高
ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS prior_provenance     text DEFAULT 'heuristic';  -- 先验来源标签
ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS prior_confidence     double precision;          -- 先验置信度 0..1（启发式取低，≈0.30）

-- ---------------------------------------------------------------------
-- BATCH 2 — 值域 CHECK（幂等）。先验列沿用证据列同一枚举，避免新脏值。
-- ---------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_ck_prior') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_ck_prior
      CHECK (central_kitchen_prior IS NULL
             OR central_kitchen_prior IN ('无','疑似','确认'));
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_premade_prior') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_premade_prior
      CHECK (premade_prior IS NULL
             OR premade_prior IN ('无','低','疑似','高'));
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_prior_provenance') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_prior_provenance
      CHECK (prior_provenance IS NULL
             OR prior_provenance IN ('heuristic','chain_tier','evidence_override'));
  END IF;
END $$;

-- prior_confidence 仅作范围约束（可空）：允许 0..1
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_prior_confidence') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_prior_confidence
      CHECK (prior_confidence IS NULL
             OR (prior_confidence >= 0 AND prior_confidence <= 1));
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- BATCH 3 — 加列后验证（独立 SELECT，应全部返回新列名）
-- ---------------------------------------------------------------------
-- SELECT column_name, data_type, column_default
--   FROM information_schema.columns
--  WHERE table_name='restaurants'
--    AND column_name IN
--        ('central_kitchen_prior','premade_prior','prior_provenance','prior_confidence')
--  ORDER BY column_name;

-- ---------------------------------------------------------------------
-- 【回滚语句】（仅当需要整体撤销本迁移时，在 SQL Editor 逐条执行）
--   ALTER TABLE restaurants DROP CONSTRAINT IF EXISTS ch_rest_prior_confidence;
--   ALTER TABLE restaurants DROP CONSTRAINT IF EXISTS ch_rest_prior_provenance;
--   ALTER TABLE restaurants DROP CONSTRAINT IF EXISTS ch_rest_premade_prior;
--   ALTER TABLE restaurants DROP CONSTRAINT IF EXISTS ch_rest_ck_prior;
--   ALTER TABLE restaurants DROP COLUMN IF EXISTS central_kitchen_prior;
--   ALTER TABLE restaurants DROP COLUMN IF EXISTS premade_prior;
--   ALTER TABLE restaurants DROP COLUMN IF EXISTS prior_provenance;
--   ALTER TABLE restaurants DROP COLUMN IF EXISTS prior_confidence;
-- ---------------------------------------------------------------------

-- =====================================================================
-- 执行说明（用户在 Supabase SQL Editor）：
--   1) 先逐条跑 BATCH 1 的 4 个 ADD COLUMN，再跑 BATCH 2 的 4 个 DO 块；
--      每段单独 Run，确认无报错再下一段（避免一个大事务里 CHECK 失败难定位）。
--   2) 跑 BATCH 3 注释里的 SELECT，确认 4 列都在。
--   3) 本迁移【不回写数据】。确认列就绪后，再在容器里跑：
--        . /app/cloud/env.sh && python3 -u cloud/prior_separate.py
--      先看 dry-run 计数与样例；核对无误后才加 --apply。
--   4) 回滚仅在出问题时执行上面 BATCH 3 后的注释块。
-- =====================================================================
