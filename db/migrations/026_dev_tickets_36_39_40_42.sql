-- =====================================================================
-- 026_dev_tickets_36_39_40_42.sql — dev 工单 #36 / #39 / #40 / #42 落地
-- ---------------------------------------------------------------------
--   #36 菜单特质：新增 dietary_tags（jsonb，含标签与证据）。
--   #39 预制下架：新增 is_delisted / delist_reason / delisted_at（硬门，不消费先验）。
--   #40 评分 v5：口味/真实食客主导（0.50 taste / 0.22 diner / 0.16 obj / 0.12 end）。
--   #42 去广强化：soft_ad_penalty 由「硬信号 + astroturf_score 自学」统一派生。
-- 幂等可重跑；DML/DDL 经 Supabase Management API 执行。
-- =====================================================================

-- #36 菜单特质标签（素食/全素/清真/无麸质/低卡/低糖/低脂 + 证据）
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS dietary_tags jsonb;

-- #39 预制/工业化门店下架（与 status='closed' 区分；下架不删数据、可审计、可恢复）
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS is_delisted boolean DEFAULT false;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS delist_reason text;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS delisted_at timestamptz;

-- 榜单默认只看「在营且未下架」
CREATE INDEX IF NOT EXISTS idx_rest_list_clean
  ON restaurants (score_total DESC NULLS LAST)
  WHERE status='active' AND COALESCE(is_delisted,false)=false;

-- =====================================================================
-- 评分 v5：derive_restaurant 单一事实源
--   1) soft_ad_penalty = greatest(硬信号, astroturf 自学)
--      硬信号仅采信 CK/premade【证据列】（非正餐豁免），不因连锁规模本身扣分；
--      astroturf = round(astroturf_score * 0.28)，0..100 → 0..28。
--   2) 口味主导权重：0.50 taste + 0.22 diner + 0.16 objective(缺省=taste) + 0.12 endorsement
--   3) evidence level / 上限沿用 v4（verified 无上限；provisional 82；仅客观/背书 70；无证据 NULL）。
--   4) is_delisted=true 强制移出精选。
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
    v_blend := 0.50*NEW.score_taste
             + 0.22*NEW.score_diner
             + 0.16*COALESCE(NEW.score_objective, NEW.score_taste)
             + 0.12*COALESCE(NEW.score_endorsement, 0);
    IF v_nind>=2 THEN
      NEW.score_evidence_level := 'verified';
      NEW.score_total := greatest(0, least(100, round(v_blend - v_pen, 1)));
    ELSE
      NEW.score_evidence_level := 'provisional';
      NEW.score_total := greatest(0, least(82, round(v_blend - v_pen, 1)));
    END IF;

  ELSIF COALESCE(NEW.score_objective,0)>0 OR COALESCE(NEW.score_endorsement,0)>0 THEN
    v_blend := 0.6*COALESCE(NEW.score_objective,0) + 0.4*COALESCE(NEW.score_endorsement,0);
    NEW.score_evidence_level := 'provisional';
    NEW.score_total := greatest(0, least(70, round(v_blend - v_pen, 1)));

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
--   SELECT count(*) FROM restaurants WHERE is_delisted;
--   SELECT count(*) FILTER (WHERE score_evidence_level='verified') FROM restaurants WHERE status='active';
