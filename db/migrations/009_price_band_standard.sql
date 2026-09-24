-- 009_price_band_standard.sql
-- 目标：用客观、可复算、不含模糊语义的"场景价格带"取代主观的 price_position（旗舰/进阶/高端/入门/主流）。
-- 设计：
--   1) price_band_thresholds：各"价格场景"5 带的固定数值边界（单一真相，可复核、可随数据更新）。
--   2) restaurants.price_scene / price_band：由管线脚本按标签(场景)+人均(带)确定性回填。
-- 边界依据 research/authority/price_distribution.py 的真实分位数（取整）：
--   正餐 P25=95/P50=133/P75=268/P90=629；快餐小吃 35/55/80/100；酒吧 150/187/221/300；
--   咖啡茶饮 40/48/55/77；面包 35/45/60/70；甜品 34/45/65/73。
-- 约定：lo 含、hi 不含；band=1 的 lo=NULL（下界开），band=5 的 hi=NULL（上界开）。

-- 1. 阈值配置表
CREATE TABLE IF NOT EXISTS price_band_thresholds (
  scene text NOT NULL,
  band  integer NOT NULL CHECK (band BETWEEN 1 AND 5),
  lo    integer,
  hi    integer,
  PRIMARY KEY (scene, band)
);

INSERT INTO price_band_thresholds (scene, band, lo, hi) VALUES
  -- 正餐
  ('正餐',1,NULL,90), ('正餐',2,90,135), ('正餐',3,135,270), ('正餐',4,270,630), ('正餐',5,630,NULL),
  -- 快餐小吃
  ('快餐小吃',1,NULL,35), ('快餐小吃',2,35,55), ('快餐小吃',3,55,80), ('快餐小吃',4,80,100), ('快餐小吃',5,100,NULL),
  -- 酒吧
  ('酒吧',1,NULL,150), ('酒吧',2,150,190), ('酒吧',3,190,220), ('酒吧',4,220,300), ('酒吧',5,300,NULL),
  -- 咖啡茶饮（茶饮样本少且分布与咖啡相近，合并）
  ('咖啡茶饮',1,NULL,40), ('咖啡茶饮',2,40,48), ('咖啡茶饮',3,48,55), ('咖啡茶饮',4,55,75), ('咖啡茶饮',5,75,NULL),
  -- 面包
  ('面包',1,NULL,35), ('面包',2,35,45), ('面包',3,45,60), ('面包',4,60,70), ('面包',5,70,NULL),
  -- 甜品
  ('甜品',1,NULL,35), ('甜品',2,35,45), ('甜品',3,45,65), ('甜品',4,65,75), ('甜品',5,75,NULL)
ON CONFLICT (scene,band) DO UPDATE SET lo=EXCLUDED.lo, hi=EXCLUDED.hi;

-- 2. 餐厅新增场景 / 价格带
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS price_scene text;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS price_band integer;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_price_band') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_price_band
      CHECK (price_band IS NULL OR price_band BETWEEN 1 AND 5);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_rest_price_band ON restaurants(price_scene, price_band);

-- 3. 配置表允许匿名只读（前端据此生成区间标签）
ALTER TABLE price_band_thresholds ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='price_band_thresholds_read') THEN
    CREATE POLICY price_band_thresholds_read ON price_band_thresholds
      FOR SELECT TO anon, authenticated USING (true);
  END IF;
END $$;
GRANT SELECT ON price_band_thresholds TO anon, authenticated;
