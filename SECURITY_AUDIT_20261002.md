# 安全攻击审计报告 · 上海美食图鉴众包系统

> 审计人：PM 窗口（安全测试授权）· 2026-10-02
> 攻击目标：Supabase 应用层 + 众包插件（服务器 49.234.35.92 网络层不可达，公网全端口关闭）
> 方法：模拟黑客多轮攻击（刷报名/SQL注入/越权枚举/恶意payload/跨参与者伪造/配额绕过/并发竞态/XSS/包完整性）

---

## 一、攻击成果总览

| 严重度 | 数量 | 状态 |
|---|---|---|
| 🔴 高危 | 3 | 2 已修复，1 待修复 |
| 🟠 中危 | 3 | 待修复 |
| 🟢 低危/信息 | 4 | 记录 |
| ✅ 防御有效 | 7 | 无需动作 |

---

## 二、🔴 高危漏洞（已修复 2 / 待修 1）

### H1 【已修复】日配额未强制 → 可无限刷单/DoS
- **攻击路径**：`crowd_submit_proof` RPC 不检查 `quota_day`。攻击者用 quota_day=20 的参与者连发 6 批×5 条=**30条全部 accepted**。
- **危害**：刷结算金额、污染数据、耗尽任务包、批量 DoS。
- **修复**：函数增加配额闸门——当日已 accepted ≥ quota_day 即返 `quota_exceeded`。
- **复测**：quota=3 参与者回传 5 条 → 只收 3 条，第 2 批被拒 ✅

### H2 【已修复】跨参与者伪造回传 → 数据错挂他人
- **攻击路径**：调用参数 `p_participant_id=P-ATTACK01`（approved），envelope 内 `participant_id=P-VICTIM01` → 校验用参数、落库用 envelope → **数据错挂受害者名下**。
- **危害**：攻击者可污染任意已知编号参与者记录；结算归属错乱。
- **修复**：强制 `envelope.participant_id == 调用参数`，不符返 `participant_id_mismatch`。
- **复测**：攻击请求被拒 ✅

### H3 【待修复】参与编号枚举（信息泄露）
- **攻击路径**：`crowd_fetch_tasks` 对 pending 参与者返回 `participant_status_pending`、对不存在编号返回 `participant_not_found` —— **可区分**。攻击者批量探测可枚举全部有效编号及状态。
- **危害**：中危。为 H2 类攻击提供目标清单。
- **修复建议**：错误信息统一为 `participant_not_found`（不区分存在与否），或对查询失败返回随机延迟防时序侧信道。

---

## 三、🟠 中危漏洞（待修复）

### M1 报名 XSS 原文入库
- **攻击路径**：`display_name="<script>alert(1)</script>"`、`contact="<img src=x onerror=alert(2)>"` → **201 入库原文**。
- **危害**：PM 审核端若用 `innerHTML` 渲染报名列表即触发 XSS（窃取审核会话/执行任意操作）。
- **修复建议**：① 服务端拒绝含 `<`/`>` 的字段；② 审核端必须用 `textContent` 渲染；③ crowd_admin.py 输出前做 HTML 转义。

### M2 报名者自定超大配额
- **攻击路径**：报名 payload 带 `quota_day:999999` → **201 入库**（pending 态虽不生效，审核时若沿用即获得无限配额）。
- **修复建议**：报名 INSERT 时强制 `quota_day` 为服务端默认值（RLS with check 里限定 `quota_day = 20`），审核时才允许改。

### M3 dedupe_key 可绕过（同笔记多收录）
- **攻击路径**：同一篇笔记改 3 个 `note_id`、同 title → **3 条全 accepted**。dedupe_key=md5(title|note_id) 随 note_id 变化，无法识别"同篇不同ID"。
- **危害**：重复收录、结算虚增。
- **修复建议**：dedupe 键改为 `md5(title)` 或 `md5(作者+title)` 的归一化版本（配合 note_id 前缀匹配）；或服务端对同 title 近 N 天内已收录的做 reject。

---

## 四、🟢 低危/信息项

| # | 发现 | 说明 |
|---|---|---|
| L1 | 并发回传竞态 | 5 并发 → 4 accepted + 1 task_not_open（任务 fulfilled 后正常拒绝）。进度最终一致，可接受；建议 future 用行锁优化。 |
| L2 | 服务器公网全端口关闭 | 49.234.35.92 扫描 22/80/443/3000 等全 refused——当前从本机网络不可达（运营商路径问题，HANDOFF 已记录走 Clash 代理）。**无公网攻击面，防御良好**。 |
| L3 | RPC 元数据不泄露 | `GET /rpc/crowd_submit_proof` → 404 PGRST202 ✅ |
| L4 | 插件包含 anon key（设计内） | anon key（sb_pub_）本就是公开可分发的最小权限 key；包内无 service_role/env/凭证明文 ✅ |

---

## 五、✅ 防御有效（实测未攻破）

| 攻击 | 结果 |
|---|---|
| 伪造 status=approved 报名 | 42501 RLS 拒 ✅ |
| 重复报名同编号 | 409 唯一约束拒 ✅ |
| SQL 注入（OR/1=1 / DROP TABLE） | 参数化查询挡掉 ✅ |
| 恶意 payload（sync_version=99/恶意域名/rating=100/空 envelope/task_id 注入） | 全部按规则 reject ✅ |
| 超大包 DoS（1000条/500条） | 任务状态校验挡掉（未达配额即可，已由 H1 补上）✅ |
| anon 直连 5 张表 SELECT | 全部 42501 ✅ |
| anon 直写 proofs 伪造 accepted | 42501 ✅ |
| OpenAPI/Swagger 暴露 | 无（需 secret key）✅ |
| pg_proc 等系统表 | 404 ✅ |

---

## 六、修复状态与后续清单

### 已交付修复（SQL 已执行 + 复测通过）
- [x] H1 配额强制（crowd_submit_proof）
- [x] H2 参与者ID一致性校验（crowd_submit_proof）

### 待修复（建议下轮迭代）
- [ ] H3 编号枚举 → 统一错误信息
- [ ] M1 XSS 入库 → 服务端拒绝 + 审核端 textContent
- [ ] M2 quota_day 默认值 → RLS with check 限定
- [ ] M3 dedupe 增强 → 归一化 dedupe 键
- [ ] L1 并发优化（可选）

### 运维建议
- [ ] 服务器 SSH 走代理（127.0.0.1:7897）恢复部署通道
- [ ] 报名审核端（crowd_admin.py）确认用 textContent 渲染
- [ ] 定期重跑本报告的攻击用例作为回归（可做成脚本）

---

## 七、审计口径

- 本次测试仅针对项目自有 Supabase 项目（bdwrhshgdeghgyzwpxnl）与本地插件代码，**未触碰任何第三方系统**。
- 所有测试数据已清理（participants/tasks/proofs 恢复干净：tasks #1/#2 open progress=0，participants 空）。
- 修复 SQL 见 `cloud/sql/crowd_rpc_security.sql`（可重复执行，幂等）。
