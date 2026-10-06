# v3.4.7 独立验证报告

验证对象：`crowd_extension/` @ v3.4.7（manifest 3.4.7，SW = src/background_v347.js，git 5774caf）。
验证方式：与实现方零协作——独立读 diff、独立取证服务端 SQL、用既有 harness 全量重跑 + 新写 27 项针对性补测。**未改插件代码，未执行 publish.sh。**

## 1. 既有套件全量重跑（对 v3.4.7）

| 套件 | 结果 |
| --- | --- |
| run-all.js（S0/A–E/F/G） | **47/47 通过** |
| run-extra.js（X1–X13） | **15/15 通过** |
| run-extra2.js（X14/X15） | **8/8 通过** |
| run-fixes.js（R1–R11，v3.4.6 修复回归） | **26/26 通过** |

合计 **96/96**。四个套件 SW 未捕获异常 0、页面异常 0、生产 Supabase/小红书真实请求 0。
（诚实备注：run-extra2 与 run-fixes 首轮各因 chrome-extension 页导航超时崩了一次，重跑即过——harness 的偶发竞态，非插件问题；另一会话对 harness 的适配改动（SW 文件名匹配 + 种子补 agreed_at）我逐行核过，纯机械适配，未弱化任何断言。）

## 2. 针对性补测（run-v347.js，27/27 通过）

**V1 同意门与队列解耦（发布安全关键）✅**
participant_id 存在但无 agreed_at（老安装升级形态）：`fetchActiveTask` 被拦（gate_block_reason="未完成知情同意"），`doCollectOnce` → no_task；滞留队列的 4 封信封全部真实发出并排空——`uploadProofs` 不查同意门，`doCollectOnce` 的 upload-first 也在门禁之前。**老安装升级不丢滞留数据，成立。**

**V2 F12 认证熔断 ✅**
401×3 → auth_fail_count 1→2→3 递增并持久化；第 3 次后 quota_blocked_until ≈ +30min、gate_block_reason 含"认证连续失败"（popup 可见）；全程信封不丢、不进死信。恢复 200 → 队列排空、计数清零。403 同路径。原"401 直接死信清队列"的灾难路径已消除。

**V3 F14 必拒条目预检 ✅（附 1 条生产观察）**
真实采集链路（伪搜索页 4 卡片）："烤"(剥离后 1 字)、"！"(剥离后 0 字)、空标题卡 三条全丢，只有"烤肉"送出（F14KEEP01），SW 日志 `F14 预检丢弃必拒条目 x3` 落痕。
**观察**：题目要求的用例 (iii)（标题空+摘要 15 字应保留）在自动采集链路**不可达**——content.js 列表页 excerpt 恒为 null，doCollectOnce 又只开搜索页，所以进预检过滤器的条目永远不带 excerpt，`excerpt≥10` 这个保留分支在生产自动采集里是死分支（无碍安全：只是少用一条豁免）。该分支的正确性只能静态确认（谓词本身：`stripPunct(title)<2 && excerpt.trim()<10 → 丢`，逻辑无误）。

**V4 F10 last_sid 去重 ✅**
同一 submission_id 的 ok 回执重放两次：kw_state accepted 2→2 不翻倍，last_sid 记录在案；换新 sid 正常累计 2→4；keyword_progress 权威分支整行覆盖时 last_sid 保留（accepted=7 覆盖 + last_sid 不丢）。

**V5 F15 alarm 不饿死 ✅**
两次 initBackground，upload_retry 的 scheduledTime 完全不变（先查后建生效）。

**V6 F13 warmup NaN ✅（附带探针）**
first_run_date 写坏成 "garbage-date" → 回退 fraction=1，canSearch 正常放行且 quotaLeft 为有限数（旧版会 NaN 静默失效）。

**V7 F16 done_task_ids 封顶 ✅（附带探针）**
200 封顶滚动：塞入第 201 个后长度仍 200，最旧的被挤出。

## 3. 问题3 正面回答：场景E 的"反驳"成不成立

**不成立。** run-all 场景E 的 crowd_fetch_tasks 响应是我自己写的 mock（harness.js 的 mockRoutes，body 里的 `safety_limits:{quota_day:10}` 是我亲手编的）。它只能证明"客户端遇到该字段时会正确处理"，证明不了"现行服务端确会下发"。

而且我取证了仓库里最新服务端定义，结论反过来支持原审计判断：
- `crowd_fix_v340_pause.sql:67-77`（crowd_fetch_tasks 最新定义）：tasks[] 元素只有 task_id/pack_type/pack/target/kpi_min/quota_day/progress/claimed_until——**没有 per-task safety_limits**。真正下发的是顶层 `safety.limits`（`:30`），客户端那条路径（`d.safety.limits`）是活的。
- `crowd_fix_v345_item_quota_replay.sql:655-663`（crowd_submit_proof 成功响应）：`{ok, submission_id, accepted, rejected, results, new_progress, keyword_progress}`——**没有 task_status**。

所以 F11 的"死代码"判定对这两个字段原本是对的；v3.4.7 注释里"经测试反驳/现行服务端确会下发"的措辞不成立。保留防御分支本身无害（缺失即 null no-op），但注释应当修正，否则是在给错误认知留档。（注：我的取证基于仓库 SQL 文件；生产库是否跑了别的版本我无从验证。）

## 4. v3.4.7 新引入/残留问题（如实说）

按严重程度，都不算阻塞发布：

1. **【低】F12 熔断恢复后 park 不自动解除**：认证恢复（200 回执）后 quota_blocked_until 仍保持 +30min，采集要等到期才自然恢复。回传不受影响（信封正常排空）。若要"恢复即解除"，需在成功分支清 quota_blocked_until——但保守滞留也说得通，看产品取舍。
2. **【低】F12 熔断只拦采集、不拦回传**：熔断期内信封仍按各自退避节奏重试（每次 401 重新刷新 30min 熔断）。数据安全无副作用，但"暂停 30 分钟"对回传通道不成立——注释/文案略有夸大。
3. **【信息】F14 的 excerpt 豁免分支是死代码**（见 V3 观察）：列表页条目 excerpt 恒 null。不影响正确性，但说明该分支从未被生产路径执行过。
4. **【信息】F12 计数复位口径**：非 auth 的临时失败（如 500）会把 authFails 清零——"连续 3 次"是按信封处理序列算的，与网络抖动交错时熔断可能不触发。与注释"连续"一致，知晓即可。
5. **未发现** F6/F10/F13/F15/F16 引入的新问题；v3.4.6 的全部修复（竞态 merge、看门狗持锁、词表、风控透传等）在 v3.4.7 上回归无损。

## 产物

- `results/v347.json`（27 项补测明细）、summary/extra/extra2/fixes.json（96 项重跑明细）
- 复跑：`node run-all.js && node run-extra.js && node run-extra2.js && node run-fixes.js && node run-v347.js`
