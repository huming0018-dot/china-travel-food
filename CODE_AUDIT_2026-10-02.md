# 代码库审计报告 · 上海美食图鉴

审计范围：cloud/ 目录 120个Python文件，26,356行代码
审计时间：2026-10-02

---

## P0 · 必须立即修复（正在影响用户）

### 1. 原始JSON泄漏到TG（4处）
用户收到的不是人类可读信息，而是 `{"apply":true,"stores_to_patch":3,...}` 这种调试输出。

| 文件 | 行号 | 问题 |
|---|---|---|
| `gate_apply.py` | 588 | `core.notify.info("gate_apply 已写库：" + json.dumps(report))` |
| `gate_apply.py` | 591 | `core.notify.info("gate_apply dry：" + json.dumps(report))` |
| `curate_gate.py` | 185 | `core.notify.info("curate_gate 已写库：" + json.dumps(report))` |
| `probe_parallel.py` | 236 | `core.notify.info("probe_parallel：" + json.dumps(summary))` |

**修复方式**：改成人类可读摘要，例如：
```python
core.notify.info(f"门控写库：{n_patch}店{n_field}字段已PATCH，{n_reverify}店待复核")
```

---

### 2. Apify API重复调用（浪费请求 + 计费延迟）
`review_apify_fill.py` 里 `remaining_credit()` 和 `used_cost()` 各自独立调用 `https://api.apify.com/v2/users/me/usage/monthly`，同一次运行可能调3次以上。

**修复方式**：缓存一次API结果，函数内共享。

---

### 3. cron任务过多导致OOM（22+个定时任务）
当前crontab有22+个任务，每小时跑多个Python进程。2GB内存服务器上同时跑5-8个进程就OOM了，sshd被kill。

**修复方式**：
- 合并同类任务（amap/phone/coord/hours合并成一个batch脚本）
- 降低频率（很多任务不需要每小时跑）
- 用flock防重叠（已有，但任务基数太多）

---

## P1 · 应该修复（代码质量差，容易出bug）

### 4. 模块路径混乱
- 126个文件 `import common`
- 19个文件 `import common_core`
- 实际只有 `common_core.py` 在cloud/目录，`common.py` 在 `/app/pipeline/` 目录
- 每个文件开头都手动 `sys.path.insert(0, ...)`，共**190处**

**问题**：路径不一致，import失败时很难排查。

**修复方式**：统一用一个bootstrap文件，或者把common.py移到cloud/目录。

---

### 5. 静默吞错（266处 `except: pass`）
大量异常被静默吃掉，出了问题不知道为什么。

典型问题：
```python
try:
    ...
except:
    pass  # 错误被吃了，不知道发生了什么
```

**修复方式**：至少加日志 `except Exception as e: print(f"[WARN] ...: {e}")`

---

### 6. print代替logging（1460处）
所有输出都是print，没有日志级别区分。cron任务的输出重定向到.log文件，但无法grep错误级别。

**修复方式**：引入logging模块，至少区分INFO/WARN/ERROR。

---

### 7. 硬编码sleep（152处）
到处 `time.sleep(2)` 之类的硬编码等待。有些是必要的（API限流），有些是等浏览器加载的玄学等待。

---

## P2 · 可以优化（不紧急）

### 8. 路径重复定义
163处引用 `/app/data` 或 `FOOD_DATA_DIR`。每个文件都自己定义DATA路径。

### 9. notifier参数不统一
有的用 `cadence=3600`，有的用 `cooldown=86400*7`，有的用 `ACTION_NUDGE`。没有统一的常量定义。

### 10. 死代码/归档文件
`_archive/` 目录下有大量旧版本文件，容易误import。

---

## 修复优先级建议

| 优先级 | 修复项 | 预计工作量 |
|---|---|---|
| 立即 | P0-1: 4处JSON泄漏改成人类可读 | 30分钟 |
| 立即 | P0-3: 合并cron任务，降低频率 | 1小时 |
| 本周 | P0-2: Apify API缓存 | 20分钟 |
| 本周 | P1-5: except: pass加日志 | 2小时 |
| 下周 | P1-4: 统一模块路径 | 1小时 |
| 下周 | P1-6: 引入logging | 3小时 |
