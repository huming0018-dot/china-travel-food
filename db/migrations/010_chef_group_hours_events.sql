-- 010_chef_group_hours_events.sql
-- 本轮9项任务的schema变更：主厨/集团profile、营业时长/日期、语义简介、事件扩展字段

-- ============================================================
-- 1. restaurants 新增字段：营业时长、营业日期、语义简介
-- ============================================================
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS opening_hours jsonb;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS open_days text;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS semantic_description text;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS chef_name text;

-- ============================================================
-- 2. restaurant_groups：餐饮集团/品牌矩阵表
-- ============================================================
CREATE TABLE IF NOT EXISTS restaurant_groups (
  id serial PRIMARY KEY,
  name text NOT NULL,
  name_en text,
  group_type text NOT NULL DEFAULT '餐饮集团',  -- 餐饮集团 / 主厨品牌 / 酒店管理集团 / 独立品牌矩阵
  founder text,
  founder_role text,
  headquarters text,
  founded_year integer,
  description text,
  website text,
  social_xhs text,
  social_wechat text,
  social_instagram text,
  data_updated_at date DEFAULT CURRENT_DATE,
  created_at timestamptz DEFAULT now(),
  UNIQUE(name)
);

-- ============================================================
-- 3. restaurant_group_members：集团-餐厅关联
-- ============================================================
CREATE TABLE IF NOT EXISTS restaurant_group_members (
  group_id integer NOT NULL REFERENCES restaurant_groups(id) ON DELETE CASCADE,
  restaurant_id integer NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  brand_name text,          -- 该店在集团内的品牌名
  role text,                -- 旗舰店/标准店/快闪店/实验店
  is_current boolean DEFAULT true,
  source_url text,
  joined_at date,
  PRIMARY KEY (group_id, restaurant_id)
);

-- ============================================================
-- 4. chefs 表扩展（如已有则跳过）
-- ============================================================
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS group_id integer REFERENCES restaurant_groups(id);
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS restaurants_owned text[];
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS culinary_background text;
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS signature_style text;
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS media_mentions integer DEFAULT 0;
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS last_tracked_at timestamptz;

-- ============================================================
-- 5. food_events 扩展字段：报名入口、标签、活动类型细化
-- ============================================================
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS registration_url text;
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS registration_info text;
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS tags text[];
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS event_subtype text;
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS dedup_fingerprint text;

-- 为去重指纹建唯一索引（允许NULL，已有重复数据先清理再加）
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup_fp ON food_events(dedup_fingerprint) WHERE dedup_fingerprint IS NOT NULL;

-- ============================================================
-- 6. v_feed_recent 视图重建：包含新字段
-- ============================================================
CREATE OR REPLACE VIEW v_feed_recent AS
SELECT
  e.id, e.scope, e.category, e.event_subtype, e.title, e.summary,
  e.event_date, e.expires_on, e.registration_url, e.registration_info,
  e.restaurant_id, e.related_restaurant_id, e.chef_id, e.city, e.district,
  e.confidence, e.status, e.tags, e.sources,
  r.name AS restaurant_name,
  c.name AS chef_name
FROM food_events e
LEFT JOIN restaurants r ON e.restaurant_id = r.id
LEFT JOIN chefs c ON e.chef_id = c.id
WHERE e.status IN ('verified', 'rumor')
ORDER BY e.event_date DESC NULLS LAST, e.created_at DESC;

-- ============================================================
-- 7. 分类标签整治：会所与私房菜拆分
-- ============================================================
-- 在 cuisines 表中新增"私房菜"（形式维度），保留"会所"
-- 先检查是否已存在，不存在则插入
INSERT INTO cuisines (name, dimension, parent_category, description)
SELECT '私房菜', '形式', '正餐', '预约制私厨/家庭厨房/个人化命名的真私厨，区别于营销"私房"'
WHERE NOT EXISTS (SELECT 1 FROM cuisines WHERE name='私房菜' AND dimension='形式');

-- 将原"私宴/会所"改名为"会所"（如存在）
UPDATE cuisines SET name='会所', description='高端会员制会所/私宴空间，通常有入会门槛或最低消费'
WHERE name='私宴/会所' AND dimension='形式';

-- 如果"会所"已存在则不重复
INSERT INTO cuisines (name, dimension, parent_category, description)
SELECT '会所', '形式', '正餐', '高端会员制会所/私宴空间，通常有入会门槛或最低消费'
WHERE NOT EXISTS (SELECT 1 FROM cuisines WHERE name='会所' AND dimension='形式');
