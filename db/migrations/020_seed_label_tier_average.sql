-- 020_seed_label_tier_average.sql — 种子标注增加第三档「一般(average)」
-- 用户口径（2026-09-30 锁定）：
--   必吃 must_eat      = 口味确实好；
--   值得 worth_eating  = 没有太多雷点；
--   一般 average       = 能吃，但很难对一个美食家留下深刻印象。
-- 能被选中至少代表“可以去吃”。在 Supabase SQL Editor 执行一次。幂等可重跑。

ALTER TABLE diner_seed_labels DROP CONSTRAINT IF EXISTS diner_seed_labels_tier_check;

ALTER TABLE diner_seed_labels
    ADD CONSTRAINT diner_seed_labels_tier_check
    CHECK (tier IN ('must_eat','worth_eating','average'));
