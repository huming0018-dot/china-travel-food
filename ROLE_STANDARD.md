# 角色工作标准 · ROLE_STANDARD

> **版本**：v1.0 | **发布**：2026-10-01 | **维护者**：PM窗口（CTFS_PM）
> **性质**：三执行角色（crawler / dev / qa）的**统一工作标准**，与 GOVERNANCE_MASTER.md 配套。
> **结构**：每个角色按同一标准定义 —— ① 数据需求及定义 ② 工作工具 ③ 工作模块职责。
> **冲突裁决**：与 GOVERNANCE_MASTER.md 冲突时以总纲为准；本文档只细化不更改。

---

# 一、CRAWLER（采集 · CTFS_爬虫工程师）

## 1.1 数据需求及定义

### 采集目标（要什么数据）
| 数据域 | 说明 | 用途 |
|--------|------|------|
| 餐厅基础 | 上海在营餐厅：名称/地址/坐标/菜系/营业态 | 主库底座 |
| 餐厅补全 | 电话/营业时间/评分/人均 | 详情可用性 |
| 食客证据 | 真实食客笔记/评论（小红书/B站） | 口味分证据链 |
| 权威榜单 | 米其林/黑珍珠上海名单对账 | 权威召回 |
| 主厨人物 | 主厨名+餐厅关联（含候选池） | 人物页 |
| KOL内容 | 美食作家/博主文章 | 内容补充 |

### 数据规范（进库硬标准，违反进不了 data_gate）
**餐厅必填**：name / address / lng / lat / cuisine / status
**评论必填**：restaurant_id / source_platform / review_kind / trust_level / content
**枚举值**：
- review_kind：`diner`（真实食客）| `platform_aggregate`（平台聚合）| `kol`（博主）| `media`（媒体）
- trust_level：`high` | `mid` | `low`
- status：`active`（营业）| `closed`（关店）
**硬标签**（连锁/预制/中央厨房）：必须有证据URL，否则不上标签
**候选数据**（未证实主厨/店铺）：进 lead_hypotheses（is_seed=true, status=hypothesized），**禁止**直接进事实表

### 质量要求（采集侧）
- 真实：每条数据可溯源（来源+采集时间）
- 无虚假通过：搜索有结果才算产出；连续空结果=stalled 非 saturated（Q-009教训）
- 覆盖：菜系/区域网格推进，CHECK A 覆盖率红灯=未完成

## 1.2 工作工具
| 工具 | 用途 | 备注 |
|------|------|------|
| **Apify**（atomus/xiaohongshu-scraper） | 小红书笔记/评论云采集 | 主力，Starter $19已生效；Token失效→ACTION用户 |
| 高德API | 电话/营业时间/评分/坐标 | cron :15/:35/:55；key配额→轮换 |
| 腾讯API | 电话/坐标 | 日配额凌晨重置 |
| B站 | 探店视频 | cron 6h |
| 权威榜单源 | 米其林/黑珍珠 | cron+router兜底 |
| KOL跨平台 | 美食作家 | cron 6h |
| **account_registry** | 账号状态唯一入口 | probe/mark/pick，不自己判定 |
| **map_quota** | 地图key配额账本 | 自动轮换 |
| **data_gate** | 入库二次验证 | 必须过闸 |
| cron调度 | watchdog/gap_pool/router等 | 无人值守 |
| sync.sh / task_helper | 开工/认领/留痕 | 每次工作必用 |

## 1.3 工作模块职责
| 模块 | 职责 | 调度 |
|------|------|------|
| **cloud_router** | 总调度中枢：按tick分派采集任务、检查pool存活（防假死） | cron */20 |
| **gap_pool** | 采集池：管理并发采集进程生命周期 | @reboot+entrypoint |
| **gap_runner** | 单任务执行：搜索→解析→过闸入库；stalled冷却不硬入库 | router |
| **cloud_discover** | 发现引擎：frontier扩展（须过滤非美食词，Q-010） | router |
| **cloud_amap_fill** | 高德补全：电话/营业时间/评分/坐标 | cron :15/:35/:55 |
| **cloud_phone_fill** | 电话补全（腾讯/高德） | cron :05/:25/:45 |
| **cloud_hours_fill** | 营业时间补全 | cron 凌晨4:00 |
| **cloud_coord_fill** | 坐标补全/纠偏 | cron 凌晨3:00 |
| **cloud_bili_collect** | B站探店采集 | cron 6h |
| **cloud_blackpearl_collect** | 黑珍珠榜单对账 | cron 6:20 |
| **cloud_michelin_collect** | 米其林榜单 | router兜底 |
| **run_batch** | 批量取证执行 | router/entrypoint |
| **comention_probe** | 同文提及探测 | cron 每小时 |
| **kol_cross** | KOL跨平台采集 | cron 6h |
| **ugc_longrun** | UGC长跑采集 | cron :39 |
| **watchdog** | 看门狗：进程存活检查+异常拉起 | cron :10/:30/:50 |
| **apify_ingest / apify_collect** | Apify小红书采集（dev实现代码，collector运行） | P0 |
| **account_repair → account_registry** | 账号探测/修复（迁移到registry） | 按需 |
| **xhs_cookie_pool → account_registry** | cookie池（Apify切换后归档） | 迁移中 |

---

# 二、DEV（开发 · CTFS_数据库及架构工程师）

## 2.1 数据需求及定义

### 负责的数据底座
| 对象 | 定义 | 验收口径 |
|------|------|---------|
| **schema** | 表/索引/视图/触发器（restaurant/comment/chef/hypothesis/task_queue等） | 迁移文件=数据库实际，0差异（Q-003教训） |
| **评分算法** | v4公式：0.45t+0.25d+0.18o+0.12e + provisional上限82 | 公式在迁移/代码/库三处一致 |
| **软广识别** | softad概率自学（贝叶斯/时间衰减/价位先验） | 准确率≥基线才上线（curate v4门） |
| **三大公共组件** | account_registry / common_core / data_gate | 见§7.4总纲验收 |
| **数据迁移** | db/migrations/*.sql | 可回滚、有记录 |
| **部署一致性** | Dockerfile/build脚本/容器内文件 | 部署必验证 |

### 数据规范（开发侧）
- 所有入库写入必须经 data_gate（dev自己实现+自己遵守）
- 全表查询必须分页（fetch_all，禁止 select * 大表）
- 所有新代码的 req/config/notify/log 走 common_core
- 账号状态读写只经 account_registry

## 2.2 工作工具
| 工具 | 用途 | 备注 |
|------|------|------|
| Python 3 / cloud/ | 全部后端模块 | 77个.py，L2/L3/L4归我治理 |
| Git + GitHub | 版本管理 | 一个任务一个commit |
| Supabase（PostgREST） | 数据库读写 | 分页查询 |
| Docker / build_on_server.sh | 部署 | 通配符打包（Q-007教训） |
| sync.sh / task_helper | 开工/认领/留痕 | 必用 |
| common_core | 统一req/config/notify/log | 自研自用 |
| data_gate | 入库验证 | 自研自用 |
| account_registry | 账号管理 | 自研自用 |

## 2.3 工作模块职责
| 模块 | 职责 | 状态 |
|------|------|------|
| **account_registry.py** | 账号统一管理（list/probe/status/mark/pick/summary） | ⏳ #11 P0，10-02前骨架 |
| **common_core.py** | 公共调用规范（req/config/notify/log） | ⏳ #12 P0 |
| **data_gate.py** | 数据二次验证（validate/cross_check/dedupe/admit/report） | ⏳ #13 P0 |
| **apify_collect.py** | Apify采集代码实现（Token/接口定义在collector侧） | ⏳ #15 P0 |
| **curate_v4.py** | 精选层dry-run（ML门，不准不上线） | ✅ 已建 |
| **health.py → common_core** | 通道/告警（13处import，迁core） | 迁移中 |
| **notifier → common_core** | 通知封装（10处import） | 迁移中 |
| **map_helpers / map_quota** | 地图工具/配额账本 | 保留 |
| **category_resolver / backfill_cuisine** | 菜系解析（L4确认去留） | 待合并 |
| **review_apify_fill + review_ugc_fill → review_fill** | 评论补数合并 | L4合并（带回归） |
| **scoring/评分相关** | 评分公式+重算（recalc_scores） | 维护 |
| **findings_* / selling_points_*** | findings管线/卖点 | L4确认用途 |
| **前端 app/** | 导航/筛选/详情/Feed（当前冻结） | 冻结，恢复由PM定 |

---

# 三、QA（质量 · 原CTFS_PM窗口）

## 3.1 数据需求及定义

### 质量验收口径（release_audit A–H）
| 项 | 检查 | 通过标准 |
|----|------|---------|
| A | 数据完整性 | 必填字段0缺失，覆盖率达标（口味≥90%/电话≥98%/营业时间≥98%） |
| B | 评分一致性 | 库公式=迁移=代码，0家不符 |
| C | 采集有效性 | 无虚假通过：有真实产出才=在跑 |
| D | 单店字段 | 电话/营业时间/菜系空比例达标（CHECK D/G） |
| E | 证据链 | 评分有食客证据，硬标签有URL |
| F | 回归 | 修A不坏B，抽样对比通过 |
| G | 覆盖率网格 | 菜系/区域网格无漏（CHECK A） |
| H | 真实渲染 | 前端页面实际渲染验收（恢复后） |

### 数据规范（QA侧）
- 问题台账：唯一真源=task_queue；QUALITY_ISSUES.md 只做摘要
- 每条问题：唯一issue_id + 唯一assignee + 状态 + 优先级
- P0不过夜、P1本周、P2排期
- 问题不登记=不存在

## 3.2 工作工具
| 工具 | 用途 | 备注 |
|------|------|------|
| **release_audit** | A–H全量审计（便携可复跑） | 每轮迭代必跑 |
| **task_helper** | 登记问题/查看队列/跟进闭环 | 真源操作 |
| **qa_broadcast** | TG统一播报（整合账号/配额/数据/任务/服务器） | 唯一通知通道 |
| **progress_broadcast** | 进度播报 | cron |
| **post_audit** | 录后校验（长期自运行） | cron 7:47 |
| **self_evolve** | 每日自检/自我迭代日报 | cron 1:00 |
| **红队测试** | 模拟用户/专家/博主/从业者/厨师老板/竞对挑刺 | 每轮迭代 |
| sync.sh | 开工/留痕 | 必用 |
| 服务器SSH | 实况核验（经代理） | Q-013后经Clash |

## 3.3 工作模块职责
| 模块 | 职责 | 调度 |
|------|------|------|
| **release_audit 套件** | A–H质量审计 | 每轮迭代 |
| **qa_broadcast.py** | 播报整合（账号/配额/数据/任务/服务器状态） | 定时 |
| **progress_broadcast.py** | 进度播报 | cron :03/:13... |
| **self_evolve.py** | 每日自检日报+自我迭代 | cron 1:00 |
| **post_audit.py** | 长期录后校验 | cron 7:47 |
| **QUALITY_ISSUES.md** | 问题台账摘要（真源=task_queue） | 持续 |
| **STATUS.md 监督** | 各窗口状态拉平核查 | 每日 |
| **task_queue 闭环** | 登记→认领→验证→关闭 | 持续 |
| **服务器连通监测** | SSH/容器/播报内置探测 | 持续（Q-013后） |

---

# 四、三角色衔接（谁产出谁消费）

```
crawler ──采集+过闸──▶ Supabase ◀──schema/算法── dev
   │                      │
   └──补全/账号状态──▶ task_queue ◀──登记问题── qa
                              │
                     PM调度/验收（唯一推动方）
```

**衔接铁律**：
1. crawler 入库必须过 data_gate（dev实现）→ 违反=QA打回
2. dev 建组件必须交付 PM 评审 → QA 验证无绕过
3. qa 发现问题立即登记 task_queue（唯一真源）→ PM 指派 → 对应窗口修
4. 三方状态以 task_queue + STATUS.md 对齐，**不私聊、不双写**
