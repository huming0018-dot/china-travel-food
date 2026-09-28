-- 013_kol.sql
-- 全局「美食声音」体系：KOL/美食家/美食导演/美食作家/主厨自媒体名单 + 推文归档 + 提及线索
-- 治：food_kol_watchlist 仅 B站、无类型/专长/地域/可信度；推文无归档；提及店名无下游。
-- 设计：KOL 到访只写【特征标签/线索】，不计入 taste；真实口味仍是唯一评定（见北极星宪法）。

-- 1) 扩 watchlist
ALTER TABLE food_kol_watchlist
  ADD COLUMN IF NOT EXISTS kol_type TEXT
        CHECK (kol_type IN ('博主','美食家','美食导演','美食作家','主厨自媒体','媒体')),
  ADD COLUMN IF NOT EXISTS specialty_tags JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS region TEXT NOT NULL DEFAULT '上海',
  ADD COLUMN IF NOT EXISTS profile_url TEXT,
  ADD COLUMN IF NOT EXISTS trust TEXT NOT NULL DEFAULT 'mid'
        CHECK (trust IN ('high','mid','low'));

-- 2) 推文归档（一帖一行，post_url 唯一）
CREATE TABLE IF NOT EXISTS food_kol_posts (
  id SERIAL PRIMARY KEY,
  kol_id INTEGER NOT NULL REFERENCES food_kol_watchlist(id) ON DELETE CASCADE,
  platform TEXT NOT NULL,
  post_url TEXT NOT NULL UNIQUE,
  title TEXT,
  summary TEXT,
  published_at TIMESTAMPTZ,
  raw_mentions JSONB NOT NULL DEFAULT '[]',
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kol_posts_kol
  ON food_kol_posts(kol_id, published_at DESC);

-- 3) 提及线索（帖子里提到的店：matched/ambiguous/unmatched + 情感）
CREATE TABLE IF NOT EXISTS food_kol_mentions (
  id SERIAL PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES food_kol_posts(id) ON DELETE CASCADE,
  restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE SET NULL,
  mentioned_raw TEXT NOT NULL,
  match_status TEXT NOT NULL DEFAULT 'unmatched'
        CHECK (match_status IN ('matched','ambiguous','unmatched')),
  polarity TEXT NOT NULL DEFAULT 'neu'
        CHECK (polarity IN ('pos','neu','neg','mixed')),
  UNIQUE(post_id, mentioned_raw)
);
CREATE INDEX IF NOT EXISTS idx_kol_mentions_rest
  ON food_kol_mentions(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_kol_mentions_status
  ON food_kol_mentions(match_status);

-- RLS：默认仅 service role（绕过 RLS）读写；前端如需只读名单再补 anon policy。
ALTER TABLE food_kol_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE food_kol_mentions ENABLE ROW LEVEL SECURITY;
