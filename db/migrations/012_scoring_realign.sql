-- =====================================================================
-- 012_scoring_realign.sql — 评分引擎"真实食客对齐" + 价格权威归一
-- ---------------------------------------------------------------------
-- 背景（2026-09-27 生产库实测）：
--   1504/1507 家有全套 score_*，但 589 家 0 真实评价、905 家仅 1~3 条；
--   1038 条 reviews 中 899 条是高德聚合评分(trust=low)，真正小红书 UGC 仅 139 条。
--   平台聚合评分被当成口味分 → "口味优先"空心；soft_ad_flag_reviews 从未生效。
-- 修正原则（用户多次明确）：
--   ①只采信真实食客堂食 UGC（trust mid/high），平台聚合评分只进 score_objective；
--   ②真实食客/口味权重最高，平台/背书其次；
--   ③无真实食客证据者不得与已验证好店同分（provisional 封顶）；
--   ④价格以 price_scene+price_band（场景客观带）为唯一权威，补全空值；
--   tier / price_position 为遗留字段，前端恢复时移除，不在此 DROP。
-- 幂等可重跑；DDL 走 Supabase SQL Editor。
-- =====================================================================

-- ---------- BATCH 1：证据分级列 ----------
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS score_evidence_level TEXT;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_evidence_level') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_evidence_level
      CHECK (score_evidence_level IS NULL
             OR score_evidence_level IN ('verified','provisional','insufficient'));
  END IF;
END $$;

-- 旧约束要求四项分数"全有或全无"，与新设计冲突：真实 taste/diner 可空、
-- objective/endorsement 保留（provisional 由 derive 单独处理）→ 删除。
ALTER TABLE restaurants DROP CONSTRAINT IF EXISTS ch_rest_score_complete;

-- ---------- BATCH 2：品类先验只取真实食客 UGC ----------
CREATE OR REPLACE FUNCTION cuisine_prior(p_rest INTEGER)
RETURNS TABLE(c_prior numeric, v_prior numeric) AS $$
DECLARE
  v_leaf_id INTEGER;
BEGIN
  SELECT c.id INTO v_leaf_id
  FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
  WHERE rc.restaurant_id=p_rest AND c.dimension='菜系'
  ORDER BY rc.is_primary DESC, c.id LIMIT 1;

  RETURN QUERY
  WITH RECURSIVE chain AS (
    SELECT c.id AS cuisine_id, c.name::text AS lvl, c.parent_category::text AS parent, 1 AS depth
    FROM cuisines c WHERE c.id = v_leaf_id
    UNION ALL
    SELECT NULL, ch.parent, c2.parent_category::text, ch.depth+1
    FROM chain ch
    LEFT JOIN cuisines c2 ON c2.name = ch.parent AND c2.dimension = '菜系'
    WHERE ch.parent IS NOT NULL
  ),
  stats AS (
    SELECT ch.depth,
      (SELECT COALESCE(SUM(
         POWER(0.5,(CURRENT_DATE-COALESCE(rv.visit_date,rv.created_at)::DATE)/180.0)
         * (COALESCE(rv.aspect_taste,rv.rating_taste,rv.rating_total)-1)/4.0*100
       ) / NULLIF(SUM(
         POWER(0.5,(CURRENT_DATE-COALESCE(rv.visit_date,rv.created_at)::DATE)/180.0)
       ),0), 70.0)
       FROM reviews rv
       JOIN restaurant_cuisines rc2 ON rc2.restaurant_id=rv.restaurant_id
       JOIN cuisines c2 ON c2.id=rc2.cuisine_id
       WHERE rv.review_kind='diner'
         AND COALESCE(rv.is_fake_suspect,false)=false
         AND rv.is_hidden=false
         AND COALESCE(rv.trust_level,'low') IN ('mid','high')   -- 仅真实 UGC
         AND COALESCE(rv.aspect_taste,rv.rating_taste,rv.rating_total) IS NOT NULL
         AND (ch.cuisine_id IS NOT NULL AND c2.id=ch.cuisine_id
              OR ch.cuisine_id IS NULL AND c2.parent_category=ch.lvl)
      ) AS c_val,
      (SELECT COALESCE(SUM(
         POWER(0.5,(CURRENT_DATE-COALESCE(rv.visit_date,rv.created_at)::DATE)/180.0)
       ),0)
       FROM reviews rv
       JOIN restaurant_cuisines rc2 ON rc2.restaurant_id=rv.restaurant_id
       JOIN cuisines c2 ON c2.id=rc2.cuisine_id
       WHERE rv.review_kind='diner'
         AND COALESCE(rv.is_fake_suspect,false)=false
         AND rv.is_hidden=false
         AND COALESCE(rv.trust_level,'low') IN ('mid','high')
         AND COALESCE(rv.aspect_taste,rv.rating_taste,rv.rating_total) IS NOT NULL
         AND (ch.cuisine_id IS NOT NULL AND c2.id=ch.cuisine_id
              OR ch.cuisine_id IS NULL AND c2.parent_category=ch.lvl)
      ) AS v_val
    FROM chain ch
  )
  SELECT s.c_val, s.v_val FROM stats s
  ORDER BY (s.v_val >= 20) DESC, s.depth ASC LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;

-- ---------- BATCH 3：单店口味重算（仅真实食客 UGC） ----------
--   taste = 贝叶斯收缩到品类先验；diner = 时间加权原始均值（不收缩）；
--   review_count / confidence 只统计真实 UGC；无真实评价则四项归 NULL/0。
CREATE OR REPLACE FUNCTION recalc_taste_for(p_rest INTEGER) RETURNS void AS $$
DECLARE
  c_half_life CONSTANT numeric := 180;
  m           CONSTANT numeric := 8;
  v_R numeric; v_v numeric; v_cnt int; v_C numeric; v_nind int;
BEGIN
  SELECT cp.c_prior INTO v_C FROM cuisine_prior(p_rest) cp;

  WITH eff AS (
    SELECT (COALESCE(aspect_taste,rating_taste,rating_total)-1)/4.0*100 AS q,
           POWER(0.5,(CURRENT_DATE-COALESCE(visit_date,created_at)::DATE)/c_half_life) AS w
    FROM reviews
    WHERE restaurant_id=p_rest AND review_kind='diner'
      AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
      AND COALESCE(trust_level,'low') IN ('mid','high')          -- 仅真实 UGC
      AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL
  )
  SELECT SUM(w*q)/NULLIF(SUM(w),0), SUM(w), COUNT(*)
    INTO v_R, v_v, v_cnt FROM eff;

  SELECT COUNT(DISTINCT author_name) INTO v_nind FROM reviews
  WHERE restaurant_id=p_rest AND review_kind='diner'
    AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
    AND COALESCE(trust_level,'low') IN ('mid','high')
    AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL;

  IF v_v > 0 THEN
    UPDATE restaurants SET
      score_taste = ROUND((v_v/(v_v+m))*v_R + (m/(v_v+m))*v_C, 2),
      score_diner = ROUND(v_R, 2),
      review_count = v_cnt,
      review_confidence = ROUND(v_v/(v_v+m), 3)
    WHERE id = p_rest;
  ELSE
    UPDATE restaurants SET
      score_taste = NULL, score_diner = NULL,
      review_count = 0, review_confidence = 0
    WHERE id = p_rest;
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recalc_taste_all() RETURNS void AS $$
BEGIN
  PERFORM recalc_taste_for(id) FROM restaurants;
END;
$$ LANGUAGE plpgsql;

-- ---------- BATCH 4：derive_restaurant — 权重重排 + 证据分级 + 封顶 ----------
--   verified(≥2 独立真实食客)：0.45 taste + 0.25 diner + 0.18 objective + 0.12 endorsement
--                             （真实食客 0.70 / 平台 0.30），不封顶；
--   仅 1 名真实食客：同公式但封顶 82，标 provisional；
--   无真实评价：0.6 objective + 0.4 endorsement，封顶 70，标 provisional；
--   无任何证据：insufficient，total NULL。
CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_chain_flag TEXT; v_rev_flag TEXT; v_nondiner BOOLEAN;
  v_nind INT; v_blend NUMERIC;
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();
  IF NEW.price_avg IS NOT NULL THEN
    NEW.tier := tier_for_price(NEW.price_avg);
  END IF;

  -- chain 硬信号；非正餐豁免（保持 007 口径）
  SELECT EXISTS(SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
    WHERE rc.restaurant_id=NEW.id AND c.dimension='菜系' AND c.parent_category='非正餐')
    INTO v_nondiner;
  IF v_nondiner THEN
    v_chain_flag := 'none';
  ELSE
    v_chain_flag := CASE
      WHEN NEW.central_kitchen='确认' OR NEW.premade_risk='高' THEN 'confirmed'
      WHEN NEW.central_kitchen='疑似' OR NEW.premade_risk='疑似'
           OR NEW.chain_type IN ('资本化连锁','大型连锁') THEN 'suspected'
      ELSE 'none' END;
  END IF;
  v_rev_flag := COALESCE(NEW.soft_ad_flag_reviews, 'none');
  NEW.soft_ad_flag := CASE
    WHEN v_chain_flag='confirmed' OR v_rev_flag='confirmed' THEN 'confirmed'
    WHEN v_chain_flag='suspected' OR v_rev_flag='suspected' THEN 'suspected'
    ELSE 'none' END;
  NEW.soft_ad_penalty := CASE NEW.soft_ad_flag
    WHEN 'confirmed' THEN 25 WHEN 'suspected' THEN 10 ELSE 0 END;

  SELECT COUNT(DISTINCT author_name) INTO v_nind
  FROM reviews
  WHERE restaurant_id=NEW.id AND review_kind='diner'
    AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
    AND COALESCE(trust_level,'low') IN ('mid','high')
    AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL;

  IF NEW.score_taste IS NOT NULL AND NEW.score_diner IS NOT NULL THEN
    v_blend := 0.45*NEW.score_taste + 0.25*NEW.score_diner
             + 0.18*COALESCE(NEW.score_objective, NEW.score_taste)
             + 0.12*COALESCE(NEW.score_endorsement,0);
    IF v_nind >= 2 THEN
      NEW.score_evidence_level := 'verified';
      NEW.score_total := greatest(0, least(100, round(v_blend - NEW.soft_ad_penalty,1)));
    ELSE
      NEW.score_evidence_level := 'provisional';
      NEW.score_total := greatest(0, least(100,
        round(least(v_blend,82) - NEW.soft_ad_penalty,1)));
    END IF;
  ELSIF COALESCE(NEW.score_objective,0) > 0 OR COALESCE(NEW.score_endorsement,0) > 0 THEN
    v_blend := 0.6*COALESCE(NEW.score_objective,0) + 0.4*COALESCE(NEW.score_endorsement,0);
    NEW.score_evidence_level := 'provisional';
    NEW.score_total := greatest(0, least(100,
      round(least(v_blend,70) - NEW.soft_ad_penalty,1)));
  ELSE
    NEW.score_evidence_level := 'insufficient';
    NEW.score_total := NULL;
  END IF;
  RETURN NEW;
END $$;
-- 注：触发器 trg_restaurants_derive 已在 007 创建，函数替换即生效，无需重建。

-- ---------- BATCH 5：价格场景补全（依据标签，默认正餐） ----------
UPDATE restaurants r SET price_scene = sub.scene
FROM (
  SELECT r2.id,
    CASE
      WHEN EXISTS (SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
        WHERE rc.restaurant_id=r2.id AND c.dimension='菜系'
          AND (c.name LIKE '%咖啡%' OR c.name LIKE '%茶饮%' OR c.name LIKE '%奶茶%')) THEN '咖啡茶饮'
      WHEN EXISTS (SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
        WHERE rc.restaurant_id=r2.id AND c.dimension='菜系'
          AND (c.name LIKE '%面包%' OR c.name LIKE '%烘焙%')) THEN '面包'
      WHEN EXISTS (SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
        WHERE rc.restaurant_id=r2.id AND c.dimension='菜系'
          AND (c.name LIKE '%甜品%' OR c.name LIKE '%甜汤%' OR c.name LIKE '%冰淇淋%'
               OR c.name LIKE '%刨冰%' OR c.name LIKE '%蛋糕%' OR c.name LIKE '%gelato%')) THEN '甜品'
      WHEN EXISTS (SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
        WHERE rc.restaurant_id=r2.id AND c.dimension='菜系'
          AND (c.name LIKE '%酒吧%' OR c.name LIKE '%清吧%')) THEN '酒吧'
      ELSE '正餐'
    END AS scene
  FROM restaurants r2 WHERE r2.price_scene IS NULL
) sub WHERE r.id=sub.id;

-- ---------- BATCH 6：price_band 按场景阈值全量重算（唯一权威、补空） ----------
UPDATE restaurants r SET price_band = t.band
FROM (
  SELECT r2.id,
    (SELECT th.band FROM price_band_thresholds th
      WHERE th.scene = r2.price_scene
        AND (th.lo IS NULL OR r2.price_avg >= th.lo)
        AND (th.hi IS NULL OR r2.price_avg < th.hi)) AS band
  FROM restaurants r2
  WHERE r2.price_scene IS NOT NULL AND r2.price_avg IS NOT NULL
) t WHERE r.id=t.id AND r.price_band IS DISTINCT FROM t.band;

-- ---------- BATCH 7：全量重算口味并刷新 derive ----------
SELECT recalc_taste_all();
UPDATE restaurants SET id = id;

-- =====================================================================
-- 验证（独立 SELECT）
--   SELECT score_evidence_level, count(*) FROM restaurants GROUP BY 1;
--   SELECT count(*) FILTER (WHERE score_taste IS NOT NULL) AS taste_n,
--          count(*) FILTER (WHERE review_count>0) AS rc_n,
--          count(*) AS total FROM restaurants;
--   SELECT count(*) FILTER (WHERE price_scene IS NULL) AS scene_null,
--          count(*) FILTER (WHERE price_band IS NULL AND price_avg IS NOT NULL) AS band_null
--     FROM restaurants;
--   SELECT score_evidence_level, score_total, score_taste, review_count
--     FROM restaurants ORDER BY score_evidence_level='verified' DESC, score_total DESC NULLS LAST LIMIT 15;
-- =====================================================================
