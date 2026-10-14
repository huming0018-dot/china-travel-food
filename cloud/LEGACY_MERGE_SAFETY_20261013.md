# 旧删除器安全审查（2026-10-13）

基线 main b235ce16b90711608e212abf24cd6daab6ac17db。

## 入口与调度

全仓（含隐藏配置，排除 .git）检索 merge_duplicates 及 migrate/fill_master：实际模块引用为 cloud_patrol 与 entity_resolve；唯一旧 CLI 自动调用为 patrol --apply。entity_resolve --apply 已禁用。旧脚本可直接运行，也可通过 import 调用两个写入函数，因此三处边界均封锁。
cloud/crontab.txt:29 配置 `52 */4 * * * ... cloud_patrol.py --apply`，仓库调度有触发条件；未核实生产已加载该配置或实际执行历史。
HANDOFF 历史段落记载曾通过该模块迁移子表并归并26簇，此为历史记录，不能证明 patrol 路径执行过，也不能证明数据受损。

## 最小修复

- patrol 保留重复检测，落非可执行 entity_review.json；apply 不启动旧删除器。其他巡逻修复维持原行为。
- 旧 --commit 参数保留但 argparse error，退出2，发生在 fetch_all/REST 前。
- migrate/fill_master 保留兼容签名但无条件拒绝；移除原子表迁移、补字段及 DELETE 实现，无环境变量或参数绕过开关。
- CLI dry-run 实际写 JSON 报告；标注旧品牌/距离候选不等于实体证据，不裁决 keep。master/dup 字段仅为旧建议，executable=false。
- 此次没有实现事务执行器，不授权其他独立实体脚本写入。恢复写入须另行完成事务、完整外键清单、人工裁决、keep 重检、备份与持久回执。

## 隔离验收

`python -m unittest discover -s tests -v`：29/29通过（既有25，新增4）。新增覆盖：--commit 在任何IO前拒绝；两个函数在模拟HTTP500环境下不发首个请求；距离单链误判与历史keep候选只能生成不可执行报告；真实 patrol main --apply 在模块/网络/子进程/告警被mock后检测重复并落报告，绝不启动删除器。既有测试验证keep增长/缩小/异常格式保护。部分失败测试证明已阻断首个写入，不声称实现回滚。`git diff --check`通过。

## 状态与后续

代码：本补丁提交 canonical 仓库，PR状态以GitHub为准。
测试：本地离线通过，无凭据、无生产请求。
部署：未执行。DevSpace 对已知原Mac项目路径返回 Internal error，未建立服务器连接。
线上审计：未执行。恢复连接后只读检查有效crontab、容器/镜像SHA、patrol.log及数据库审计/备份差异；不可用当前餐厅数量替代历史删除审计。部署时须同步cloud和实际/app/pipeline副本并通过正式镜像固化；仅隔离测试，不运行生产patrol --apply作验收。
