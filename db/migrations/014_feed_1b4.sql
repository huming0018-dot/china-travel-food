-- ============================================================
-- 014_feed_1b4.sql — Track 1B-4：首页 feed 数据模型补全 + 集团/主厨 tracking
-- 目的：把首页 feed 的 7 类事件（飞行厨房/主厨新店/海外米其林入沪/海外热门入沪/
--       主厨变化/跨界联名/联合快闪）落到可筛选的数据模型；事件含开始日 + 报名入口。
-- 注意：DDL 只能在 Supabase SQL Editor 执行；REST 数据写入由 1B-4 脚本完成。
-- 幂等：全部 IF NOT EXISTS / OR REPLACE，可重复跑。
-- ============================================================

-- ------------------------------------------------------------
-- 1. food_events 缺字段：海外品牌来源 + 是否海外品牌
--    （event_date 即活动开始日 start_date；registration_url 即报名/购票入口 signup_url；
--      expires_on 即活动结束日——三者已在 010/004 存在，不再重复建列）
-- ------------------------------------------------------------
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS origin_market text;
-- e.g. '米兰'/'伦敦'/'巴黎'/'东京'/'纽约'；本土事件留 NULL
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS is_overseas_brand boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN food_events.origin_market IS '海外品牌来源地（海外米其林入沪/海外热门入沪用）；本土事件 NULL';
COMMENT ON COLUMN food_events.is_overseas_brand IS '是否海外/境外品牌入沪或快闪；与 event_subtype=海外米其林入沪/海外热门入沪配套筛选';

-- ------------------------------------------------------------
-- 2. event_subtype 受控词表（仅注释约束，应用层脚本保证取值）：
--    飞行厨房 | 主厨新店 | 海外米其林入沪 | 海外热门入沪 | 主厨变化 |
--    跨界联名 | 联合快闪 | 荣誉榜单 | 待开业 | 关店搬迁
-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- 3. 去重指纹唯一索引（1B-4 脚本已回填 dedup_fingerprint 且无重复后启用）
-- ------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup_fp
  ON food_events(dedup_fingerprint) WHERE dedup_fingerprint IS NOT NULL;

-- ------------------------------------------------------------
-- 4. v_feed_recent 视图重建：纳入 start_date/signup_url 别名与海外字段
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_feed_recent AS
SELECT
  e.id, e.scope, e.category, e.event_subtype, e.title, e.summary,
  e.event_date            AS start_date,        -- 活动开始日
  e.expires_on,                                  -- 活动结束日
  e.registration_url      AS signup_url,        -- 报名/购票入口
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

-- ------------------------------------------------------------
-- 5. chefs / groups tracking 心跳列已在 010 存在（last_tracked_at / data_updated_at），
--    由数据脚本在每轮 tracking 时刷新；此处不另建列。
-- ------------------------------------------------------------
