# 众包采集插件 · 数据契约 v1（CROWD-CONTRACT-001）

> PM 窗口独立开发 · 2026-10-02
> 原则：**格式、获取、回传、同步四方一致**——同一份 schema 同时约束插件端采集、HTTP 回传、服务端校验、库表落点。任何一方读到的字段名/类型/枚举都必须与此文档逐字一致。


## ⚡ v2 安全架构变更（2026-10-02 · smoke审计后）

**为什么改**：原方案插件用 anon key 直连表（GET crowd_tasks / POST crowd_proofs），
实测发现 crowd_tasks/proofs 无 anon policy → 插件拉不到任务、回传 42501 被拒；
且 crowd_participants 的 anon SELECT(pending|approved) 会泄漏全部参与者联系方式。

**新架构（本契约 v2 唯一有效版本）**：
```
参与者浏览器 (Chrome 扩展 v3.2.0)
   │ ① RPC crowd_fetch_tasks(participant_id)     — security definer，非黑名单即放行
   │    → 返回 {ok, tasks:[{task_id,pack_type,pack,target,kpi_min,quota_day}]}
   ▼
扩展本地队列 (chrome.storage.local)
   │ ② 按安全线节奏采集 → 组 envelope（格式不变，§2/§3）
   ▼
   │ ③ RPC crowd_submit_proof(participant_id, envelope) — security definer
   │    → 服务端校验：非黑名单 / sync_version=1 / note_url 含 xiaohongshu.com /
   │      rating∈[1,5] / rating_reason≥8字 / 幂等(unique 四元组)
   │    → 落库 + 回写 crowd_tasks.progress + crowd_participants.total_effective
   │    → 返回 {ok, accepted, rejected[], results[], new_progress}
   ▼
Supabase 表（anon 零权限，报名 insert pending 除外）
```
**安全边界（已实测）**：
- anon 对 crowd_tasks/proofs/reviews/settlements SELECT/INSERT/UPDATE/DELETE 全部 401 ✓
- anon 无法绕过 RPC 伪造回传（直写 proofs 被 42501 拒）✓
- 参与者隐私：crowd_participants 的 anon SELECT 策略已撤销 ✓
- 插件包仅含 anon key（sb_pub_，公开可分发），绝不含 service_role ✓
- SQL 实现见 cloud/sql/crowd_rpc_security.sql（可重复执行，幂等）

## 1. 参与方与数据流

```
参与者浏览器 (Chrome 扩展)
   │ ① GET /crowd_tasks?status=eq.open   → 任务包 task_pack（契约 §2）
   ▼
扩展本地队列 (chrome.storage.local)  — 离线可排队，重连续传
   │ ② 按安全线节奏执行采集 → 产出 proof 记录（格式见 §3）
   ▼
POST /crowd/proof  (带 participant_id + 签名)
   │ ③ 服务端 data_gate.crowd_validate() 校验
   ▼
Supabase 表：crowd_proofs / crowd_reviews / crowd_tasks
   │ ④ 状态回写（proof_status / task_status / 结算流水）
   ▼
结算：crowd_settlements（有效条数 × 单价）

注：task_queue 的 assignee 有 check 约束（仅 dev/collector/qa/pm，众包参与者
不是内部窗口角色），故任务包落独立表 crowd_tasks（契约 §4.1）。
若 crowd_tasks 尚未建表，crowd_pack.py 自动回退发布为 task_queue 中
assignee=pm 且标题带 [CROWD] 前缀的工单，插件拉取端两者都兼容。
```

## 2. 任务包 task_pack（插件从 task_queue 获取）

字段与 Supabase task_queue 行对齐，插件只读不改：

| 字段 | 类型 | 说明 |
|---|---|---|
| task_id | int | task_queue.id（**回传必须原样带还**，用于同步锚定） |
| task_type | enum | `store_pack` / `keyword_pack` |
| pack | array | 词包或店铺包：`["店名A","店名B",...]` 或 `["词1","词2",...]`，5-8 项 |
| target | enum | `notes`（收录笔记）/ `review`（口味评分）/ `both` |
| kpi_min | int | 该包最低有效收录条数（默认 5），未达标不计酬 |
| quota_day | int | 该任务单账号日采集上限（默认 20，安全线引擎读取，只降不升） |
| created_at | string(ISO8601) | 任务创建时间 |

## 3. 采集 proof（插件产出 → 回传 payload）

**回传信封**（POST /crowd/proof 的 body，顶层固定）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| participant_id | string | ✓ | 参与者注册 ID（uuid，参与协议时生成，插件本地保存） |
| task_id | int | ✓ | 原样回传（§2 锚定） |
| proof_seq | int | ✓ | 本次回传内记录序号，从 0 递增（断点续传排序用） |
| captured_at | string(ISO8601) | ✓ | 捕获时间（插件本地时钟） |
| sync_version | int | ✓ | 契约版本号=1（服务端拒绝不匹配版本） |
| items | array | ✓ | proof 记录数组，格式见下 |

**proof 记录 items[]（每条一篇笔记或一条评分）**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| kind | enum | ✓ | `note`（笔记收录）/ `rating`（口味评分） |
| note_id | string | ✓ | 小红书笔记 ID（URL 末段，如 explore/xxxx） |
| note_url | string(url) | ✓ | 完整 URL（服务端校验 https://www.xiaohongshu.com） |
| title | string | note 必填 | 笔记标题 |
| excerpt | string | 否 | 正文前 200 字摘要（脱敏后） |
| author | string | 否 | 作者昵称（**服务端脱敏存储**，仅保留首尾字符） |
| rating | number(1-5) | rating 必填 | 口味评分 |
| rating_reason | string | rating 必填 | 评分理由（≥8 字，含具体菜品/口感词，防空话） |
| matched_store | string | 否 | 插件侧锚定的店铺名（服务端用 entity_match 二次校验） |
| anchor_score | number(0-1) | 否 | 插件侧锚定置信度（服务端复核） |
| raw_query | string | ✓ | 本次搜索用的词包项（溯源） |
| client_ip_salt | string | ✓ | 客户端设备指纹盐（一机一号校验，不传明文 IP） |

## 4. 服务端库表（Supabase，建表 SQL 见 cloud/sql/crowd_tables.sql）

### 4.0 crowd_participants —— 参与者报名与管控（灵活报名闭环）
| 字段 | 类型 | 说明 |
|---|---|---|
| participant_id | text PK | `P-`* 参与编号（报名即发，直接可用） |
| display_name / contact | text | 报名信息（contact 回传前脱敏展示） |
| status | enum | `pending` / `approved` / `suspended` / `blacklisted` / `rejected` |
| quota_day | int | 审核时设定日配额（默认 20） |
| device_salt | text | 一机一号，首次回传绑定 |
| total_effective / reject_rate | int/float | 累计有效条数 / 拒收率（ingest 回写，风控参考） |

**管控闸门（两端双层）**：
- 插件端：`fetchActiveTask` 前先查本表，非黑名单（suspended/blacklisted/rejected）不发任务（popup 显示拦截原因）。
- 服务端：`crowd_ingest` 回传时复查，黑名单/暂停/驳回整包拒收（防绕过插件直发）。

### 4.1 crowd_tasks —— 任务包状态（与 task_queue 联动）
| 字段 | 类型 | 说明 |
|---|---|---|
| task_id | bigint PK 自增 | 独立于 task_queue（crowd 不是内部窗口角色） |
| pack_type / pack / target / kpi_min / quota_day | — | 与 §2 一致 |
| progress | int | 有效 proof 累计条数 |
| status | enum | `open` / `in_progress` / `fulfilled` / `closed` |

### 4.2 crowd_proofs —— 回传明细（校验后落点）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | bigserial PK | — |
| participant_id / task_id / proof_seq / captured_at / sync_version | — | 信封字段原样 |
| kind / note_id / note_url / title / excerpt / author / rating / rating_reason / matched_store / anchor_score / raw_query / client_ip_salt | — | §3 字段原样 |
| gate_status | enum | `accepted` / `rejected`（data_gate 判定） |
| dedupe_key | string | cjk_norm(title)+note_id 指纹，唯一约束防重 |
| unique(participant_id, task_id, proof_seq) | — | 幂等键 |

### 4.3 crowd_reviews —— 口味评分（仅 rating 类 accepted 后落此）
| 字段 | 类型 | 说明 |
|---|---|---|
| store_name | text | 锚定店铺名（entity_match 二次解析） |
| participant_id / rating / rating_reason / note_id / captured_at | — | 同上 |
| trust_level | enum | `crowd_single` / `crowd_crossed`（多参与者交叉后升） |

### 4.4 crowd_settlements —— 结算
| 字段 | 类型 | 说明 |
|---|---|---|
| id | bigserial PK | — |
| participant_id | string | — |
| period | string(YYYY-Www) | 结算周期 |
| effective_notes / effective_ratings | int | 有效笔记 / 有效评分（accepted） |
| unit_note / unit_rating | number | 单价（默认试点：0.5 / 1.0 元，可配置） |
| amount | number | 合计 |
| unique(participant_id, period) | — | 每周期一条流水 |

## 5. 同步一致性规则（防漂移，铁律）

1. **task_id 原样回传**：插件领取什么包，回传就必须带同一 task_id；服务端不认"看起来像"的包。
2. **sync_version 门槛**：契约版本不符 → 409 拒绝，插件弹更新提示。
3. **proof_seq 单调**：同一 participant+task 内 seq 必须严格递增；重复 seq → 幂等忽略，不重复计酬。
4. **gate_status 唯一权威**：计酬只认 `accepted`；`pending` 不结算、`rejected` 记录原因供参与者申诉。
5. **一机一号**：client_ip_salt + participant_id 绑定；同 salt 出现多 participant → 触发人工审计。
6. **断点续传**：插件本地队列未回传成功的 proof 不删除，重连后按 seq 续传；服务端按 (participant_id, task_id, proof_seq) 幂等去重。
7. **状态回写**：服务端校验完成后 PATCH crowd_tasks.progress / task_queue（fulfilled 时 PM 调度器自动标 done），插件拉取任务时可见进度，避免重复采集同一包。

## 7. 报名与管控（灵活报名闭环）

```
参与者                        PM/服务端
  │ ① apply.html 填写报名
  ├──────────────────────────▶ POST /crowd_participants (status=pending, participant_id=P-*)
  │                             
  │ ② 报名即用（P-编号）；异常时 crowd_admin.py 干预
  │◀─────────────────────────── 发放正式编号 P-XXXXXX + quota_day
  │                             
  │ ③ onboarding 填 P- 编号 → 插件 fetchActiveTask 先查管控闸门
  │ ④ 采集回传 → ingest 复查状态 + 累计 total_effective
  │ ⑤ 违规/异常 → suspend / blacklist → 插件端不再派任务、服务端拒回传
```

- **报名即用**：apply.html 匿名提交（anon key 仅可 insert pending 行），提交即得 P- 编号立即可用；风控后置（黑名单/暂停/驳回即时拦截）。
- **管控入口**：cloud/crowd_admin.py（list/suspend/blacklist/reject/stats），审核后置为风控抽查。
- **双层拦截**：插件端发任务前查状态；服务端回传时再查（防绕过插件直发）。
- **配额**：quota_day 审核时设定，服务端为上限，安全线引擎只降不升。

## 8. 安全线（插件硬编码，独立于本契约，见 safety_engine.js）

| 动作 | 阈值 |
|---|---|
| 日搜索 | ≤ quota_day（默认 20，max 30） |
| 搜索间隔 | 随机 60-120s（硬下限 60s，不可调） |
| 单次会话 | ≤15min 后强制冷却 30min |
| 浏览停留 | ≥30s/篇 |
| 触发"访问频繁" | 立即停 15min（只读恢复） |
| 一机一号 | 绑定 device salt，禁止多账号切换 |
