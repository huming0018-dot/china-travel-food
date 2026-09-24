-- =====================================================================
-- 006_softad_derive.sql —— 软广/预制 确定性派生机制
--   修正审计发现：1169 家 soft_ad_flag=none 却背着无依据的手填 penalty(3/5/8…)
--   机制：
--     ① soft_ad_flag 由 chain/中央厨房/预制 硬信号确定性派生，reviews 6 规则可升级（取最严重）
--     ② soft_ad_penalty 由 final flag 派生（confirmed=25 / suspected=10 / none=0），禁止手填
--     ③ 全表回填，清除无依据罚分
--   依赖：001..005；restaurants 现有 chain_type/central_kitchen/premade_risk/soft_ad_flag/soft_ad_penalty
--   DDL 只能走 Supabase SQL Editor。幂等可重跑。
-- =====================================================================

-- BATCH 1 — 升级 derive_restaurant：并入 flag/penalty 确定性派生
DROP TRIGGER IF EXISTS trg_derive_restaurant ON restaurants;
CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_sig_flag TEXT;
  v_nondiner BOOLEAN;
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();
  IF NEW.price_avg IS NOT NULL THEN
    NEW.tier := tier_for_price(NEW.price_avg);
  END IF;

  -- ① 确定性硬信号（chain / 中央厨房 / 预制）；非正餐（咖啡/面包/甜品/Bar/茶饮）豁免：
  --    连锁供应链是其业态常态，好坏交给 taste/reviews，不按预制软广沉底
  SELECT EXISTS(SELECT 1 FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
    WHERE rc.restaurant_id=NEW.id AND c.dimension='菜系' AND c.parent_category='非正餐')
    INTO v_nondiner;
  IF v_nondiner THEN
    v_sig_flag := 'none';
  ELSE
    v_sig_flag := CASE
      WHEN NEW.central_kitchen = '确认' OR NEW.premade_risk = '高' THEN 'confirmed'
      WHEN NEW.central_kitchen = '疑似' OR NEW.premade_risk = '疑似'
           OR NEW.chain_type IN ('资本化连锁','大型连锁') THEN 'suspected'
      ELSE 'none' END;
  END IF;

  -- 与 reviews 6 规则 / 人工已写入的 flag 取「最严重」（none < suspected < confirmed）
  NEW.soft_ad_flag := CASE
    WHEN NEW.soft_ad_flag IS NULL OR NEW.soft_ad_flag = 'none' THEN v_sig_flag
    WHEN NEW.soft_ad_flag = 'suspected' AND v_sig_flag = 'confirmed' THEN 'confirmed'
    ELSE NEW.soft_ad_flag END;

  -- ② penalty 由 final flag 确定性派生（覆盖任何历史手填）
  NEW.soft_ad_penalty := CASE NEW.soft_ad_flag
    WHEN 'confirmed' THEN 25 WHEN 'suspected' THEN 10 ELSE 0 END;

  -- ③ 综合分（taste 核心 0.35；平台客观降权；penalty 沉底）
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

CREATE TRIGGER trg_derive_restaurant
  BEFORE INSERT OR UPDATE ON restaurants
  FOR EACH ROW EXECUTE FUNCTION derive_restaurant();

-- BATCH 2 — 全表回填：触发 derive_restaurant 重算 flag/penalty/total
UPDATE restaurants SET id = id;

-- BATCH 3 — 核对（执行后在结果中查看分布）
-- SELECT soft_ad_flag, COUNT(*) FROM restaurants GROUP BY 1 ORDER BY 1;
