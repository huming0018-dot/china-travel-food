# 爬虫模块总规范（Crawler Module Spec）

> 上位契约：`north-star-constitution.md`（口味唯一最高、宁空不假、机制优先）。
> 本文件定义 collector（采集/爬虫工程师）窗口的**完整工作边界与交付契约**：数据目标 → 爬虫方法 → 可用工具 → 管线 → 交付 dev → 验证数据包 → 经验回流。
> 通道层操作细则见 `cloud/COLLECTION_SOP.md`；机制绑定见 skill `references/mechanism-master-v4.md`。
> **spec→code 绑定原则**：本文件每条规定只有在同时满足 ①绑定确定性模块、②状态/账本留痕、③被某个闸门调用，才算「已实现」；只写在文档 = 未实现。

---

## 1. 数据目标（What we produce）

Collector 产出**五族数据**，每族有明确字段、口径、达标线与更新节奏。

| 族 | 内容 | 核心字段 / 落表 | 达标线（SLA） | 更新节奏 |
|---|---|---|---|---|
| **A 宇宙/目录** | 菜系×品类×场景×食材×形式的叶子全集与目标 | `cuisines`、`restaurant_cuisines`；`research/coverage/leaf_supply.json`、`ledger.json` | 无**合格空格**；薄格率<20%；米其林/黑珍珠对账 0 真缺；回归集 100% 命中 | 每日 stage6 |
| **B 事实** | 规模/工艺/出品/安全四轴 + 人均/电话/地址/坐标/营业时间 | `restaurants`：chain_type、central_kitchen、premade_risk、food_safety、price_avg、phone、address、location、opening_hours；`fact_claims` | phone ≥95%、location ≥99%、hours ≥90%、price ≥99%；关键字段 100% 带来源；**同址真重复=0** | 每小时/每日 fill |
| **C 口味（UGC）** | 真实食客堂食评价与口味分 | `reviews`；`restaurants`：score_taste、review_count、review_confidence | active 店有 score_taste 占比 ≥70%（基线 25%）；每店 ≥2 独立声音；无口味信号不打分 | 常驻/每日 |
| **D 动向（事件）** | 新店/首店/快闪/联名/飞行厨房/搬迁/闭店/主厨变动 | events 表/`research/events`；写回 restaurants.status、closed_date | 事件采集**接线自动跑**；去重；含起始日期 + 报名入口；关店三要素齐 | 每 6h/每日 |
| **E 关联（关系）** | 主厨 / 集团 / 品牌 profile 与关系 | chef/group profile；`restaurants.chef_name`、investor_info | 知名主厨/集团 100% 建档；每周跟踪 last_tracked_at | 每周一 |

**基线快照（2026-10-02）**：active 1497；phone 87.1%、location 99.7%、hours 63.3%、price 99.9%；有 score_taste 仅 376（25%）；24 叶子中 12 个合格缺口（6 空 + 6 薄）。

---

## 2. 爬虫方法（How we collect）

### 2.1 多抽样框（同一全集用多个独立框枚举，单框漏的由其他框补）
| 框 | 枚举方式 | 模块 |
|---|---|---|
| F1 地理框 | 行政区→商圈/马路→品类逐格 | 高德/腾讯 + patrol |
| F2 权威框 | 米其林/黑珍珠全量索引并与官方总数对账 | authority_sitemap / authority_compare / blackpearl |
| F3 集团/品牌/主厨树 | 从集团、品牌、主厨反向枚举所有门店 | group/chef tree |
| F4 社交框 | KOL/老饕种子 + 词矩阵 + 图遍历 | fleet_grid、kol_monitor、discovery |
| F5 地图 POI 框 | 高德/腾讯按区+品类拉 POI | cloud_amap_fill、empty_leaf_discovery |
| F6 滚雪球 | 同主厨/同品类/评论区交叉提及 | comention_probe、图遍历 |

候选必须记录 `discovery_frames[]`（被哪些框发现）；**多框或 ≥2 独立声音**才从 frontier 进入收录。

### 2.2 通道降级阶梯（自上而下优先，成本与封号最小化）
- **L0 公开/官方 API（免费、无封号）**：地图 REST（高德/腾讯）、米其林/黑珍珠公开页、官方公众号/新闻稿、集团/主厨树。
- **L1 匿名签名直连（免费、能力受限）**：xhs 签名 HTTP（浏览器标 restricted 的账号走签名仍 code0）；匿名搜索 = -101 死路；feed/详情需 xsec_token。
- **L2 网页只读（免费，部分需代理）**：SmartShanghai/TimeOut、B 站（单视频评论更开放）。
- **L3 登录账号 / Apify（兜底）**：仅用于无替代能力；Apify 跑 actor 的账号，**我方零封号**。

### 2.3 地毯式词根（标准模块：地毯搜索 + 可定制词根）
- 每叶子：语义词 **≥10**、每词 **≥4 篇**、**必采评论区**；词根配置化（`discovery_keywords`），加叶子只加配置。
- 事件词根独立维护：飞行厨房 / 客座 / 快闪 / 联名 / 首店 / 开业 / 搬迁 / 闭店 / 换主厨。
- 语义层：is=主营（决定菜系叶），serves=含有（仅标签）；地名/招牌陷阱词典（海南鸡饭≠海南、黄启云牛肉面=台湾菜、Lady M/聚福≠日式甜品）。

### 2.4 工程纪律
- 限速（搜索 ≤2 次/分、间隔 28s）、指数退避、熔断（整轮 0 达标才 trip）、断点续跑、幂等写、写后回读。
- 成本路由：**0 结果=$0 优先（atomus）**；opspilot 固定 $0.10/启动适合召回；sian 适合全文/评论与大品牌。
- **禁止**多账号轮换注册薅 Apify 免费额度（违反 ToS、关联封号）；我方账号不跑关键词搜索（唯一会封自己号的做法）。

---

## 3. 可用工具（Tools inventory）

| 工具 | 能拿什么 | 鉴权/成本 | 封号风险 | 边界 |
|---|---|---|---|---|
| 高德 REST（多 key 池） | POI、聚合星级、人均、电话、地址、营业时间 | L0 key / 免费有日配额 | 无 | 无点评正文，仅聚合星级 |
| 腾讯地图 REST | 同上、suggestion | L0 key / 免费有日配额 | 无 | 配额耗尽需跨源故障转移 |
| ARK 模型舰队（4 模型：deepseek-v4-1-flash 主力、doubao lite/turbo、glm） | 语义发现、候选假设、归类判断 | LLM key / 付费（极低） | 无 | 产出=假设，须过闸才晋升 |
| B 站（kol_monitor / bili_collect） | KOL 探店视频、提及、单视频评论 | L2 部分签名 / 免费 | 无 | 搜索需 wbi + 真实 cookie |
| 公众号/搜狗（kol_cross） | 公众号文章、KOL 痕迹 | L2 / 免费 | 无 | 搜狗常风控/验证码 |
| Apify·atomus | XHS 笔记/评论，按结果计费 | L3 / 0 结果=$0 | 账号是 actor 的 | 召回率略低，采信率最高 |
| Apify·opspilot | XHS 关键词搜索，固定 $0.10/启动 | L3 / 每次 $0.10 | actor 的 | 只认单数 keyword；memory=512 |
| Apify·sian | XHS 全文/评论，召回最大 | L3 / 按用量 | actor 的 | 适合大品牌/合集路由 |
| xhs 签名直连（xhs_api） | feed/详情/评论 | L1 签名 / 免费 | 低（仍需登录 cookie） | 匿名搜索 -101；须 xsec_token |
| 米其林/黑珍珠公开页 | 权威名单、tag | L0 / 免费 | 无 | 纯 requests 202 空体须浏览器 |
| SmartShanghai/TimeOut | 英文媒体店评 | L2 / 免费（经代理） | 无 | 旧搜索路径 404 需重定位 |
| notifier / watchdog / task_helper | 双通道通知、存活探测、任务认领 | 内部 / 免费 | 无 | 密钥只进 gitignored deploy.env |

---

## 4. 管线（Pipelines，端到端六段）

| 段 | 动作 | 脚本（示例） | 节奏 | 产物 |
|---|---|---|---|---|
| **P1 发现** | 多框枚举 → 标准候选信封 | fleet_grid_run、kol_monitor、cloud_amap_fill、group/chef tree、comention_probe | 每日/每 6h/每小时 | frontier / lead_hypotheses、raw_kol.jsonl |
| **P2 取证** | 取口味/事实证据 | review_apify_fill、xhs_api、evidence_pool、cloud_phone/coord/hours_fill | 常驻/每小时 | reviews、fact_claims |
| **P3 清洗校准** | 归一、去重、跨源校准、字段校验 | common（clean_phone/cjk_norm/addr_core）、entity_resolve、xhs_to_reviews | 写时 | 标准信封记录 |
| **P4 准入** | ≥2 独立声音 + 口味均分≥3.5 | admission_gate | 写时 | verdict（admit/hold/reject） |
| **P5 写库** | 唯一写入口、幂等、回读 | gate_apply、atlas_write、stage3_upsert | 写时 | restaurants/reviews 变更 |
| **P6 审计保鲜** | 质量门、巡逻、关店/字段保鲜 | stage4_audit、stage6_coverage(v5)、fact_evidence_gap、patrol、post_audit、duplicate/regression | 每日/每周 | 覆盖报告、缺口任务 |

调度实况：容器 food-cloud root crontab 共 24 条（见 `COLLECTION_SOP` §9）；主机 systemd 常驻 `food-apify-fill`。

---

## 5. 交付给 dev 的工作流（Collector → Dev handoff）

Collector 有**两类交付**，都经 Supabase `task_queue`（assignee/status/priority 用英文枚举）。

### 5.1 数据包（data package）—— 已采集/清洗、待 dev 二次验证
- 落盘布局：`research/packages/<YYYYMMDD>_<family>/`
  - `items.jsonl`（标准信封记录）、`sources.jsonl`（每条来源 url/kind/confidence/captured_at）、`manifest.json`
- `manifest.json` 字段：`package_id, created_at, family, items_n, files[], coverage_snapshot, open_gaps[], collector_notes, target_gates[]`
- 建任务：`task_queue{assignee:dev, status:todo, priority, title, source:"collector", description:含包路径}`。

### 5.2 工程任务（engineering task）—— 需 dev 接线/工程化
- 典型：把 live 脚本**纳入镜像构建**、新增/修复 cron 接线、补字段 schema、前端与 tag 联动（如隐藏连锁、三级菜单、事件浮窗）。
- 同样入 `task_queue(assignee:dev)`，附复现步骤与验收标准。

### 5.3 标准流程
1. collector 完成采集/清洗 → `bash sync.sh collector`（push 代码与数据包）；
2. `cloud/task_helper.py` 建交付任务并关联包；
3. dev `claim` → 二次验证（见 §6）；
4. collector 不直接改前端、不绕过闸门写最终收录；事实/口味写库统一收口 `gate_apply`。

---

## 6. Dev 二次验证后的数据包（Verified package）

Dev 以 `release_audit.py`（只读串联各质量门）做二次验证：stage4 / stage6(v5) / fact_evidence_gap / duplicate / regression / cross_cuisine / chain / cuisine_classify / entity_align / authority_compare / stage5。

### 6.1 通过（PASS）
- 产出**验证包**：`research/packages/<id>/verified/`
  - `canonical.jsonl`（可入库正名记录）、`provenance.jsonl`、`coverage_diff.json`（本次带来的覆盖变化）、`changelog.md`、`verified_manifest.json`
- `verified_manifest.json`：`package_id, verified_at, gates:[{name,pass,detail}], canonical_files[], residual_gaps[]`
- 经 gate_apply/atlas_write 入库回读；任务置 `done`；更新 HANDOFF。

### 6.2 不通过（FAIL）—— 退回 collector
- 产出 `rejection.json`：`gate, failing_items:[{id,reason}], suggested_fix`
- 任务改派 `assignee:collector, status:todo`（或 blocked 待凭据/决策）；
- collector 按失败清单**修机制/采集器**（不手工补单店），重新走 §5。

---

## 7. 经验回流流程（Feedback loop）

```
采集/验证/线上问题
   │
   ├─1) 记录 lessons-learned #n（现象 / 根因 / 通则）
   ├─2) 能固化 → 确定性脚本/质量门/词表/阈值，且必须被某闸门调用（否则算未实现）
   ├─3) dev 退回 / 点名店 → 更新词根/匹配器/归类器，并把点名店加入回归集（回归用例，非待办）
   ├─4) 信源一次发现 → source registry 长期注册、定 cadence 定时监控（不做一次性采集）
   └─5) 每日 02:00 self_evolve 复盘；发版前 release_audit A–H 全绿才发布
            │
            └─ 指标回流（覆盖率/字段完整率/需登录占比/单位成本/封号数）→ 播报 + 下一版采集计划
```

- 误判/软限流案例 → 更新探测与节奏（存活权威判据＝GET user/me code=0 且 guest=false，不用搜索判活）。
- 软广/污染新特征 → 回流 `softad_distribution` 与负面清单，阈值随品类区分（小吃 vs 正餐）。
- 每次闭环后更新 `HANDOFF.md` 与 `work_progress.json`，保证任务不丢失、可一键复现。

---

## 8. 角色边界一句话
- **collector（本窗口）**：对“数据能否稳定、完整、准确、低成本、零封号地拿到”负责，产出标准信封与数据包。
- **dev**：二次验证、工程化接线、纳入镜像、前端联动、入库收口。
- **pm**：调度、验收、裁决（QA 已并入），以真实口味为唯一收录原则。
