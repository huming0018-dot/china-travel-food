# 专项审计报告 · 按历史问题复盘 + Ponytail精简方案

审计时间：2026-10-02
代码规模：120文件 / 26,356行 / 29个cron任务

---

## 一、历史问题专项复盘

### 专项1：虚假成功（登录显示OK但实际没工作）

**出过的事**：小红书账号登录返回成功、cookie有效，但采集器实际没在跑，空转几小时才发现。

**代码现状**：
- `xhs_qr_login.py:153` 有验证：`web_session + id_token` 双标志才算登录成功
- 但只验证了"登录态"，没验证"数据回流"

**问题根因**：登录验证 ≠ 采集验证。需要一个"心跳验证"：登录后5分钟内必须有raw数据写入，否则判定为虚假成功。

**修复建议**：在 `progress_broadcast.py` 已有停滞检测（60分钟无增长报警），但60分钟太长。缩短到15分钟，并增加"登录后首次数据延迟"检测。

---

### 专项2：Apify费用事故（$5额度超支到$18.94）

**出过的事**：预算门基于错误单价，toolzerhub跑了134次×$0.10=$13.40，无人发现。

**代码现状**：
- `review_apify_fill.py` 有 `price_per_run`、`FREE_COST_CAP`、`remaining_credit()` 三重门
- 但 `ab_compare.py`、`events_apify.py` 各有独立的预算逻辑，不统一

**问题根因**：
1. 预算门分散在3个文件，各算各的，不共享
2. toolzerhub标记price=0，绕过了预算门
3. Apify API计费有延迟，实时查询的remaining_credit不准

**Ponytail方案**：3个预算逻辑合并成1个 `cost_guard.py`，所有付费采集都过同一个门。预计砍200行重复代码。

---

### 专项3：OOM断连（SSH反复Connection refused）

**出过的事**：2GB服务器跑29个cron任务，OOM killer杀掉sshd。

**代码现状**：crontab.txt有29个任务，每小时跑5-8个Python进程。

**问题根因**：任务太多太碎。高德/电话/坐标/营业时间各自一个cron，每个都import一套common+requests，内存重复加载。

**Ponytail方案**：29个任务合并到6个：
| 合并后 | 原来的任务 | 频率 |
|---|---|---|
| `cloud_fill_batch.py` | amap_fill + phone_fill + coord_fill + hours_fill + hours_fill2 | 每2小时 |
| `cloud_router.py` | 浏览器调度（不动） | 每20分钟 |
| `progress_broadcast.py` | 播报（不动） | 每小时 |
| `night_patrol.py` | patrol + softad + curate + reconcile + post_audit | 每天凌晨一次 |
| `kol_collect.py` | kol_cross + kol_monitor + bili_collect | 每6小时 |
| `watchdog.py` | 看门狗（不动） | 每20分钟 |

预计cron从29个降到6个，内存占用降60%。

---

### 专项4：TG通知刷屏/发JSON

**出过的事**：gate_apply把 `{"apply":true,...}` 原始JSON发到TG；同一告警每30分钟重复发。

**代码现状**：31处notifier调用，4处发原始JSON。

**Ponytail方案**：
- 4处JSON dump全部改成一行人类可读摘要
- notifier.py已有cooldown机制，但各文件参数不统一（有的3600秒，有的7天）
- 统一常量：INFO cadence=3600，WARN cooldown=86400*7，ACTION nudge每天一次

---

### 专项5：空值/数据质量

**出过的事**：`'NoneType' object is not iterable` 错误；78%店铺品味分空。

**代码现状**：275处空值判断（`is not None`、`or []`、`or {}`）。

**问题根因**：采集链路太长，每个环节都可能丢数据，但没人在入口校验。

**Ponytail方案**：在写库入口加一个统一校验层，不通过的数据直接拒收并记日志，不要让它流到后面的环节才报错。

---

## 二、Ponytail精简方案：2.6万行 → 目标1.2万行

### 可以直接砍掉的（YAGNI）

| 模块 | 行数估算 | 理由 |
|---|---|---|
| `_archive/` 整个目录 | ~3000行 | 归档死代码，没人用 |
| `vendor/pipeline/_archive/` | ~2000行 | 同上 |
| 重复的地图API封装（36个文件各自import） | ~1500行 | 统一到map_helpers.py |
| 重复的写库逻辑（57个apply/write/patch） | ~2000行 | 统一到一个写库层 |
| 重复的预算逻辑（3处） | ~300行 | 合并到cost_guard.py |
| 未启用的cron任务对应的脚本 | ~1000行 | 检查哪些cron已经注释了但脚本还在 |

**预计可砍：~9800行，从26356 → ~16500行**

### 可以合并的

| 合并项 | 原来 | 合并后 |
|---|---|---|
| 5个地图补齐脚本 | amap/phone/coord/hours/hours2 | 1个batch脚本 |
| 3个KOL采集脚本 | kol_cross/kol_monitor/bili | 1个脚本 |
| 3个预算逻辑 | review_apify/ab_compare/events_apify | 1个cost_guard |
| 4个门控写库 | gate_apply/curate_gate/chain_review/candidate_apply | 1个apply层 |

---

## 三、立即行动清单

| 优先级 | 动作 | 预计效果 |
|---|---|---|
| P0 | 修4处JSON泄漏到TG | 你不再看到原始JSON |
| P0 | 合并cron任务从29→6 | 解决OOM断连 |
| P0 | 统一预算门到cost_guard.py | 防止Apify费用事故重演 |
| P1 | 删_archive/死代码 | 砍5000行 |
| P1 | 统一写库层 | 砍2000行 |
| P2 | 引入logging替代print | 可维护性提升 |

**目标：26356行 → 15000行以内，cron 29→6，TG不再发JSON，OOM解决。**
