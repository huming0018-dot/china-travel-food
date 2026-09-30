-- 018_add_pm_role.sql
-- 为task_queue表添加pm角色支持

-- 删除旧约束
ALTER TABLE task_queue DROP CONSTRAINT IF EXISTS task_queue_assignee_check;

-- 添加新约束（包含pm）
ALTER TABLE task_queue ADD CONSTRAINT task_queue_assignee_check 
CHECK (assignee IN ('dev', 'collector', 'qa', 'pm'));
