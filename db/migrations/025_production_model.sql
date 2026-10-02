-- 025_production_model.sql
-- 二次校验升级：把「所有权/资本结构」与「出餐方式」解耦为两个正交维度。
--   所有权维度 = chain_type（独立店/小型连锁/大型连锁/资本化连锁）——已有。
--   出餐方式维度 = production_model（新增）——回答“菜到底怎么做出来、怎么到盘里”。
--
-- 为什么需要：大型连锁也可能每店现炒（火锅/现炒），单店也可能用料理包；
--   旧 central_kitchen/premade_risk 只当零散硬负面，无法表达完整出餐链路。
--   production_model 由证据经 gate 仲裁写入（宁空不假；NULL=证据不足，不猜）。
--
-- 枚举口径（从“最现做”到“最复热”排序）：
--   现炒现做            门店有完整厨房，热食现点现炒/现包/现切（明厨/锅气/炒锅）。
--   门店现制·标准化      门店现制但流程标准化（现烤面包/现切烧肉/手工面+标准备料）。
--   中央厨房·门店加工    央厨配送半成品，门店仍有实质热加工（锅底/腌制+门店现炒、火锅烫煮）。
--   中央厨房·门店复热    央厨配送成品，门店仅复热/摆盘（无实质烹饪）。
--   预制料理包·复热      外购/自有预制料理包，门店复热即出（无真实烹饪）。
--   外购成品·无堂食厨房  无堂食厨房，转售外购成品（分装/外采）。

ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS production_model text;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'restaurants_production_model_chk') THEN
    ALTER TABLE restaurants
      ADD CONSTRAINT restaurants_production_model_chk CHECK (
        production_model IS NULL OR production_model IN (
          '现炒现做','门店现制·标准化','中央厨房·门店加工',
          '中央厨房·门店复热','预制料理包·复热','外购成品·无堂食厨房'));
  END IF;
END $$;

-- 确定性“复热出餐”标记（供精选门/评分/前端“只看现做”使用）：
--   仅在明确复热/外购三类时为真；NULL（证据不足）与各类现做均为假，绝不因未知误杀。
ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS is_reheat_served boolean
  GENERATED ALWAYS AS (
    production_model IN ('中央厨房·门店复热','预制料理包·复热','外购成品·无堂食厨房')
  ) STORED;

-- 验收（应为真）：
--   select name, chain_type, production_model, is_reheat_served from restaurants
--   where production_model is not null order by is_reheat_served desc;
-- 回滚：
--   ALTER TABLE restaurants DROP COLUMN IF EXISTS production_model;
--   ALTER TABLE restaurants DROP COLUMN IF EXISTS is_reheat_served;
