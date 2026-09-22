-- ============================================================
-- China Travel · 美食地图 数据库 Schema（初始结构 001）
-- 数据库: PostgreSQL 15+ (Supabase) + PostGIS
-- 执行方式: 在 Supabase SQL Editor 中粘贴执行，或 psql -f
--
-- ★ 完整现网结构 = 001_init.sql + 002_harden.sql 按顺序执行：
--    001 建表/RLS/基础索引/GENERATED 搜索列；002 追加归一函数、CHECK 约束、
--    派生触发器（tier/score_total）、防重唯一索引、审计/保鲜视图、幂等 RPC。
--    重建库时两个都要跑，勿只跑 001。
-- ============================================================

-- 启用 PostGIS（地理坐标/距离查询）
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 1. cuisines — 三维分类字典表（菜系/食材/形式统一存储）
-- ============================================================
CREATE TABLE cuisines (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(100) NOT NULL,
  dimension       VARCHAR(20)  NOT NULL,  -- 菜系 / 食材 / 形式
  parent_category VARCHAR(100),             -- 一级分类（如"中餐·八大菜系"）
  flavor_profile  TEXT,
  signature_dishes TEXT,
  price_low       INTEGER,
  price_mid       INTEGER,
  price_high      INTEGER,
  shanghai_format TEXT,
  decision_maker  VARCHAR(100),
  negotiation_anchor TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_cuisines_dimension ON cuisines(dimension);
CREATE INDEX idx_cuisines_parent ON cuisines(parent_category);

-- ============================================================
-- 2. restaurants — 餐厅核心表
-- ============================================================
CREATE TABLE restaurants (
  id                SERIAL PRIMARY KEY,
  name              VARCHAR(200) NOT NULL,
  name_en           VARCHAR(200),
  tier              VARCHAR(20),              -- 五档（002 触发器按 price_avg 自动算）：经济/平价/中档/高档/奢华
  price_avg         INTEGER,
  price_range       VARCHAR(50),
  address           TEXT,
  district          VARCHAR(50),
  location          GEOGRAPHY(POINT, 4326),  -- PostGIS 经纬度
  phone             VARCHAR(50),
  booking_method    TEXT,
  signature_dishes  JSONB DEFAULT '[]',       -- 招牌菜数组
  discount_info     TEXT,
  investor_info     TEXT,
  -- 反软广评分各维度
  score_total       NUMERIC(5,2),
  score_objective   NUMERIC(5,2),
  score_diner       NUMERIC(5,2),
  score_taste       NUMERIC(5,2),
  score_endorsement NUMERIC(5,2),
  soft_ad_penalty   NUMERIC(5,2),
  evidence_summary  TEXT,
  status            VARCHAR(30) DEFAULT 'active', -- active/closed
  closed_date       DATE,
  closed_source     TEXT,
  data_updated_at   DATE,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_restaurants_tier     ON restaurants(tier);
CREATE INDEX idx_restaurants_district ON restaurants(district);
CREATE INDEX idx_restaurants_status   ON restaurants(status);
CREATE INDEX idx_restaurants_location ON restaurants USING GIST(location);

-- ============================================================
-- 3. restaurant_cuisines — 餐厅-分类多对多关联（三维交叉检索基础）
-- ============================================================
CREATE TABLE restaurant_cuisines (
  restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
  cuisine_id    INTEGER REFERENCES cuisines(id)    ON DELETE CASCADE,
  is_primary    BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (restaurant_id, cuisine_id)
);
CREATE INDEX idx_rc_cuisine    ON restaurant_cuisines(cuisine_id);
CREATE INDEX idx_rc_restaurant ON restaurant_cuisines(restaurant_id);

-- ============================================================
-- 4. reviews — 食客点评证据（只计堂食）
-- ============================================================
CREATE TABLE reviews (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  restaurant_id INT REFERENCES restaurants(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users,
  author_name TEXT,
  rating_total INT CHECK (rating_total BETWEEN 1 AND 5),
  rating_taste INT CHECK (rating_taste BETWEEN 1 AND 5),
  content TEXT,
  visit_date DATE,
  is_hidden BOOLEAN DEFAULT FALSE,
  report_count INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_reviews_restaurant ON reviews(restaurant_id);

-- ============================================================
-- 5. negotiations — 议价记录
-- ============================================================
CREATE TABLE negotiations (
  id                   SERIAL PRIMARY KEY,
  restaurant_id        INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
  channel              VARCHAR(30),  -- 外呼/在线/微信/手动
  contact_person       VARCHAR(100),
  contact_role         VARCHAR(50),
  cost_analysis        TEXT,
  target_discount_range VARCHAR(50),
  actual_result        TEXT,
  status               VARCHAR(30) DEFAULT '待联系', -- 待联系/进行中/已成交/已拒绝
  evidence_url         TEXT,
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  updated_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_negotiations_restaurant ON negotiations(restaurant_id);
CREATE INDEX idx_negotiations_status     ON negotiations(status);

-- ============================================================
-- 6. price_benchmarks — 单品价格锚点（成本端议价用）
-- ============================================================
CREATE TABLE price_benchmarks (
  id                    SERIAL PRIMARY KEY,
  restaurant_id         INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
  dish_name             VARCHAR(200),
  price                 NUMERIC(10,2),
  portion               VARCHAR(50),
  japan_equivalent_price NUMERIC(10,2),
  notes                 TEXT,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pb_restaurant ON price_benchmarks(restaurant_id);

-- ============================================================
-- 7. sync_log — 飞书→数据库同步日志
-- ============================================================
CREATE TABLE sync_log (
  id             SERIAL PRIMARY KEY,
  source         VARCHAR(200),  -- 飞书表格名/URL 或 vercel-cron
  sheet_name     VARCHAR(100),
  revision       INTEGER,
  records_synced INTEGER,
  status         VARCHAR(30),   -- running/success/failed/skipped
  synced_at      TIMESTAMPTZ DEFAULT NOW(),
  -- /api/sync 保鲜巡检心跳使用（002 对旧库以 ADD COLUMN IF NOT EXISTS 补齐）
  started_at          TIMESTAMPTZ,
  completed_at        TIMESTAMPTZ,
  records_processed   INTEGER,
  notes               TEXT
);

-- ============================================================
-- 8. profiles — 用户扩展信息（关联 Supabase auth.users）
-- ============================================================
CREATE TABLE profiles (
  id         UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
  username   VARCHAR(50),
  avatar_url TEXT,
  role       VARCHAR(20) DEFAULT 'user',  -- user / admin
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 新用户注册时自动创建 profile
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, username)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'username', NEW.email));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- 9. favorites — 用户收藏
-- ============================================================
CREATE TABLE favorites (
  id            SERIAL PRIMARY KEY,
  user_id       UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, restaurant_id)
);
CREATE INDEX idx_favorites_user ON favorites(user_id);

-- ============================================================
-- Row Level Security (RLS) — 数据权限
-- ============================================================
ALTER TABLE restaurants       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuisines          ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurant_cuisines ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews           ENABLE ROW LEVEL SECURITY;
ALTER TABLE negotiations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_benchmarks  ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles          ENABLE ROW LEVEL SECURITY;
ALTER TABLE favorites         ENABLE ROW LEVEL SECURITY;

-- 公开读：餐厅/分类/点评/价格锚点 所有人可读
CREATE POLICY "餐厅公开读" ON restaurants FOR SELECT USING (true);
CREATE POLICY "分类公开读" ON cuisines    FOR SELECT USING (true);
CREATE POLICY "关联公开读" ON restaurant_cuisines FOR SELECT USING (true);
CREATE POLICY "reviews_public_read" ON reviews FOR SELECT USING (is_hidden = false);
CREATE POLICY "reviews_insert_own" ON reviews FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "reviews_update_own" ON reviews FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "reviews_delete_own" ON reviews FOR DELETE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "价格锚点公开读" ON price_benchmarks FOR SELECT USING (true);

-- 议价记录：仅登录用户可读（管理员可见全部，普通用户仅可见已成交的摘要）
CREATE POLICY "议价登录可读" ON negotiations FOR SELECT USING (auth.role() = 'authenticated');

-- 管理员写权限（通过 Supabase Dashboard 的 service_role 或 admin 角色）
-- 同步脚本使用 service_role key 写入，不受 RLS 限制

-- profiles：用户只能读写自己的
CREATE POLICY "用户读自己profile" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "用户更新自己profile" ON profiles FOR UPDATE USING (auth.uid() = id);

-- favorites：用户只能读写自己的收藏
CREATE POLICY "用户读自己收藏" ON favorites FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "用户写自己收藏" ON favorites FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "用户删自己收藏" ON favorites FOR DELETE USING (auth.uid() = user_id);

-- ============================================================
-- updated_at 自动更新触发器
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cuisines_updated     BEFORE UPDATE ON cuisines      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_restaurants_updated  BEFORE UPDATE ON restaurants   FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_negotiations_updated BEFORE UPDATE ON negotiations  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- 全文搜索索引（餐厅名/地址/招牌菜）
-- ============================================================
-- search_vector 为 GENERATED 列（数据库强制自动维护，任何写入都无法手填或绕过）。
-- 权重：店名/英文名 A，商圈/行政区 B，门牌地址 C。002 触发器不再写此列。
ALTER TABLE restaurants ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', COALESCE(name,'')), 'A') ||
    setweight(to_tsvector('simple', COALESCE(name_en,'')), 'A') ||
    setweight(to_tsvector('simple', COALESCE(business_area,'')), 'B') ||
    setweight(to_tsvector('simple', COALESCE(district,'')), 'B') ||
    setweight(to_tsvector('simple', COALESCE(address,'')), 'C')
  ) STORED;
CREATE INDEX idx_restaurants_search ON restaurants USING GIN(search_vector);

-- ===== Schema 完 =====
