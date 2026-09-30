-- 023_kol_identity.sql
-- Track 1C 收尾：KOL 跨平台身份归一表 + mentions 上下文列。
-- 上位契约：references/source-classes-and-calibration.md §3.1（跨平台 handle 归一、同内容去重）。
-- 幂等：IF NOT EXISTS / IF EXISTS 风格，可重复执行。
-- 审计结论（2026-09-30 REST 实测）：
--   food_kol_posts    已存在 206 行，字段已够（summary≈content，captured_at≈collected_at），不动。
--   food_kol_mentions  已存在 190 行，缺 context（提及上下文窗口），本迁移补列。
--   food_kol_identity 不存在，本迁移新建。
-- 注意：DDL 由人工在 Supabase SQL Editor 执行；本文件不自动跑。

-- 1) mentions 补 context 列（提及所在句子窗口；可从 posts.summary 推导）
ALTER TABLE food_kol_mentions
  ADD COLUMN IF NOT EXISTS context TEXT;

-- 2) 跨平台身份归一表（规范化，与 watchlist.handles JSONB 互补：每行=一个平台身份）
CREATE TABLE IF NOT EXISTS food_kol_identity (
  id SERIAL PRIMARY KEY,
  canonical_kol_id INTEGER NOT NULL REFERENCES food_kol_watchlist(id) ON DELETE CASCADE,
  platform TEXT NOT NULL
        CHECK (platform IN ('bilibili','wechat','weibo','zhihu','douyin','xiaohongshu','youtube','web_media')),
  handle TEXT NOT NULL,                 -- 该平台账号定位：mid / 公众号名 / uid / sec_uid / url
  profile_url TEXT,
  confidence TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (confidence IN ('confirmed','candidate','unverified')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (canonical_kol_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_kol_identity_kol
  ON food_kol_identity(canonical_kol_id);
CREATE INDEX IF NOT EXISTS idx_kol_identity_platform
  ON food_kol_identity(platform);

ALTER TABLE food_kol_identity ENABLE ROW LEVEL SECURITY;

-- 3) 验证（执行后跑这两条应返回 context 列存在 + 0 行空表）：
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='food_kol_mentions' AND column_name='context';
-- SELECT count(*) FROM food_kol_identity;
