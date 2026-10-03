-- =====================================================================
-- 027_platform_rating_pillar.sql — 平台评分柱 + 背书柱清洗 + 评分 v6
-- ---------------------------------------------------------------------
-- 背景：
--   · score_endorsement 被污染（1492 店有值，实际仅 125 店有奖项 restaurant_awards）；
--   · 平台聚合评分（高德/点评门店星级）此前无独立、可追溯的落点，混入 score_objective；
--   · 平台星级明显通胀（高德多在 4.5–4.7），不能线性 rating/5*100。
-- 本次：
--   1) 新建 platform_ratings：原始平台聚合评分（可追溯、可复采、多平台）；
--   2) restaurants 新增 score_platform（由 platform_score.py 按平台校准后写入）；
--   3) derive_restaurant 升级 v6：口味主导，平台/背书仅作三角校准；
--   4) score_endorsement 改由 platform_score.py 严格按 restaurant_awards 重算（非奖项清零）。
-- 幂等可重跑；经 Supabase Management API 执行。
-- =====================================================================

-- 1) 原始平台聚合评分（一行 = 某店在某平台某次抓取的聚合星级）
CREATE TABLE IF NOT EXISTS platform_ratings (
  restaurant_id integer NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  platform      text NOT NULL,                 -- amap / dianping / meituan ...
  rating        numeric(3,1) NOT NULL,         -- 平台原始星级（一般 0–5）
  review_count  integer,                        -- 平台口径评论数（缺省 NULL）
  source_url    text,
  captured_at   date NOT NULL DEFAULT CURRENT_DATE,
  PRIMARY KEY (restaurant_id, platform, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_platform_ratings_rid ON platform_ratings(restaurant_id);

-- 2) 平台评分柱（校准后的 0–100；由 platform_score.py 确定性计算）
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS score_platform numeric;

-- =====================================================================
-- 评分 v6：derive_restaurant 单一事实源
--   组件（均由管线确定性写入，触发器只 blend）：
--     score_taste     真实食客口味（贝叶斯收缩，稳健）        —— 最高权重
--     score_diner     真实食客口味时间加权原始均值（不收缩）
--     score_platform  平台聚合星级（按平台分布校准，去通胀）  —— 三角校准
--     score_endorsement 奖项背书（仅米其林/黑珍珠/必比登，稀疏）
--   权重：0.58 taste + 0.20 diner + 0.12 platform + 0.10 endorsement
--   证据等级：独立食客≥2 verified（无上限）；否则 provisional（上限 82）；
--             仅平台/背书、无真实 UGC：上限 68；全无证据 NULL。
--   soft_ad_penalty 沿用 v5（硬信号 greatest astroturf；非正餐豁免；不因连锁规模扣分）。
-- =====================================================================
CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_nind integer; v_blend numeric; v_pen numeric; v_hard numeric; v_astro numeric; v_nondiner boolean;
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();
  IF NEW.price_avg IS NOT NULL THEN NEW.tier := tier_for_price(NEW.price_avg); END IF;

  -- 是否非正餐（咖啡/面包/甜品/Bar/茶饮）：连锁供应链是业态常态，硬信号豁免
  SELECT EXISTS(SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
    WHERE rc.restaurant_id=NEW.id AND c.dimension='菜系' AND c.parent_category='非正餐')
    INTO v_nondiner;

  IF v_nondiner THEN
    v_hard := 0;
  ELSE
    v_hard := CASE
      WHEN NEW.central_kitchen='确认' OR NEW.premade_risk='高' THEN 25
      WHEN NEW.central_kitchen='疑似' OR NEW.premade_risk='疑似' THEN 10
      ELSE 0 END;
  END IF;

  v_astro := ROUND(COALESCE(NEW.astroturf_score,0) * 0.28);
  v_pen := GREATEST(v_hard, v_astro);
  NEW.soft_ad_penalty := v_pen;

  -- 独立食客作者数（证据等级）
  SELECT COUNT(DISTINCT author_name) INTO v_nind
  FROM reviews
  WHERE restaurant_id=NEW.id AND review_kind='diner'
    AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
    AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL;

  IF NEW.score_taste IS NOT NULL AND NEW.score_diner IS NOT NULL THEN
    v_blend := 0.58*NEW.score_taste
             + 0.20*NEW.score_diner
             + 0.12*COALESCE(NEW.score_platform, NEW.score_taste)
             + 0.10*COALESCE(NEW.score_endorsement, 0);
    IF v_nind>=2 THEN
      NEW.score_evidence_level := 'verified';
      NEW.score_total := greatest(0, least(100, round(v_blend - v_pen, 1)));
    ELSE
      NEW.score_evidence_level := 'provisional';
      NEW.score_total := greatest(0, least(82, round(v_blend - v_pen, 1)));
    END IF;

  ELSIF COALESCE(NEW.score_platform,0)>0 OR COALESCE(NEW.score_endorsement,0)>0 THEN
    -- 无真实食客 UGC：平台/背书仅给低分 provisional，不冒充口碑
    v_blend := 0.55*COALESCE(NEW.score_platform,0) + 0.45*COALESCE(NEW.score_endorsement,0);
    NEW.score_evidence_level := 'provisional';
    NEW.score_total := greatest(0, least(68, round(v_blend - v_pen, 1)));

  ELSE
    NEW.score_evidence_level := 'insufficient';
    NEW.score_total := NULL;
  END IF;

  IF COALESCE(NEW.is_delisted,false) THEN
    NEW.is_curated := false;
    NEW.curate_badge := NULL;
  END IF;

  RETURN NEW;
END $$;

-- 验证：
--   SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname='derive_restaurant';
--   SELECT platform, count(*) FROM platform_ratings GROUP BY 1;
--   SELECT count(*) FILTER (WHERE score_platform IS NOT NULL) FROM restaurants;
--   SELECT count(*) FILTER (WHERE score_endorsement>0) FROM restaurants;  -- 应≈125
