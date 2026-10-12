# 地图采集故障转移修复与验收（2026-10-12）

基于 canonical `huming0018-dot/china-travel-food` main `ae58feb`。
修复单 Key 配额失败被提升成整个采集任务配额失败的问题。

## 状态合同

| 状态 | 含义与动作 |
|---|---|
| ok | 供应商正常响应，包括正常无搜索结果；空结果不重试 |
| rate | 单 Key 配额回执，仅内部使用，持久禁用至对应窗口后切 Key |
| no_budget | 配额账本与真实回执共同表明当前池没有可用额度 |
| reserved | 仍有额度但仅够电话预留；full 不侵占 |
| auth | Key、签名、来源或权限失败，短时熔断 30 分钟，不当配额耗尽 |
| network / error | 网络、HTTP、解析或其他服务错误，保守计一次请求，有限切 Key |
| retry_limit | 本次最多四把 Key 的上限已到，仍存在未试 Key；不得报整池耗尽 |
| unconfigured | 没有配置该供应商 Key，不等同额度耗尽 |

`MQ.call` 每次最多尝试四把不同 Key；网络和服务错误切换前等待
0.25 / 0.5 / 1 秒，单 Key 配额与鉴权错误直接切换。
所有请求仍由 acquire 保护电话预留，report 维护原账本；保留原月/日预算桶和上限。
共享 map_helpers 删除外层重复轮换，避免请求上限被放大为 N×4，旧调用方返回形状保持兼容。

全字段采集对高德和腾讯均使用 consumer=full，继续通过既有匹配质量门。
只有两个供应商均为 QUOTA/YIELD 时停止；其中存在预留保护就安静 yield。
鉴权/网络失败不会计作门店无匹配，也不增加门店 fail 惩罚。
高德正常无匹配而腾讯额度不可用时，继续下一候选，不误报全池耗尽。
腾讯证据使用腾讯来源 URL 和 source_platform，不再错误挂到高德。
账本新增无密钥的最近状态码/时间；fill_stats 新增 quota_snapshot 和 service_errors。

`--limit` 和历史 amap_used 仍是逻辑搜索计数，故障转移的一次逻辑调用可能包含多个
实际 HTTP 请求；真实尝试计数以配额账本为准。默认最多 40 次逻辑主搜/降级查询，
腾讯兜底最多两种查询，每种最多四把 Key。不应将 84/5000 当供应商实时余额。

## 官方错误码核对

- 高德官方 https://lbs.amap.com/api/webservice/guide/tools/info ：10044 是账号维度日调用量超限；
  10003 为日访问量超限；10001/10005—10009/10012/10013 为 Key/来源/签名/权限问题。
  修正旧代码将 10044 封至月初的处理，改为北京时间次日零点；不清空月用量。
- 腾讯官方 https://lbs.qq.com/service/webService/webServiceGuide/status ：121 为 Key 日量，
  110/111/112/113/190/199/311 为来源/签名/IP/权限/无效 Key；347 为正常无查询结果。
- 新代码在 acquire/snapshot 时滚动北京时间日/月窗口。到点开放尝试不代表供应商已恢复。
- 不推断同账号不同 Key 是独立额度，不扩大既有本地预算。账号归属映射仍是后续工作。
- 历史账本没有真实代码的 monthly_quota 禁用记录保留，不能仅据本次源码变更自动清除。

## 隔离验收

运行 `python -m unittest discover -s cloud/tests -p test_map_failover.py -q`：23 项通过。
三个修改模块 py_compile 与 git diff --check 通过。所有 HTTP 都打桩，账本和统计写临时目录，
数据库模块隔离，无生产 API 或数据库调用。

覆盖首 Key 超限/失效→次 Key 成功、腾讯成功兜底、全池耗尽、预留保护、全部鉴权失败、
网络失败及短退避、请求上限、正常空结果、真实回执格式持久化、北京时间零点、
日/月窗口滚动、10044 跨日恢复且保留月用量、腾讯无效 Key/347、混合网络/配额错误、
弱匹配拒绝，以及 main 不将服务错误计入门店 fail。

## 生产状态与后续验收

本次服务器终端未可用，DevSpace 恢复返回 Internal error；未部署、未重启容器、
未手工修改配额账本、未运行生产采集。交接中的 84/5000、1193 候选和
腾讯预计 10-13 00:00 恢复均未通过最新生产日志独立核验。

接通服务器后：先保存部署前日志/配额账本的脱敏快照，按
`cloud/CONTAINER_REBUILD_RUNBOOK.md` 将已合入 main 的修复烘焙进镜像；
容器内核验三个模块版本和 py_compile。优先观察现有 cron 的一次有限批次，
核对 fill_stats 的 candidates/called/service_errors/no_match/quota_snapshot、实际剩余
候选及真实回执。不得删除 dead 或提高预算来强行验证，不进行批量额度探测。
回退时恢复上一镜像和源码版本，保留配额与 POI 缓存持久卷。
