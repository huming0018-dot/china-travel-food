-- =====================================================================
-- 005_scoring_v3.sql — 评分引擎 v3 + 分类增量 + Social Listening 增量
-- ---------------------------------------------------------------------
-- 对应三份 v3 设计文档：
--   research/design/scoring-db-architecture-v3.md（评分+数据库架构）
--   research/design/classification-user-journey-v3.md（分类+用户旅程）
--   research/design/social-listening-chef-feed-v3.md（社交监听+主厨+Feed）
--
-- 前置迁移：001_init + 002_harden + 003_mechanism_v2 + 004_atlas_v2
-- 幂等可重跑；DDL 只能走 Supabase SQL Editor（REST 做不了 DDL）。
-- 执行后用文件末尾验证语句独立 SELECT 核对。
-- =====================================================================

-- =====================================================================
-- BATCH 1 — 分类增量：食材轴补全（v3 分类设计）
-- =====================================================================
-- 004 已建「包馅面食」父叶 + 饺子/馄饨/锅贴/生煎/小笼包/烧卖/汤圆
-- v3 补：汤包、包子；饼子叶细化；甜品父叶补甜可丽饼/舒芙蕾松饼
INSERT INTO cuisines (name, dimension, parent_category) VALUES
  ('汤包','食材','包馅面食'),
  ('包子','食材','包馅面食'),
  ('中式烙烤饼','食材','饼'),
  ('咸galette','食材','饼'),
  ('甜可丽饼','食材','甜品'),
  ('舒芙蕾松饼','食材','甜品')
ON CONFLICT (name, dimension, (COALESCE(parent_category,''))) DO NOTHING;

-- =====================================================================
-- BATCH 2 — Social Listening 增量列
-- =====================================================================
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS last_listened_at TIMESTAMPTZ;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS freshness_due DATE;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS taste_prior_source TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS soft_ad_flag TEXT DEFAULT 'none';

ALTER TABLE chefs ADD COLUMN IF NOT EXISTS mentor_ids INTEGER[];
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS tracking_seeds JSONB;

ALTER TABLE food_events ADD COLUMN IF NOT EXISTS expires_on DATE;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_softadflag') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_softadflag
      CHECK (soft_ad_flag IS NULL OR soft_ad_flag IN ('none','suspected','confirmed'));
  END IF;
END $$;

-- awards award_type 枚举 CHECK
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_awards_type') THEN
    ALTER TABLE restaurant_awards ADD CONSTRAINT ch_awards_type
      CHECK (award_type IN ('michelin_star','bib_gourmand','black_pearl','media_show','other_list'));
  END IF;
END $$;

-- awards 唯一索引（同店同类型同年只一条）
CREATE UNIQUE INDEX IF NOT EXISTS uq_awards_rest_type_year
  ON restaurant_awards (restaurant_id, award_type, COALESCE(year,0));

-- =====================================================================
-- BATCH 3 — 升级综合分权重（0.35 taste / 0.25 objective / 0.25 diner / 0.15 endorsement）
--   取代 004 之前的 0.4/0.3/0.2/0.1；taste 成为核心
-- =====================================================================
CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();
  IF NEW.price_avg IS NOT NULL THEN
    NEW.tier := tier_for_price(NEW.price_avg);
  END IF;
  IF NEW.score_objective IS NULL OR NEW.score_diner IS NULL
     OR NEW.score_taste IS NULL OR NEW.score_endorsement IS NULL THEN
    NEW.score_total := NULL;
  ELSE
    NEW.score_total := greatest(0, least(100, round(
        0.35*NEW.score_taste
      + 0.25*NEW.score_objective
      + 0.25*NEW.score_diner
      + 0.15*NEW.score_endorsement
      - coalesce(NEW.soft_ad_penalty,0), 1)));
  END IF;
  RETURN NEW;
END $$;

-- =====================================================================
-- BATCH 4 — 品类先验函数（同品类均值，样本不足上溯父类）
--   修正 004 用全局均值的问题：寿司店和拉面店不再共享先验
-- =====================================================================
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

-- =====================================================================
-- BATCH 5 — 单店口味重算（时间衰减 + 贝叶斯收缩到品类先验）
--   五原则落地：①只算diner+非软广+未隐藏 ②v/(v+m)显式置信度
--               ③w=0.5^(age/180)近期权重高 ④aspect_taste只含菜品评价
-- =====================================================================
CREATE OR REPLACE FUNCTION recalc_taste_for(p_rest INTEGER) RETURNS void AS $$
DECLARE
  c_half_life CONSTANT numeric := 180;
  m           CONSTANT numeric := 8;
  v_R numeric; v_v numeric; v_cnt int; v_C numeric;
BEGIN
  SELECT cp.c_prior INTO v_C FROM cuisine_prior(p_rest) cp;

  WITH eff AS (
    SELECT (COALESCE(aspect_taste,rating_taste,rating_total)-1)/4.0*100 AS q,
           POWER(0.5,(CURRENT_DATE-COALESCE(visit_date,created_at)::DATE)/c_half_life) AS w
    FROM reviews
    WHERE restaurant_id=p_rest AND review_kind='diner'
      AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
      AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL
  )
  SELECT SUM(w*q)/NULLIF(SUM(w),0), SUM(w), COUNT(*)
    INTO v_R, v_v, v_cnt FROM eff;

  IF v_v > 0 THEN
    UPDATE restaurants SET
      score_taste = ROUND((v_v/(v_v+m))*v_R + (m/(v_v+m))*v_C, 2),
      review_count = v_cnt,
      review_confidence = ROUND(v_v/(v_v+m), 3)
    WHERE id = p_rest;
  ELSE
    UPDATE restaurants SET review_count=0, review_confidence=0 WHERE id=p_rest;
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recalc_taste_all() RETURNS void AS $$
BEGIN
  PERFORM recalc_taste_for(id) FROM restaurants;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- BATCH 6 — 背书分自动派生（从 restaurant_awards 触发器，取代手填）
-- =====================================================================
CREATE OR REPLACE FUNCTION recalc_endorsement_for(p_rest INTEGER) RETURNS void AS $$
DECLARE v_endorse numeric;
BEGIN
  SELECT MAX(CASE
    WHEN award_type='michelin_star' AND level LIKE '%三%' THEN 100
    WHEN award_type='michelin_star' AND level LIKE '%二%' THEN 90
    WHEN award_type='michelin_star' AND level LIKE '%一%' THEN 80
    WHEN award_type='black_pearl' AND level LIKE '%三%' THEN 90
    WHEN award_type='black_pearl' AND level LIKE '%二%' THEN 75
    WHEN award_type='black_pearl' AND level LIKE '%一%' THEN 60
    WHEN award_type='bib_gourmand' THEN 65
    WHEN award_type='media_show' THEN 50
    WHEN award_type='other_list' THEN 40
    ELSE 40 END) INTO v_endorse
  FROM restaurant_awards
  WHERE restaurant_id=p_rest AND is_current=true;

  UPDATE restaurants SET score_endorsement = COALESCE(v_endorse, 0)
  WHERE id=p_rest;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recalc_endorsement_all() RETURNS void AS $$
BEGIN
  PERFORM recalc_endorsement_for(id) FROM restaurants;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- BATCH 7 — 触发器：reviews 变 → 刷新 taste；awards 变 → 刷新 endorsement
-- =====================================================================
CREATE OR REPLACE FUNCTION trg_reviews_taste() RETURNS trigger AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    PERFORM recalc_taste_for(OLD.restaurant_id);
  ELSE
    PERFORM recalc_taste_for(NEW.restaurant_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reviews_taste ON reviews;
CREATE TRIGGER trg_reviews_taste
  AFTER INSERT OR UPDATE OR DELETE ON reviews
  FOR EACH ROW EXECUTE FUNCTION trg_reviews_taste();

CREATE OR REPLACE FUNCTION trg_awards_endorsement() RETURNS trigger AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    PERFORM recalc_endorsement_for(OLD.restaurant_id);
  ELSE
    PERFORM recalc_endorsement_for(NEW.restaurant_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_awards_endorsement ON restaurant_awards;
CREATE TRIGGER trg_awards_endorsement
  AFTER INSERT OR UPDATE OR DELETE ON restaurant_awards
  FOR EACH ROW EXECUTE FUNCTION trg_awards_endorsement();

-- =====================================================================
-- BATCH 8 — 索引（列表/地图/搜索三模式）
-- =====================================================================
CREATE INDEX IF NOT EXISTS idx_rest_list
  ON restaurants (score_total DESC) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_rc_cuisine_primary
  ON restaurant_cuisines (cuisine_id, is_primary DESC);
CREATE INDEX IF NOT EXISTS idx_rest_aliases ON restaurants USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_reviews_effective
  ON reviews (restaurant_id, visit_date DESC)
  WHERE review_kind='diner'
    AND COALESCE(is_fake_suspect,false)=false
    AND is_hidden=false
    AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rest_district_tier
  ON restaurants (district, tier, score_total DESC) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_events_expires
  ON food_events (expires_on) WHERE expires_on IS NOT NULL;

-- pg_trgm（中文模糊搜索；Supabase 不支持 zhparser，务实替代）
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_rest_name_trgm
  ON restaurants USING GIN (lower(name) gin_trgm_ops);

-- =====================================================================
-- BATCH 9 — 只读视图（详情聚合 + Feed）
-- =====================================================================
CREATE OR REPLACE VIEW restaurant_detail_view
WITH (security_invoker=on) AS
SELECT r.*,
  ST_X(r.location::geometry) AS lng,
  ST_Y(r.location::geometry) AS lat,
  (SELECT array_agg(c.name ORDER BY rc.is_primary DESC, c.name)
   FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
   WHERE rc.restaurant_id=r.id AND c.dimension='菜系') AS cuisine_arr,
  (SELECT array_agg(c.name ORDER BY c.name)
   FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
   WHERE rc.restaurant_id=r.id AND c.dimension='形式') AS form_arr,
  (SELECT array_agg(c.name ORDER BY c.name)
   FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
   WHERE rc.restaurant_id=r.id AND c.dimension='食材') AS ingredient_arr,
  (SELECT jsonb_agg(jsonb_build_object('award_type',a.award_type,'level',a.level,'year',a.year)
                    ORDER BY a.year DESC NULLS LAST)
   FROM restaurant_awards a WHERE a.restaurant_id=r.id AND a.is_current=true) AS awards,
  (SELECT jsonb_agg(jsonb_build_object('name',ch.name,'title',ch.title,'role',rc2.role))
   FROM restaurant_chefs rc2 JOIN chefs ch ON ch.id=rc2.chef_id
   WHERE rc2.restaurant_id=r.id AND rc2.is_current=true) AS chefs,
  (SELECT jsonb_agg(jsonb_build_object('author',rv.author_name,'rating',rv.aspect_taste,
       'source',rv.source_platform,'url',rv.source_url,'visit_date',rv.visit_date,
       'excerpt',left(rv.content,120)))
   FROM (SELECT * FROM reviews
         WHERE restaurant_id=r.id AND review_kind='diner'
           AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
         ORDER BY visit_date DESC NULLS LAST LIMIT 5) rv) AS recent_reviews
FROM restaurants r;
GRANT SELECT ON restaurant_detail_view TO anon, authenticated;

CREATE OR REPLACE VIEW feed_view
WITH (security_invoker=on) AS
SELECT fe.id, fe.scope, fe.category, fe.title, fe.summary, fe.event_date, fe.expires_on,
       fe.restaurant_id, fe.related_restaurant_id, fe.chef_id,
       r.name AS restaurant_name, ch.name AS chef_name,
       fe.district, fe.confidence, fe.status
FROM food_events fe
LEFT JOIN restaurants r ON r.id=fe.restaurant_id
LEFT JOIN chefs ch ON ch.id=fe.chef_id
WHERE fe.event_date IS NOT NULL AND fe.status='verified'
  AND (fe.expires_on IS NULL OR fe.expires_on >= CURRENT_DATE)
ORDER BY fe.event_date DESC, fe.id DESC;
GRANT SELECT ON feed_view TO anon, authenticated;

-- =====================================================================
-- BATCH 10 — 回填（执行一次，取消注释）
-- =====================================================================
-- SELECT recalc_taste_all();
-- SELECT recalc_endorsement_all();

-- =====================================================================
-- 验证（独立 SELECT，确认批次生效）
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--   WHERE table_name IN ('chefs','restaurant_chefs','restaurant_awards','food_events');
-- SELECT column_name FROM information_schema.columns WHERE table_name='restaurants'
--   AND column_name IN ('taste_prior_source','soft_ad_flag','last_listened_at','freshness_due','review_confidence');
-- SELECT column_name FROM information_schema.columns WHERE table_name='chefs'
--   AND column_name IN ('mentor_ids','tracking_seeds');
-- SELECT name,parent_category FROM cuisines WHERE dimension='食材'
--   AND (parent_category IN ('包馅面食','饼','甜品'));
-- SELECT proname FROM pg_proc WHERE proname IN ('recalc_taste_for','cuisine_prior','recalc_endorsement_for');
-- SELECT id,name,score_taste,review_count,review_confidence
--   FROM restaurants WHERE status='active' ORDER BY review_confidence DESC NULLS LAST LIMIT 10;
-- SELECT count(*) FILTER (WHERE review_confidence<0.2) AS low_conf,
--        count(*) FILTER (WHERE review_confidence>=0.5) AS high_conf,
--        count(*) AS total FROM restaurants;
-- =====================================================================
