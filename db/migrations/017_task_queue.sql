-- 017_task_queue.sql — 跨角色任务队列
-- 在 Supabase SQL Editor 中执行一次即可
-- 三个窗口（开发/采集/QA）通过这张表结构化分配任务，不再靠口头传话

CREATE TABLE IF NOT EXISTS task_queue (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  assignee TEXT NOT NULL CHECK (assignee IN ('dev', 'collector', 'qa')),
  status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done', 'blocked', 'cancelled')),
  priority TEXT NOT NULL DEFAULT 'P1' CHECK (priority IN ('P0', 'P1', 'P2')),
  source TEXT NOT NULL DEFAULT 'qa' CHECK (source IN ('qa', 'collector', 'dev', 'user')),
  issue_id TEXT DEFAULT '',          -- 关联 QUALITY_ISSUES.md 中的编号（如 Q-010）
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 自动更新 updated_at
CREATE OR REPLACE FUNCTION update_task_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_task_updated_at ON task_queue;
CREATE TRIGGER trigger_task_updated_at
  BEFORE UPDATE ON task_queue
  FOR EACH ROW EXECUTE FUNCTION update_task_updated_at();

-- 索引
CREATE INDEX IF NOT EXISTS idx_task_assignee_status ON task_queue(assignee, status);
CREATE INDEX IF NOT EXISTS idx_task_priority ON task_queue(priority, status);

-- Row Level Security：service_role 可全权操作
ALTER TABLE task_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON task_queue
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 插入初始任务（从 QUALITY_ISSUES.md 当前 open 问题迁移）
INSERT INTO task_queue (title, description, assignee, priority, source, issue_id) VALUES
  ('Apify集成：开发apify_collect.py替换xhs_api', '用户已决定切换Apify云采集方案，需开发apify_collect.py模块，适配数据格式，部署验证。推荐actor: atomus/xiaohongshu-scraper', 'dev', 'P0', 'user', 'Q-012'),
  ('提供新的腾讯地图API key和SK', '当前腾讯key日配额超限，用户说可以配置新key做轮换。需要用户提供key+SK后配置到deploy.env', 'collector', 'P1', 'user', 'Q-011'),
  ('高德评论review_kind清理', '高德聚合评论被标记为diner，前端已分离，后端需将625条高德聚合评论的review_kind改为platform_aggregate', 'dev', 'P1', 'qa', 'Q-004'),
  ('frontier污染验证', '代码已修复（NON_FOOD_KEYWORDS黑名单）+数据已清理，但因cookie失效采集未恢复，无法验证搜索词是否为美食相关', 'collector', 'P1', 'qa', 'Q-010'),
  ('口味分批量补全', '1207家score_taste为空(82%)，需等Apify采集恢复、有真实UGC评论后运行scoring_engine.py --apply', 'collector', 'P1', 'qa', 'Q-005'),
  ('营业时间补全（剩余546家）', '高德key#1月配额有限，腾讯key明天0点重置后再跑一轮。高德上无营业时间的小众餐厅后续需从笔记提取', 'collector', 'P2', 'qa', 'Q-006');
