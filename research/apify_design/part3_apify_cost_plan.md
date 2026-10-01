# Apify 耗速深度调研与省钱方案（PM #44 交付）

> 调研执行：2026-10-02（PM窗口）
> 数据来源：① Apify Console 真实账单（billing/current-period + historical-usage，浏览器实测）；② `cloud/review_apify_fill.py` 代码逐行审计；③ `cloud/apify_fill_controller.sh` 控制器审计；④ `research/apify_design/part2_apify_actors.md` 市场调研。

---

## 一、铁证：账单实况（10月周期第2天）

| 指标 | 数值 |
|---|---|
| 平台用量（当前计费周期） | **$39.95 / 上限 $40（99.9% 已烧）** |
| 周期 | 2026-10-01 ~ 10-31（刚过2天） |
| 预付额度消耗 | $19.00（Starter 预付，已清零） |
| 超额开票 | **$20.95（已走信用卡）** |
| 服务构成 | **Actors $39.93（99.9%）**，其余 $0.02 |

### 按 actor 拆分（historical usage，10月原始用量）

| Actor | 消耗 | 占比 | 代码内标价 |
|---|---|---|---|
| **opspilot.cc/xiaohongshu-keyword-search-scraper** | **$34.10** | 85% | **$0.00/run（误标）** |
| toolzerhub/rednote-xiaohongshu-search-scraper | $3.43 | 9% | $0.10/run |
| sian.agency/xiaohongshu-rednote-scraper | $2.40 | 6% | — |

**一句话结论：烧钱主凶是 opspilot——市场调研明确它按「启动次数计费（$0.10/次启动 + 内存×时长平台费）」收取真实费用，但 review_apify_fill.py 把它标成 0.0 美元，导致内部成本闸完全失效、控制器无感无限循环调用。**

---

## 二、根因链（三层）

### 1. 成本记账错误（最致命）
- `review_apify_fill.py` PROVIDERS 表：`opspilot: {"price_per_run": 0.0}`、`zenstudio: 0.0`
- **part2 调研（2026-10-01，已精读 apify.com 页面）：opspilot 是 $0.10/actor start（按启动计费，非按结果）**
- 后果：内部累计 `billable_cost_usd` 永远 ≈ 0 → `FREE_COST_CAP=0.50` 永不触发 → **烧钱的不是免费 actor，是被误标成免费的付费 actor**
- 真实单 run 平台费 ≈ $0.20（$34.10 ÷ 约170次 run），与"启动费+内存×时长"口径吻合

### 2. 常驻死循环（机械驱动）
- `apify_fill_controller.sh`：`while true` 无限循环
  - 每轮 `--limit 30`（处理30家店）→ 一轮最多烧到 ROUND_CAP=$2.0 → sleep 30秒 → 下一轮
  - **一天可跑数百轮**，即使每轮$2，日消耗可达数十美元
- 唯一的停闸：`remaining_credit < FLOOR=0.25` → 但记账错了，账单 API 的剩余值在额度归零前一直"看起来够"
- 结果：$40 限额 2 天烧穿，且超额 $20.95 已真实扣卡

### 3. 每 run 产出太低（效率浪费）
- `max_items=6`：每次 run 只取 6 条 → 采信率低 → 达标需要更多 run → 启动费摊薄不掉
- opspilot 单次固定返回~20条但相关度参差 → 更多"无效 run 仍在计费"
- 目标排序里 DEFER 冷门店，但缺证据店仍有数百家 → 控制器"永不完工、持续烧钱"

---

## 三、省钱方案（按优先级，立即执行）

### 🔴 P0：立即止血（今天，10-02）
1. **停掉常驻死循环**：服务器 `systemctl stop food-apify-fill`（或 kill 对应 while 循环进程）
2. **下调平台限额**：Apify Console → Limits，$40 → $20（已超额部分按现状结算，防止继续超）
3. **修正记账**：`review_apify_fill.py` PROVIDERS 价格表改真实值——
   - opspilot: 0.10（按启动计费）
   - zenstudio: 0.005/条（$4.99/1k 换算）
   - toolzerhub: 0.10、atomus: 0.17（已有）
   - 或直接改为"每次 run 后从账单 API 拉真实增量"（更准）

### 🟡 P1：换 actor 策略（成本结构重排）
| 方案 | 说明 | 预计成本 |
|---|---|---|
| **A. sian.agency 为主**（当前 apify_collect.py 默认） | 启动 $0.014 + 搜索 $0.004/条；用户量最大(646)、最活跃；错误行不计费 | 搜索30条≈$0.13/店，远低于 opspilot |
| **B. atomus 为主** | 免cookie全模式、$0.02/条、失败查询免费；评论$0.01/条 | 搜索20条≈$0.40/店 |
| **C. 混合**：sian 搜索 + atomus 补评论 | 成本与覆盖平衡 | 综合最优 |

**放弃 opspilot**（按启动计费的劣质 actor，虽有 $0.10 低价但"每 run 固定成本+低采信"双重浪费）；**toolzerhub 也移出默认**（质量差且贵）。

### 🟢 P2：调度机制改造（一次改对，长期省钱）
1. **常驻循环 → cron 定点**：每天固定 2~3 轮（如 07:00 / 13:00 / 21:00），每轮 `--limit 12`、ROUND_CAP=$1.0
2. **成本闸改为账单 API 真值**：每轮结束读 `/users/me/usage/monthly` 真实增量，超日预算即停到次日
3. **提高单 run 产出**：`max_items` 6 → 20~30（摊薄启动费）；对 sian/atomus 按条计费，多取不贵
4. **按"缺证据店数"动态调度**：目标店数降到 0 自动停服务（已有 TARG=0 逻辑，但需记账修正后才可信）
5. **日预算硬门**：新增 `DAILY_CAP_USD=2.0`（一天最多 $2），服务器端 watchdog 强制

### 🔵 P3：长期（纳入 #44 后续）
- **批量合并 run**：sian/atomus 支持多关键词或页游合并 → 一 run 多店，启动费摊薄到极限
- **免费额度利用**：Apify Starter 本身含免费 CU；sian 免费档 25 行/run（Console 跑）可做试探性采集不花钱
- **本地 LLM 舰队替代部分搜索**：方舟 key 注入后（#26），探针/判读本地化，减少对外部采集依赖

---

## 四、预期效果

| 项 | 现状 | 改造后 |
|---|---|---|
| 日消耗 | ~$20（失控） | ≤$2（硬门） |
| 单店搜索成本 | ~$0.20（opspilot启动费） | ~$0.13（sian按条） |
| 月消耗 | $40 上限+超额 | ≤$60 可控（或更少） |
| 采信质量 | 低（opspilot泛搜） | 高（sian/atomus精准） |

---

## 五、落地分工（PM 调度）

| 工单 | 责任 | 内容 |
|---|---|---|
| #44（crawler） | collector | 按本方案执行 P0 三项 + 确认服务器停循环 |
| #15 补充（dev） | dev | 修正 PROVIDERS 价格表 + 加 DAILY_CAP_USD + max_items 调优 |
| #1（crawler） | collector | 止血后按新 actor 重跑 #1 实跑验证 |

> 验收标准：24小时内 Apify 消耗 ≤$2；opspilot 不再被调用；账单 API 真实增量反映在每次调度日志。
