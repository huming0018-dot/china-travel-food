-- =====================================================================
-- 003_mechanism_v2.sql — 美食图鉴机制升级 v2
-- ---------------------------------------------------------------------
-- 对应 5 类机制缺陷：
--   1) social listening（综艺/名厨/私房菜/本地老饕）——发现端，见 skill discovery
--   2) 米其林/黑珍珠全量名单闭环——发现端，见 skill discovery
--   3) 工业化餐饮（预制菜/中央厨房/资本化连锁）识别——本文件加列 + 标签
--   4) 跨菜系档次矛盾——本文件加 price_position（品类内相对档）
--   5) 分类语义消歧（海南鸡饭/大富贵等）——见 skill cuisine-map 消歧表
--
-- 本文件只做：加 4 列 + CHECK、新建 2 个特别标签、扩展审计视图。
-- 计算（price_position 分位、工业化取证、语义审计）走 pipeline 脚本，DB 只存储与约束。
-- 幂等可重复执行。执行环境：Supabase -> SQL Editor；PostgreSQL 17 / PostGIS。
-- =====================================================================

-- =====================================================================
-- BATCH 1 — 新增 4 列（幂等）
-- =====================================================================
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS chain_type     text;  -- 独立店/小型连锁/大型连锁/资本化连锁
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS central_kitchen text;  -- 无/疑似/确认
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS premade_risk   text;  -- 无/低/疑似/高
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS price_position text;  -- 品类内相对档：入门/主流/进阶/高端/旗舰

-- 1.1 chain_type 值域
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_chain_type') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_chain_type
      CHECK (chain_type IS NULL OR chain_type IN ('独立店','小型连锁','大型连锁','资本化连锁'));
  END IF;
END $$;

-- 1.2 central_kitchen 值域
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_central_kitchen') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_central_kitchen
      CHECK (central_kitchen IS NULL OR central_kitchen IN ('无','疑似','确认'));
  END IF;
END $$;

-- 1.3 premade_risk 值域
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_premade_risk') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_premade_risk
      CHECK (premade_risk IS NULL OR premade_risk IN ('无','低','疑似','高'));
  END IF;
END $$;

-- 1.4 price_position 值域
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_price_position') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_price_position
      CHECK (price_position IS NULL OR price_position IN ('入门','主流','进阶','高端','旗舰'));
  END IF;
END $$;

-- =====================================================================
-- BATCH 2 — 新建 2 个特别标签（dimension=标签；幂等）
-- =====================================================================
INSERT INTO cuisines (name, dimension, parent_category) VALUES
  ('上海老字号', '标签', NULL),
  ('工业化餐饮', '标签', NULL)
ON CONFLICT (name, dimension, (COALESCE(parent_category,''))) DO NOTHING;

-- =====================================================================
-- BATCH 3 — 扩展审计视图 v_audit_gaps（新增 2 类 issue，其余不变）
-- =====================================================================
CREATE OR REPLACE VIEW v_audit_gaps
WITH (security_invoker=on) AS
WITH tag AS (
  SELECT rc.restaurant_id, c.dimension, c.id AS cid, c.name AS cname
  FROM restaurant_cuisines rc JOIN cuisines c ON c.id = rc.cuisine_id
), agg AS (
  SELECT restaurant_id,
         bool_or(dimension='菜系') AS has_cuisine,
         bool_or(dimension='形式') AS has_form,
         bool_or(cid IN (162,163))  AS has_meal,
         bool_or(cid = 71)          AS has_finedining,
         bool_or(cname='工业化餐饮') AS has_industrial_tag
  FROM tag GROUP BY restaurant_id
), issues AS (
  SELECT r.id, r.name, g.issue
  FROM restaurants r
  LEFT JOIN agg a ON a.restaurant_id = r.id
  CROSS JOIN LATERAL (VALUES
    ('无坐标',        CASE WHEN r.status='active' AND r.location IS NULL THEN 1 END),
    ('地址空',        CASE WHEN nullif(btrim(coalesce(r.address,'')),'') IS NULL THEN 1 END),
    ('电话空',        CASE WHEN nullif(btrim(coalesce(r.phone,'')),'') IS NULL THEN 1 END),
    ('证据过短',      CASE WHEN r.evidence_summary IS NULL OR length(r.evidence_summary) < 30 THEN 1 END),
    ('招牌菜空',      CASE WHEN r.signature_dishes IS NULL
                            OR jsonb_typeof(r.signature_dishes)<>'array'
                            OR jsonb_array_length(r.signature_dishes)=0 THEN 1 END),
    ('缺菜系叶子',    CASE WHEN NOT coalesce(a.has_cuisine,false) THEN 1 END),
    ('缺形式',        CASE WHEN NOT coalesce(a.has_form,false) THEN 1 END),
    ('缺午晚餐',      CASE WHEN NOT coalesce(a.has_meal,false) THEN 1 END),
    ('评分不完整',    CASE WHEN r.score_objective IS NULL OR r.score_diner IS NULL
                            OR r.score_taste IS NULL OR r.score_endorsement IS NULL THEN 1 END),
    ('FineDining越档',CASE WHEN coalesce(a.has_finedining,false)
                            AND (r.price_avg IS NULL OR r.price_avg < 250) THEN 1 END),
    ('关店三要素缺',  CASE WHEN r.status='closed'
                            AND (r.closed_date IS NULL OR r.closed_source IS NULL) THEN 1 END),
    ('坐标越界',      CASE WHEN r.location IS NOT NULL AND
                            (ST_SRID(r.location)<>4326
                             OR ST_X(r.location::geometry) NOT BETWEEN 120.80 AND 122.20
                             OR ST_Y(r.location::geometry) NOT BETWEEN 30.65 AND 31.95) THEN 1 END),
    ('采集日期空',    CASE WHEN r.data_updated_at IS NULL THEN 1 END),
    ('高预制风险缺标签', CASE WHEN r.premade_risk='高' AND NOT coalesce(a.has_industrial_tag,false) THEN 1 END),
    ('price_position未算', CASE WHEN r.chain_type IS NOT NULL AND r.price_position IS NULL THEN 1 END)
  ) AS g(issue, flag)
  WHERE g.flag IS NOT NULL
)
SELECT * FROM issues;

-- 视图权限维持：审计视图仅 service_role
REVOKE SELECT ON v_audit_gaps FROM PUBLIC, anon, authenticated;
GRANT  SELECT ON v_audit_gaps TO service_role;

-- =====================================================================
-- 完成后验证：
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='restaurants' AND column_name IN
--       ('chain_type','central_kitchen','premade_risk','price_position');
--   SELECT id,name,dimension FROM cuisines WHERE name IN ('上海老字号','工业化餐饮');
--   SELECT issue,count(*) FROM v_audit_gaps GROUP BY issue ORDER BY 2 DESC;
-- =====================================================================
