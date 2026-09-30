-- =====================================================================
-- 021_goalkeeper_curate.sql — 守门员·精选体系字段
-- ---------------------------------------------------------------------
-- 背景：评分 v4 的子分与人工三档标注实测不相关（一般档甚至高于值得档），
--   需建立独立于“广泛收录”的【精选层】：以人工三档为监督、真实奖项 + 足量独立
--   真实食客证据为正向依据，工业化/预制/刷评为负向闸门。
--   本迁移只新增精选层列，不改动任何在跑评分（score_total 等）口径。
--
-- 列含义：
--   is_curated        是否进入“真美食精选”（默认 false，广泛库不受影响）
--   curate_badge      必吃 / 值得 / 精选（NULL=未入选）
--   curate_score      精选排序分（真实证据贝叶斯收缩 + 奖项，0-100）
--   curate_confidence 精选置信度（0-1，随独立食客数/奖项/人工标注）
--   curate_reason     入选/落选的可追溯理由
--   astroturf_score   伪草根刷评连续分（softad_distribution 自学，0-1）
--
-- 由 curate_score.py / softad_distribution.py PATCH；幂等可重跑。
-- DDL 只能走 Supabase SQL Editor。
-- =====================================================================

ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS is_curated BOOLEAN DEFAULT false;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS curate_badge VARCHAR(16);
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS curate_score NUMERIC;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS curate_confidence NUMERIC;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS curate_reason TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS astroturf_score NUMERIC;

CREATE INDEX IF NOT EXISTS idx_rest_curated ON restaurants(is_curated) WHERE is_curated;
CREATE INDEX IF NOT EXISTS idx_rest_curate_score ON restaurants(curate_score DESC NULLS LAST);

-- =====================================================================
-- 验证（独立 SELECT）
--   SELECT count(*) FILTER (WHERE is_curated) AS curated,
--          count(*) AS total,
--          count(*) FILTER (WHERE curate_badge='必吃') AS must,
--          count(*) FILTER (WHERE curate_badge='值得') AS worth
--   FROM restaurants WHERE status='active';
-- =====================================================================
