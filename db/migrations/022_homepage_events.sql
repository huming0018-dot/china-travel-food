-- ============================================================
-- 022_homepage_events.sql — 批次5·首页动态数据层补全
-- 目的：补 014 未落库的海外品牌字段、新增首页动态筛选用索引，并把本批
--       已写入 food_events 的海外品牌行回填 is_overseas_brand/origin_market。
-- 注意：DDL 只能在 Supabase SQL Editor 执行；REST 数据写入由 022 配套脚本完成。
-- 幂等：全部 IF NOT EXISTS / OR REPLACE，可重复跑。
-- 背景：live 库核查（2026-09-30）food_events 尚无 origin_market / is_overseas_brand，
--       说明 014_feed_1b4.sql 的这两列尚未在 SQL Editor 执行；本迁移补齐，重复执行无害。
-- ============================================================

-- ------------------------------------------------------------
-- 1. 海外品牌字段（与 014 同义，幂等）
-- ------------------------------------------------------------
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS origin_market text;
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS is_overseas_brand boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN food_events.origin_market IS '海外品牌来源地（海外米其林入沪/海外热门入沪用）；本土事件 NULL';
COMMENT ON COLUMN food_events.is_overseas_brand IS '是否海外/境外品牌入沪或快闪；与 event_subtype=海外米其林入沪/海外热门入沪配套筛选';

-- ------------------------------------------------------------
-- 2. event_subtype 受控词表（应用层保证取值；此处仅文档注释）：
--    飞行厨房 | 主厨新店 | 新店开业 | 重新开业 | 海外米其林入沪 | 海外热门入沪 |
--    主厨变化 | 跨界联名 | 联合快闪 | 荣誉榜单 | 待开业 | 关店搬迁 | 通告
--    （本批新增「新店开业 / 重新开业 / 通告」三个取值，category 新增 announcement）
-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- 3. 本批数据回填：曼谷 Tribe Sky Beach Club 中国首店
--    （写入脚本当时两列尚不存在，先入库后补标；按标题幂等匹配）
-- ------------------------------------------------------------
UPDATE food_events
   SET is_overseas_brand = true,
       origin_market     = '曼谷'
 WHERE category IN ('coming_soon','new_open')
   AND title LIKE '%Tribe Sky Beach Club%'
   AND origin_market IS NULL;

-- ------------------------------------------------------------
-- 4. 首页动态筛选用索引（标签 GIN + 未过期窗口）
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_events_tags_gin ON food_events USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_events_open_window
  ON food_events(event_date DESC)
  WHERE status = 'verified';

-- ------------------------------------------------------------
-- 5. v_feed_recent 视图重建（与 014 同义，补 tags GIN 后字段不变）
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_feed_recent AS
SELECT
  e.id, e.scope, e.category, e.event_subtype, e.title, e.summary,
  e.event_date            AS start_date,
  e.expires_on,
  e.registration_url      AS signup_url,
  e.registration_info,
  e.origin_market,
  e.is_overseas_brand,
  e.restaurant_id, e.related_restaurant_id, e.chef_id, e.city, e.district,
  e.confidence, e.status, e.tags, e.sources,
  r.name AS restaurant_name,
  c.name AS chef_name
FROM food_events e
LEFT JOIN restaurants r ON e.restaurant_id = r.id
LEFT JOIN chefs c ON e.chef_id = c.id
WHERE e.status IN ('verified', 'rumor')
ORDER BY e.event_date DESC NULLS LAST, e.created_at DESC;
