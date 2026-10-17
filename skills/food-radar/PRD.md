# food-radar PRD v3（合并态说明）

> v3.0 ｜ 2026-10-18 ｜ **执行规格以 [PROPOSAL.md](PROPOSAL.md) 为准**
>
> 本文件只保留"v2 → v3 改了什么、为什么"。完整路由、数据契约、
> 输出格式与安全边界均在 PROPOSAL.md 与 references/ 下，不在此重复。

## 变更摘要

| 维度 | v2（自建） | v3（合并） |
|---|---|---|
| 执行规格 | PRD.md 自述 | **PROPOSAL.md**（候选实现，已评审） |
| 记录层 | "待定 JSON schema" | **SQLite 单文件**，`schema_version=2` |
| 字段置信度 | 建议"落到字段" | **已实现**：`basis` 出处性质 + `valid_until` TTL 衰减 |
| 证据去重 | 建议"转载不算独立" | **已实现**：`origin_id` 必填去重键 |
| 失败语义 | 文字铁律 | **已实现**：`channel_unverified` 枚举 + `not proof of zero shops` |
| 安全 | 无 | **提示注入/命令注入/路径控制/身份伪造 四类防护** |
| 预检 | 全量检查，缺一即废 | **按任务通道**：`public`/`dianping`/`media` |
| 采集 | 自建 MediaCrawler + 点评直采 | 保留（候选无此能力），接入新语义 |
| 多用户 | 未做 | **已实现**：`surface+actor` 隔离，profile 路径按二者哈希 |

## 保留的自建部分

- `references/environment.md` — 本机工具实测基线（候选没有）
- `references/validation.md` — 校验铁律与 13 条踩坑（候选无）
- `scripts/dianping_fetch.py` 的推荐菜/团购解析 + 真实世界选择器
- MediaCrawler 采集层（小红书/抖音登录态持久化）

## 范围外（明确不做）

- 定时调度与自动推送：仅在用户明确要求后接宿主调度；`changes` 是日志不是调度器
- 多租户鉴权：SQLite 是宿主自用单文件，**不要当服务直接开放**
