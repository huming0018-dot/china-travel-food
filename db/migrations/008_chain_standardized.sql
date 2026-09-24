-- 008_chain_standardized.sql
-- 「标准化连锁」派生列：本表信号即可判定，generated STORED，供前端"隐藏连锁/预制"与连锁角标对齐。
-- 口径：
--   资本化连锁              -> 一律标准化（强中央厨房、融资/上市驱动）。
--   大型 / 小型连锁         -> 仅当有中央厨房(确认/疑似) 或 预制风险(高/疑似/低) 才标准化。
--   高端餐饮集团(多店但 ck=无、pr=无，如新荣记/大董/甬府)、独立店、同城现做多店(pr=无) -> 非标准化，保留。
-- 非正餐(咖啡/面包/甜品/Bar/茶饮)的连锁豁免放在前端，不在此列（数据层只做客观标注）。

ALTER TABLE restaurants
  ADD COLUMN IF NOT EXISTS is_chain_standardized boolean
  GENERATED ALWAYS AS (
    chain_type = '资本化连锁'
    OR ( chain_type IN ('大型连锁','小型连锁')
         AND ( central_kitchen IN ('确认','疑似')
               OR premade_risk IN ('高','疑似','低') ) )
  ) STORED;

-- 验收（应为真）：
--   select name, chain_type, central_kitchen, premade_risk, is_chain_standardized
--   from restaurants where name ilike '%FAT PHO%' or name ilike '%西贡妈妈%';
-- 新荣记/大董 is_chain_standardized 应为 f；小菜园应为 t。
