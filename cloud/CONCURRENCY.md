# 众包美食家 · 并发模型与回流安全（v3.1）

> 本文回答：**多个远端参与者（多线）并发采集/回传时，系统如何保证不丢数据、不重复计酬、不虚假通过？并发监听如何不错乱？**

## 一、三层并发架构总览

```
┌─ 插件端（每个参与者一台设备，各自独立）─────────────────┐
│  service worker 单线程 + alarm 心跳 + _running 互斥       │
│  本地 proof_queue（最多 100 条）→ 串行 RPC 回传           │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP (anon key, security definer RPC)
┌──────────────▼──────────────────────────────────────────┐
│ 服务端 RPC（并发安全核心）                                 │
│  ① 参与者行锁 FOR UPDATE      → 同一参与者并发串行化      │
│  ② on conflict 幂等键         → 重复回传静默跳过          │
│  ③ dedupe_key 唯一索引        → 跨参与者全局去重          │
│  ④ UPDATE progress 原子行更新 → 任务进度/fulfilled 不重算  │
└──────────────┬──────────────────────────────────────────┘
               │ Management API（只读轮询）
┌──────────────▼──────────────────────────────────────────┐
│ 监听端（PM 侧监控）                                       │
│  flock 进程锁 + 原子替换快照  → 多监听实例不错乱/不覆盖    │
└─────────────────────────────────────────────────────────┘
```

## 二、服务端：多参与者并发回传的安全机制（已加固，无需改）

`crowd_submit_proof`（cloud/sql/crowd_submit_proof_live_v2.sql + 红队加固 SQL）：

| 并发场景 | 防护机制 | 效果 |
|---|---|---|
| 同一参与者同时发多个回传 | `select ... from crowd_participants ... for update`（函数开头行锁） | 第二个请求阻塞至第一个提交，同参与者串行 |
| 不同参与者同时回传 | 无共享锁（各自独立参与者行、独立 quota） | 天然并行，互不阻塞 |
| 重复回传（网络重试/插件重入） | `on conflict (participant_id, task_id, proof_seq, note_id) do nothing` | 幂等，重复静默跳过 |
| 两参与者提交同一笔记标题（刷量） | `idx_crowd_proofs_dedupe_title` 唯一索引 on dedupe_key（归一化标题） | 第二个 unique_violation → duplicate_skipped |
| 多参与者同时往同一任务回传（进度竞争） | `UPDATE crowd_tasks SET progress = progress + v_accepted`（原子行更新）+ 循环内复查 `status='open'` | 进度不重复累加，fulfilled 判定基于最新已提交值 |
| 任务已 fulfilled 后还有回传涌入 | 循环内 `v_task_fulfilled` 复查 → `item_task_fulfilled` 拒收 | 超发被拦截 |

**结论**：服务端已正确处理"多线并发 + 回流"，RPC 返回 `{ok, accepted, rejected, new_progress}` 是每个回传的**服务端权威确认**，插件端据此判定回流是否真实落地。

## 三、插件端：防重入互斥（v3.1 新增）

**缺陷**：`doCollectOnce` 无互斥。service worker 单线程，但 alarm 每 3 分钟触发一次；若某次采集/回传因网络慢超过 3 分钟，下一个 alarm 会**重入** → 重复采集 push 队列、重复调用 RPC、本地状态错乱。

**修复**（background.js）：
```js
let _running = false;
async function doCollectOnce() {
  if (_running) return { status: "busy" }; // 防重入
  _running = true;
  try { return await _collectOnceInner(); }
  finally { _running = false; }            // 无论成败都释放
}
```

**回传为什么保持串行**：服务端对同一参与者已用行锁串行化；插件端并发 RPC 只会变成数据库锁等待，无吞吐收益。因此串行 for 循环是正确设计（跨参与者的"多线"由服务端并行承载）。

## 四、监听端：并发监听不错乱（v3.1 新增）

**缺陷**：`crowd_smoke_monitor.py` 共享快照文件 `.data/crowd_smoke_last.json`，后台监听实例 + 手动实例并发跑时互相覆盖 → diff 错乱（误报/漏报）。

**修复**（flock 进程锁 + 原子替换）：
- `SnapshotLock.acquire()`：非阻塞 flock；拿到锁的实例写快照，未拿到的实例只读快照计算自己的 diff
- `write_snapshot()`：先写 `.tmp` 再 `os.replace()` 原子替换，杜绝半写文件

```bash
# 两个实例并发监听也不会互相覆盖
python3 cloud/crowd_smoke_monitor.py --loop 120   # 后台
python3 cloud/crowd_smoke_monitor.py --json       # 手动查（只读快照）
```

## 五、回流判定的并发语义

- **回流真实落地** = RPC 返回 `ok=true` 且 `accepted≥0`、`new_progress` 存在（服务端权威确认），且 DB 中 `crowd_proofs` 新增行 / `crowd_tasks.progress` 增长可被监听器观测到。
- **连续零有效**（accepted=0 ≥ 3 次）→ 插件 popup 红色告警；这是"服务端确实接收但全部去重/拒收"的正常信号（例如提交了别人已采过的笔记），不是虚假通过。
- **多线并发下监听不漏报**：监听器每次快照是全量聚合（proofs 总数/accept/reject、tasks progress 合计、参与者有效合计）+ 最近 5 条回传明细，任何一条新回传都会体现为快照变化。

## 六、验证

- 服务端并发安全：红队 10 类攻击回归全绿（含并发配额竞态 R9）
- 插件端互斥：node --check 语法 + 逻辑审查（busy 分支/finally 释放）
- 监听端 flock：多实例并发实测（后台 + 手动 --json 同时跑，无覆盖）
