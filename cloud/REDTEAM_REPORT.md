# 红队对抗审计报告 — 众包采集体系（v2.0 加固）

> PM 窗口 · 2026-10-02 · 审计对象：crowd RPC 层（crowd_submit_proof / crowd_fetch_tasks / 报名 RLS）
> 审计方式：以"投机者"身份对线上环境实测攻击 → 记录漏洞 → 修复 → 回归验证
> 所有测试数据（P-RED/P-RACE/P-RETEST/P-FINAL/P-CHK 系列）均已 service_role 清理

---

## 一、实测攻击清单与结果

| # | 攻击向量 | 修复前结果 | 危害等级 | 状态 |
|---|---|---|---|---|
| A1 | 同一设备无限批量注册（不传 device_salt） | ✅ 3/3 注册成功 | 🔴 严重 | 已修复 |
| A2 | 伪造 URL 绕过域名白名单（`evil.com/?goto=xiaohongshu.com`、`xiaohongshu.com.evil.net`） | ✅ 全 accepted | 🔴 严重 | 已修复 |
| A3 | 垃圾 note_id 灌库（超长/任意字符） | ✅ accepted | 🔴 严重 | 已修复 |
| A4 | 任务 DoS：攻击者可刷满 open 任务让正常参与者无任务可领 | ✅ 复现（任务被刷到 fulfilled） | 🔴 严重 | 已修复 |
| A5 | 去重绕过：title 变体 + proof_seq 自增刷量 | ✅ 5 次刷 2 accepted | 🟠 高 | 已修复 |
| A6 | 伪造口味评分（无真实笔记锚定） | ✅ rating 构造即 accepted | 🟠 高 | 已修复 |
| A7 | captured_at 伪造（未来/过去时间） | ✅ 未来时间可写 | 🟡 中 | 已修复 |
| A8 | 并发配额计数竞态（超 quota） | ✅ 10 并发 5 accepted | 🟡 中 | 已修复 |
| A9 | 幂等键绕过（同 note 换 proof_seq 重复回传） | ✅ 被 dedupe 兜底部分拦截 | 🟡 中 | 已修复 |
| A10 | 评分/笔记去重键混淆（对已收录笔记评分被误判重复） | ⚠️ 功能 bug（新发现） | 🟢 功能 | 已修复 |

## 二、修复内容

### 1. 报名层（R1 一机一号）
- **强制 device_salt**：RLS 校验长度 8-64 + 格式 `^[A-Za-z0-9\-]{8,64}$`
- **同设备唯一**：partial unique index `idx_crowd_participants_salt_active`（pending/approved 状态下 device_salt 唯一）→ 同机二报 409
- **participant_id 格式收紧**：`^P-[A-Z0-9-]{6,20}$`（与现有生成格式兼容）
- apply.html 客户端自动生成并持久化 device_salt（localStorage 复用）

### 2. 回传校验层（R2/R3/R6/R7）
- **URL 严格正则**：仅接受 `https://www.xiaohongshu.com/explore/[0-9a-f]{24}` 或 `/discovery/item/[0-9a-f]{24}` → 子域/路径/端口混淆全拒
- **note_id 格式**：强制 24 位十六进制
- **title 实质校验**：去标点/空白后 ≥2 字符
- **字段长度截断**：title≤100、excerpt≤200、author≤50、matched_store≤100、raw_query≤50
- **captured_at 时间窗**：不晚于 now()+10min、不早于 now()-7d
- **评分锚定**：rating 必须锚定已收录笔记（note_id 在 accepted 记录中存在）+ 理由去标点后 ≥8 字符

### 3. 防刷/去重层（R4/R5/R8/A10）
- **行锁串行化**：参与者行 `FOR UPDATE` → 并发配额计数不再竞态
- **循环内任务状态复查**：任务 fulfilled 后本批剩余条目全部拒（`item_task_fulfilled`）→ 防单次大批量刷满
- **dedupe_key 升级**：
  - note → `md5('n:' || 归一化title)`（去标点/空白/小写）→ 变体标题归一后同 key 被全局唯一索引拦
  - rating → `md5(参与者 || ':r:' || note_id)` → 每人每笔记一条评分，跨参与者评分可并存
- **拒收率自动风控**：累计条目 >20 且 reject_rate >0.6 → 自动 suspend（review_note 记录原因）

## 三、回归验证（线上实测）

| 测试 | 结果 |
|---|---|
| 无 salt 报名 | ✅ 401 RLS 拒绝 |
| 同 salt 二报 | ✅ 409 唯一索引拒绝 |
| 恶意 URL（子串/端口/路径穿越） | ✅ 全 rejected |
| 垃圾 note_id | ✅ rejected |
| title 变体去重（不同标点） | ✅ duplicate_skipped |
| 评分锚定（先收笔记再评分） | ✅ accepted |
| 重复评分 | ✅ duplicate_skipped |
| 无锚评分 | ✅ rejected |
| 未来时间 | ✅ captured_at_future 拒绝 |
| 并发 8 请求 | ✅ 行锁串行化，任务填满后新请求 task_not_open |
| 端到端（报名→领任务→回传→幂等） | ✅ 全通过 |

## 四、残余风险与后续

| 风险 | 说明 | 后续 |
|---|---|---|
| 格式合法但内容伪造 | URL/ID 格式校验无法验证笔记真实存在性 | 后续可加：Edge Function 抽查访问 URL 验证 HTTP 200 + 内容指纹 |
| 多号分散刷量 | 一机一号已防同机，但多设备多号仍可分散 | 依赖 20/日配额 + 拒收率风控 + PM 人工抽检；后续可加设备盐可信硬件绑定 |
| 客户端代码可改 | 调速类攻击（改 SAFETY_LIMITS）防不住——客户端不可信 | 服务端是唯一真相源：配额/RPC 校验在服务端强制执行；安全线收紧仍由服务端下发 |

## 五、关键结论

**架构原则确认：客户端一切输入不可信，服务端是唯一校验闸门。**
- 调速（改插件本地参数）只影响该参与者自己账号的封禁风险，无法突破服务端配额与校验
- 伪造回传字段（URL/ID/rating/时间）全部被服务端规则拦截
- 任务 DoS 通过"循环内状态复查 + 拒收率风控"双重缓解
- 一机一号通过"RLS + 唯一索引 + 报名页自动生成 salt"闭环

**本次加固不破坏现有参与者兼容性**：旧参与者（approved/pending）不受影响；新报名自动带 device_salt。
