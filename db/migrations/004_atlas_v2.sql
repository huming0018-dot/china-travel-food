-- =====================================================================
-- 004_atlas_v2.sql — 美食图鉴架构升级 v2（Atlas）
-- ---------------------------------------------------------------------
-- 对应 architecture-v2-atlas.md 的 5 项升级：
--   1) user journey 分类：食材叶子「包馅面食」+「饼」细分
--   2) social listening：food_events 事件 / feed（含搬迁建模）
--   3) 主厨 / 卖点 / 荣誉建档：chefs / restaurant_chefs / restaurant_awards
--   4) 首页动态 feed：复用 food_events
--   5) 评分五原则：reviews 加方面 / 真实性字段 + taste 评分引擎
--
-- 幂等可重复执行；DDL 只能走 Supabase SQL Editor（REST 做不了 DDL）。
-- 执行后用文件末尾的验证语句独立 SELECT 核对。
-- =====================================================================

-- =====================================================================
-- BATCH 1 — 人事域：chefs / restaurant_chefs
-- =====================================================================
CREATE TABLE IF NOT EXISTS chefs (
  id            SERIAL PRIMARY KEY,
  name          VARCHAR(100) NOT NULL,
  name_en       VARCHAR(100),
  title         VARCHAR(100),
  bio           TEXT,
  origin        VARCHAR(150),
  is_traveling  BOOLEAN DEFAULT false,
  social_xhs    VARCHAR(100),
  social_douyin VARCHAR(100),
  social_weibo  VARCHAR(100),
  reputation    JSONB,
  data_updated_at DATE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS restaurant_chefs (
  restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
  chef_id       INTEGER REFERENCES chefs(id) ON DELETE CASCADE,
  role          VARCHAR(40) NOT NULL DEFAULT '主厨',
  is_current    BOOLEAN DEFAULT true,
  started       DATE,
  ended         DATE,
  source_url    TEXT,
  PRIMARY KEY (restaurant_id, chef_id, role)
);
CREATE INDEX IF NOT EXISTS idx_rchefs_chef ON restaurant_chefs(chef_id);

-- =====================================================================
-- BATCH 2 — 荣誉域：restaurant_awards
-- =====================================================================
CREATE TABLE IF NOT EXISTS restaurant_awards (
  id           SERIAL PRIMARY KEY,
  restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
  award_type   VARCHAR(40) NOT NULL,  -- michelin_star/black_pearl/bib_gourmand/media_show/other
  level        VARCHAR(40),           -- 三星/二星/一星/三钻/二钻/一钻/冠军/入选...
  year         INTEGER,
  season       VARCHAR(40),
  is_current   BOOLEAN DEFAULT true,
  source_url   TEXT,
  source_name  VARCHAR(100),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_awards_rest ON restaurant_awards(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_awards_current
  ON restaurant_awards(is_current) WHERE is_current;

-- =====================================================================
-- BATCH 3 — 事件 / Feed 域：food_events
-- =====================================================================
CREATE TABLE IF NOT EXISTS food_events (
  id                    SERIAL PRIMARY KEY,
  scope                 VARCHAR(20) NOT NULL DEFAULT 'local',   -- local/overseas/industry
  category              VARCHAR(30) NOT NULL,                   -- new_open/relocated/closed/chef_changed/guest_kitchen/collaboration/popup/award/menu_update/coming_soon
  title                 VARCHAR(200) NOT NULL,
  summary               TEXT,
  event_date            DATE,
  restaurant_id         INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
  related_restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE SET NULL,
  chef_id               INTEGER REFERENCES chefs(id) ON DELETE SET NULL,
  city                  VARCHAR(50),
  district              VARCHAR(50),
  sources               JSONB DEFAULT '[]',
  confidence            VARCHAR(10) DEFAULT 'mid',              -- high/mid/low
  status                VARCHAR(10) DEFAULT 'verified',          -- verified/rumor
  created_at            TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_date ON food_events(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_events_rest ON food_events(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_events_cat ON food_events(category);

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_events_scope') THEN
    ALTER TABLE food_events ADD CONSTRAINT ch_events_scope
      CHECK (scope IN ('local','overseas','industry')); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_events_conf') THEN
    ALTER TABLE food_events ADD CONSTRAINT ch_events_conf
      CHECK (confidence IN ('high','mid','low')); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_events_status') THEN
    ALTER TABLE food_events ADD CONSTRAINT ch_events_status
      CHECK (status IN ('verified','rumor')); END IF;
END $$;

-- =====================================================================
-- BATCH 4 — restaurants / reviews 加列 + CHECK
-- =====================================================================
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS selling_points    JSONB;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS aliases           TEXT[];
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS review_count      INTEGER DEFAULT 0;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS review_confidence NUMERIC(4,3) DEFAULT 0;

ALTER TABLE reviews ADD COLUMN IF NOT EXISTS source_platform    TEXT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS source_url         TEXT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS review_kind        TEXT DEFAULT 'diner';
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS is_verified_diner  BOOLEAN DEFAULT false;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS trust_level        TEXT DEFAULT 'mid';
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS is_fake_suspect    BOOLEAN DEFAULT false;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS aspect_taste       INT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS aspect_service     INT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS aspect_env         INT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS aspect_value       INT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS aspect_json        JSONB;

-- 历史登录用户评论默认按真实堂食处理
UPDATE reviews SET review_kind='diner', is_verified_diner=true, trust_level='mid'
  WHERE review_kind IS NULL OR review_kind='';

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_reviews_kind') THEN
    ALTER TABLE reviews ADD CONSTRAINT ch_reviews_kind
      CHECK (review_kind IS NULL OR review_kind IN ('diner','takeaway','press')); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_reviews_trust') THEN
    ALTER TABLE reviews ADD CONSTRAINT ch_reviews_trust
      CHECK (trust_level IS NULL OR trust_level IN ('high','mid','low')); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rconf') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rconf
      CHECK (review_confidence BETWEEN 0 AND 1); END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_aspect_taste') THEN
    ALTER TABLE reviews ADD CONSTRAINT ch_aspect_taste CHECK (aspect_taste IS NULL OR aspect_taste BETWEEN 1 AND 5); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_aspect_service') THEN
    ALTER TABLE reviews ADD CONSTRAINT ch_aspect_service CHECK (aspect_service IS NULL OR aspect_service BETWEEN 1 AND 5); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_aspect_env') THEN
    ALTER TABLE reviews ADD CONSTRAINT ch_aspect_env CHECK (aspect_env IS NULL OR aspect_env BETWEEN 1 AND 5); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_aspect_value') THEN
    ALTER TABLE reviews ADD CONSTRAINT ch_aspect_value CHECK (aspect_value IS NULL OR aspect_value BETWEEN 1 AND 5); END IF;
END $$;

-- =====================================================================
-- BATCH 5 — 食材叶子：包馅面食 + 饼细分（user journey 分类）
-- =====================================================================
INSERT INTO cuisines (name, dimension, parent_category) VALUES
  ('包馅面食','食材',NULL),
  ('饺子','食材','包馅面食'),
  ('馄饨','食材','包馅面食'),
  ('锅贴','食材','包馅面食'),
  ('生煎','食材','包馅面食'),
  ('小笼包','食材','包馅面食'),
  ('烧卖','食材','包馅面食'),
  ('汤圆','食材','包馅面食'),
  ('饼','食材',NULL),
  ('烧饼','食材','饼'),
  ('葱油饼','食材','饼'),
  ('手抓饼','食材','饼'),
  ('可丽饼','食材','饼'),
  ('薄饼','食材','饼')
ON CONFLICT (name, dimension, (COALESCE(parent_category,''))) DO NOTHING;

-- =====================================================================
-- BATCH 6 — 评分引擎：taste（时间衰减 + 贝叶斯 + 方面甄别）
-- =====================================================================
-- 单店重算：v=有效(衰减)评论数，R=衰减加权口味，C=全局先验，m=8
CREATE OR REPLACE FUNCTION recalc_taste_for(p_rest INTEGER) RETURNS void AS $$
DECLARE
  v_R numeric; v_v numeric; v_cnt int; v_C numeric;
BEGIN
  WITH eff AS (
    SELECT (COALESCE(aspect_taste, rating_taste, rating_total)-1)/4.0*100 AS q,
           POWER(0.5, (CURRENT_DATE - COALESCE(visit_date, created_at)::DATE)/180.0) AS w
    FROM reviews
    WHERE review_kind='diner' AND COALESCE(is_fake_suspect,false)=false
      AND is_hidden=false AND COALESCE(aspect_taste, rating_taste, rating_total) IS NOT NULL
  ) SELECT COALESCE(SUM(w*q)/NULLIF(SUM(w),0), 70) INTO v_C FROM eff;

  WITH eff AS (
    SELECT (COALESCE(aspect_taste, rating_taste, rating_total)-1)/4.0*100 AS q,
           POWER(0.5, (CURRENT_DATE - COALESCE(visit_date, created_at)::DATE)/180.0) AS w
    FROM reviews
    WHERE restaurant_id=p_rest AND review_kind='diner'
      AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
      AND COALESCE(aspect_taste, rating_taste, rating_total) IS NOT NULL
  ) SELECT SUM(w*q)/NULLIF(SUM(w),0), SUM(w), COUNT(*) INTO v_R,v_v,v_cnt FROM eff;

  IF v_v > 0 THEN
    UPDATE restaurants SET
      score_taste = ROUND((v_v/(v_v+8))*v_R + (8/(v_v+8))*v_C, 2),
      review_count = v_cnt,
      review_confidence = ROUND(v_v/(v_v+8),3)
    WHERE id=p_rest;
  ELSE
    -- 评论回填前保留原采集 score_taste，仅标记低置信
    UPDATE restaurants SET review_count=0, review_confidence=0 WHERE id=p_rest;
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recalc_taste_all() RETURNS void AS $$
BEGIN
  PERFORM recalc_taste_for(id) FROM restaurants;
END;
$$ LANGUAGE plpgsql;

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
CREATE TRIGGER trg_reviews_taste AFTER INSERT OR UPDATE OR DELETE ON reviews
  FOR EACH ROW EXECUTE FUNCTION trg_reviews_taste();

-- =====================================================================
-- BATCH 7 — RLS：新表公开 SELECT、无写策略（写仅 service_role）
-- =====================================================================
ALTER TABLE chefs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurant_chefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurant_awards ENABLE ROW LEVEL SECURITY;
ALTER TABLE food_events      ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='chefs' AND policyname='chefs_public_read') THEN
    CREATE POLICY chefs_public_read ON chefs FOR SELECT USING (true); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='restaurant_chefs' AND policyname='rchefs_public_read') THEN
    CREATE POLICY rchefs_public_read ON restaurant_chefs FOR SELECT USING (true); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='restaurant_awards' AND policyname='awards_public_read') THEN
    CREATE POLICY awards_public_read ON restaurant_awards FOR SELECT USING (true); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='food_events' AND policyname='events_public_read') THEN
    CREATE POLICY events_public_read ON food_events FOR SELECT USING (true); END IF;
END $$;

-- 首页 feed 便捷视图（公开）
CREATE OR REPLACE VIEW v_feed_recent WITH (security_invoker=on) AS
SELECT id, scope, category, title, summary, event_date,
       restaurant_id, related_restaurant_id, chef_id, district, confidence, status
FROM food_events
WHERE event_date IS NOT NULL
ORDER BY event_date DESC, id DESC;
GRANT SELECT ON v_feed_recent TO anon, authenticated;

-- =====================================================================
-- 验证（独立 SELECT，确认批次生效）
-- =====================================================================
-- SELECT table_name FROM information_schema.tables
--   WHERE table_name IN ('chefs','restaurant_chefs','restaurant_awards','food_events');
-- SELECT column_name FROM information_schema.columns WHERE table_name='reviews'
--   AND column_name IN ('review_kind','aspect_taste','trust_level','is_fake_suspect');
-- SELECT name,parent_category FROM cuisines WHERE dimension='食材'
--   AND (name='包馅面食' OR parent_category IN ('包馅面食','饼'));
-- SELECT recalc_taste_all();
-- SELECT count(*) FILTER (WHERE review_confidence>0) AS confident,
--        count(*) AS total FROM restaurants;
-- =====================================================================
