-- =====================================================================
-- 007_softad_v2.sql —— 软广判定 v2：chain 信号与 reviews 判定分离，最终 flag 纯派生
--   修正 006 两个缺陷：
--   ① 两个 derive trigger 重复（trg_derive_restaurant + trg_restaurants_derive）→ 合并为一个
--   ② flag「取最严重只升不降」：Manner/星巴克在第一版被 chain 误设 confirmed 后无法解除
--   新模型（输入→输出）：
--     输入：chain_type/central_kitchen/premade_risk（chain 硬信号，非正餐豁免）
--           soft_ad_flag_reviews（reviews 6 规则 + 人工判定，可升可降）
--     输出：soft_ad_flag = greatest(chain信号, reviews判定)  ← 纯派生
--           soft_ad_penalty = confirmed25/suspected10/none0  ← 纯派生
--   依赖 001..006。幂等。DDL 走 Supabase SQL Editor。
-- =====================================================================

-- BATCH 1 — 新增 reviews 侧判定输入列
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS soft_ad_flag_reviews TEXT DEFAULT 'none';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_softad_reviews') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_softad_reviews
      CHECK (soft_ad_flag_reviews IN ('none','suspected','confirmed'));
  END IF;
END $$;

-- BATCH 2 — 清理重复 derive trigger
DROP TRIGGER IF EXISTS trg_derive_restaurant ON restaurants;
DROP TRIGGER IF EXISTS trg_restaurants_derive ON restaurants;

-- BATCH 3 — 重写 derive_restaurant
CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_chain_flag TEXT;
  v_rev_flag TEXT;
  v_nondiner BOOLEAN;
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();
  IF NEW.price_avg IS NOT NULL THEN
    NEW.tier := tier_for_price(NEW.price_avg);
  END IF;

  -- chain 硬信号；非正餐（咖啡/面包/甜品/Bar/茶饮）豁免：连锁供应链是业态常态
  SELECT EXISTS(SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
    WHERE rc.restaurant_id=NEW.id AND c.dimension='菜系' AND c.parent_category='非正餐')
    INTO v_nondiner;
  IF v_nondiner THEN
    v_chain_flag := 'none';
  ELSE
    v_chain_flag := CASE
      WHEN NEW.central_kitchen='确认' OR NEW.premade_risk='高' THEN 'confirmed'
      WHEN NEW.central_kitchen='疑似' OR NEW.premade_risk='疑似'
           OR NEW.chain_type IN ('资本化连锁','大型连锁') THEN 'suspected'
      ELSE 'none' END;
  END IF;

  v_rev_flag := COALESCE(NEW.soft_ad_flag_reviews, 'none');

  -- 最终 flag = greatest(chain, reviews)；penalty 纯派生（可随输入升降）
  NEW.soft_ad_flag := CASE
    WHEN v_chain_flag='confirmed' OR v_rev_flag='confirmed' THEN 'confirmed'
    WHEN v_chain_flag='suspected' OR v_rev_flag='suspected' THEN 'suspected'
    ELSE 'none' END;
  NEW.soft_ad_penalty := CASE NEW.soft_ad_flag
    WHEN 'confirmed' THEN 25 WHEN 'suspected' THEN 10 ELSE 0 END;

  IF NEW.score_objective IS NULL OR NEW.score_diner IS NULL
     OR NEW.score_taste IS NULL OR NEW.score_endorsement IS NULL THEN
    NEW.score_total := NULL;
  ELSE
    NEW.score_total := greatest(0, least(100, round(
        0.35*NEW.score_taste
      + 0.25*NEW.score_objective
      + 0.25*NEW.score_diner
      + 0.15*NEW.score_endorsement
      - NEW.soft_ad_penalty, 1)));
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_restaurants_derive
  BEFORE INSERT OR UPDATE ON restaurants
  FOR EACH ROW EXECUTE FUNCTION derive_restaurant();

-- BATCH 4 — 全表回填
UPDATE restaurants SET id = id;
