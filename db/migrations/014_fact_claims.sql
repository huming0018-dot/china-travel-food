-- 014_fact_claims.sql
-- 事实层标签：food_safety（食安状态）+ fact_claims（事实主张 jsonb 数组）。
-- 原则（北极星 A2 宁空不假 / 事实与评价分离）：
--   中央厨房 / 预制 / 食安 属「事实」，口味属「评价」；每条事实必须可溯源
--   （source_url + quote + date + confidence），无权威来源不写。
-- fact_claims 结构：[{type, value, confidence, date, source_url, quote}]
-- is_chain_standardized 已由 chain_type + central_kitchen/premade_risk 生成，
--   本迁移不改其口径（大型连锁 + ck确认/疑似 自动 std=true）。

ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS food_safety text NOT NULL DEFAULT '无';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ch_rest_food_safety') THEN
    ALTER TABLE restaurants
      ADD CONSTRAINT ch_rest_food_safety CHECK (food_safety IN ('无','疑似','确认'));
  END IF;
END $$;

ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS fact_claims jsonb NOT NULL DEFAULT '[]'::jsonb;

-- 验收（应为真）：
--   select id,name,chain_type,central_kitchen,premade_risk,food_safety,is_chain_standardized,
--          jsonb_array_length(fact_claims)
--   from restaurants where id in (610,1445,1616);
