# Telegram 主告警 / 外部看门狗可靠性修复

基线：main f35dd8ddb10f2df456fbef606e883e3073efef9b。

## 已核实的问题

- health 优先数据库中继，外部看门狗只有反代和官方直连。
- 生产只读核查：crowd_notify_tg(text,text) 为 SECURITY DEFINER，允许 anon、authenticated、service_role；校验 ops_secret。
- 该函数调用 net.http_post 后直接返回 ok=true / request_id，只表示排队，不能证明 Telegram 发送成功。
- ALERT_WEBHOOK 在发送函数中未使用；已经移除 health、部署模板和 cron 环境传递的配置说明。HANDOFF 旧日期段落保留为历史记录，不代表当前能力。

## 修复

统一中继→反代→官方；通知专用 secret 与低权限 API key 可供看门狗使用。
两个新增 RPC 封装既有中继，回执查询只对封装登记的请求返回布尔结果。
登记表启用 RLS，撤销 public/anon/authenticated 表权限；函数固定空 search_path，撤销 PUBLIC EXECUTE，再明确授予调用角色。
看门狗断网持久化重试，主告警未送达不进入冷却。中继超时可能造成重复发送，采用告警送达优先的降级行为。

## 代码验证

- Python unittest 16 项通过，两入口分别覆盖中继成功、中继失败、反代不可达、官方失败、完全断网，以及异步回执、鉴权头、日志脱敏、冷却、断网队列。
- PGlite 33 项 SQL/ACL 检查通过，包括迁移重复执行、anon/authenticated 调用、错误/空 secret、空/超长文本、未登记请求、Telegram false/HTTP 错误/超时/无效 JSON、应用旧配置兼容。
- Python 编译、entrypoint bash 语法、git diff --check 通过。

## 部署与送达：尚未完成

本轮 DevSpace open_workspace 返回 Internal error；当前环境没有 food_cloud_deploy 私钥。
历史记录指向广州 139.199.90.169:/home/ubuntu/food-watchdog，但未取得该机 notify.env、cron、文件版本、出口测试或通知日志。因此不能认定当前部署能够可靠告警，也不能认定曾经实际丢失通知。

下一步严格按 external_watchdog/README.md 的分层验收执行。不得为了测试运行具有 Stop/Start 能力的 food_watchdog.main；只运行通知自检。
数据库迁移、GitHub 合并及真实消息结果应在执行后追加本文件，不能预填。

## 工具限制

Supabase CLI migration new 已生成迁移文件，但附带遥测请求被自动审批拒绝；没有重试该 CLI 请求。隔离测试不依赖 CLI。
