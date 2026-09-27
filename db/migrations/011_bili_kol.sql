-- 011_bili_kol.sql
-- B站(bilibili)美食探店接入：KOL 监控名单表
-- 通道①：统计在美食探店视频中出现≥3次的 UP主，长期监控其新视频作探店线索。
-- 餐厅候选（通道②）走现有 restaurants 表 + admission_gate→candidate_apply，不另立表。

CREATE TABLE IF NOT EXISTS food_kol_watchlist (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,                      -- UP主名
  platform TEXT NOT NULL DEFAULT 'bilibili',
  follower_count INT,                      -- 粉丝数（搜索API不返回，可空，后续补）
  video_count INT DEFAULT 0,               -- 在美食探店视频中被采集到的条数
  first_seen DATE DEFAULT CURRENT_DATE,
  last_seen DATE DEFAULT CURRENT_DATE,
  status TEXT DEFAULT 'active' CHECK (status IN ('active','ignored')),
  notes TEXT,
  UNIQUE(name, platform)
);

-- 按平台 + 状态过滤监控名单时常用
CREATE INDEX IF NOT EXISTS idx_food_kol_platform_status
  ON food_kol_watchlist(platform, status);

ALTER TABLE food_kol_watchlist ENABLE ROW LEVEL SECURITY;
-- service role 绕开 RLS 做采集 upsert；前端如需只读可另行加 anon policy。
