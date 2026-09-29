-- 016_kol_handles.sql
-- KOL 跨平台身份注册表（Track 1C）。
-- 上位契约：references/source-classes-and-calibration.md §3.1
--   「以 food_kol_watchlist 为主实体，把同一博主在 XHS/B站/抖音/公众号/微博/知乎/YouTube 的账号挂为跨平台 handle」。
-- 原则：只能确定性地按「同名归一 / 已知 mid / 主页链接」补 handle；无法确定的留空 {}，绝不硬猜错绑账号。
-- 注意：DDL 只能在 Supabase SQL Editor 执行（REST 不能 DDL）；执行后用 SELECT 验证列存在。

ALTER TABLE food_kol_watchlist
  ADD COLUMN IF NOT EXISTS handles JSONB NOT NULL DEFAULT '{}';

-- handles 结构（jsonb，键=平台，值=该平台的账号定位信息；缺省 {} 表示尚未解析、不猜）：
-- {
--   "bilibili": {"mid": "398324573", "url": "https://space.bilibili.com/398324573"},
--   "wechat":    {"name": "公众号名称", "url": ""},
--   "weibo":     {"uid": "", "url": ""},
--   "douyin":    {"sec_uid": "", "url": ""},
--   "zhihu":     {"url": ""},
--   "youtube":   {"handle": ""}
-- }
-- 独立声音计数口径：同一博主跨平台同发同款内容，按内容指纹（归一标题 hash / bvid / 文章 url）去重后只算 1 个独立声音。

CREATE INDEX IF NOT EXISTS idx_kol_watchlist_handles
  ON food_kol_watchlist USING GIN (handles);

-- 验证（执行后跑这条应返回 handles 列）：
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name='food_kol_watchlist' AND column_name='handles';
