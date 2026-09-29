-- =====================================================================
-- 016_scoring_v4_alignment.sql — 评分公式 v4 对齐（迁移文件与数据库实际运行一致）
-- ---------------------------------------------------------------------
-- 背景：
--   005_scoring_v3.sql 写的是 v3 公式（0.35t+0.25o+0.25d+0.15e），
--   但数据库实际运行的是 v4 公式（0.45t+0.25d+0.18o+0.12e + provisional上限82），
--   该修改可能直接在 Supabase SQL Editor 中执行，未记录在迁移文件中。
--   经 1479 家餐厅精确重验，v4 公式 + provisional上限82 = 0 家不符。
--   本迁移文件将 derive_restaurant 函数显式更新为 v4，确保代码与数据库一致。
--
-- v4 公式：
--   score_total = round(clamp(
--     0.45*score_taste + 0.25*score_diner + 0.18*score_objective + 0.12*score_endorsement
--     - soft_ad_penalty), 1)
--   evidence_level:
--     - 独立作者数 >= 2 → verified（无上限）
--     - 独立作者数 = 1 → provisional（上限 82 分）
--     - 仅有 objective/endorsement → provisional（上限 70 分）
--     - 无任何证据 → insufficient（score_total = NULL）
--
-- 幂等可重跑；DDL 只能走 Supabase SQL Editor（REST 做不了 DDL）。
-- =====================================================================

CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_nind INTEGER;
    v_blend NUMERIC;
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();
  IF NEW.price_avg IS NOT NULL THEN
    NEW.tier := tier_for_price(NEW.price_avg);
  END IF;

  -- 计算独立作者数（用于 evidence_level 判定）
  SELECT COUNT(DISTINCT author_name) INTO v_nind
  FROM reviews
  WHERE restaurant_id = NEW.id
    AND review_kind = 'diner'
    AND COALESCE(is_fake_suspect, false) = false
    AND is_hidden = false
    AND COALESCE(aspect_taste, rating_taste, rating_total) IS NOT NULL;

  -- 四项子分齐全时用 v4 加权公式
  IF NEW.score_taste IS NOT NULL AND NEW.score_diner IS NOT NULL THEN
    v_blend := 0.45 * NEW.score_taste
             + 0.25 * NEW.score_diner
             + 0.18 * COALESCE(NEW.score_objective, NEW.score_taste)
             + 0.12 * COALESCE(NEW.score_endorsement, 0);

    IF v_nind >= 2 THEN
      NEW.score_evidence_level := 'verified';
      NEW.score_total := greatest(0, least(100, round(v_blend - COALESCE(NEW.soft_ad_penalty, 0), 1)));
    ELSE
      NEW.score_evidence_level := 'provisional';
      NEW.score_total := greatest(0, least(82, round(v_blend - COALESCE(NEW.soft_ad_penalty, 0), 1)));
    END IF;

  -- 仅有 objective/endorsement（无口味/食客分）时，provisional 上限 70
  ELSIF COALESCE(NEW.score_objective, 0) > 0 OR COALESCE(NEW.score_endorsement, 0) > 0 THEN
    v_blend := 0.6 * COALESCE(NEW.score_objective, 0)
             + 0.4 * COALESCE(NEW.score_endorsement, 0);
    NEW.score_evidence_level := 'provisional';
    NEW.score_total := greatest(0, least(70, round(v_blend - COALESCE(NEW.soft_ad_penalty, 0), 1)));

  -- 无任何证据
  ELSE
    NEW.score_evidence_level := 'insufficient';
    NEW.score_total := NULL;
  END IF;

  RETURN NEW;
END $$;

-- =====================================================================
-- 验证（独立 SELECT，确认迁移生效）
-- =====================================================================
-- 1. 检查函数定义中包含 v4 权重
-- SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname='derive_restaurant';
--
-- 2. 抽样验证：取 10 家有 score_total 的餐厅，手工重算对比
-- SELECT id, name, score_taste, score_diner, score_objective, score_endorsement,
--        score_evidence_level, score_total,
--        round(0.45*score_taste + 0.25*score_diner + 0.18*COALESCE(score_objective,score_taste) + 0.12*COALESCE(score_endorsement,0) - COALESCE(soft_ad_penalty,0), 1) AS expected_v4
-- FROM restaurants
-- WHERE score_total IS NOT NULL AND score_taste IS NOT NULL AND score_diner IS NOT NULL
-- ORDER BY score_total DESC NULLS LAST
-- LIMIT 10;
--
-- 3. 全量验证：v4 公式不符的餐厅数（应为 0）
-- SELECT count(*) FROM restaurants
-- WHERE score_total IS NOT NULL AND score_taste IS NOT NULL AND score_diner IS NOT NULL
--   AND abs(score_total - LEAST(
--     CASE WHEN score_evidence_level='provisional' THEN 82 ELSE 100 END,
--     round(0.45*score_taste + 0.25*score_diner + 0.18*COALESCE(score_objective,score_taste) + 0.12*COALESCE(score_endorsement,0) - COALESCE(soft_ad_penalty,0), 1)
--   )) > 0.1;
-- =====================================================================
