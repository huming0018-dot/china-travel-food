# 全量代码审计报告 · 2026-09-28

> 审计范围：cloud/ 全部 Python 模块（40+ 文件）、cloud/vendor/pipeline/ 底层管道、部署脚本、前端核心模块
> 审计人：质量监管官
> 审计方式：逐文件代码审查 + 共性模式扫描 + 跨文件关联性分析

---

## 一、审计覆盖

| 模块 | 文件数 | 已审 | 状态 |
|---|---|---|---|
| 采集核心 | xhs_api, cloud_discover, run_batch, cloud_bili_collect, cloud_michelin_collect, cloud_dianping_phone | 6 | ✅ |
| 调度编排 | cloud_router, gap_pool, gap_runner | 3 | ✅ |
| 监控告警 | health, watchdog, notifier, account_repair, warning_handler, map_key_repair, map_quota | 7 | ✅ |
| 数据补齐 | cloud_phone_fill, cloud_coord_fill, cloud_hours_fill, cloud_review_fill, cloud_amap_fill | 5 | ✅ |
| 工具支撑 | xhs_cookie_pool, xhs_qr_login, cloud_bu, cloud_ready, candidate_apply, unmatched_bridge, patrol_classify, cloud_patrol, map_helpers, reap_claims, progress_broadcast, work_progress, self_evolve | 13 | ✅ |
| 底层管道 | common, admission_gate, discovery_engine, discovery_keywords | 4 | ✅ |
| 部署 | Dockerfile, build_on_server.sh, docker-compose.yml, crontab.txt, entrypoint.sh | 5 | ✅ |
| 前端 | supabase.ts, auth.tsx, 页面结构 | 核心 | ✅ |

---

## 二、问题总览

| 严重度 | 数量 | 已修复 | 待修复 |
|---|---|---|---|
| P0（立即修复） | 4 | 4 | 0 |
| P1（高优先级） | 7 | 0 | 7 |
| P2（中优先级） | 7 | 0 | 7 |
| **合计** | **18** | **4** | **14** |

---

## 三、P0 问题（已修复）

### P0-1 采集空转 / 假饱和
- **位置**：`discovery_engine.py:321-350`, `gap_runner.py`
- **问题**：搜索被限流返回空 → frontier 无新店名补充 → 耗尽 → 误判 `saturated` → 自动入库残缺数据
- **修复**：新增 `empty_streak` 计数，连续 3 次返回 0 篇 → `status="stalled"`，立即停止；gap_runner 遇到 stalled 不自动 gate+apply，告警+冷却
- **验证**：语法检查通过

### P0-2 搜索限流与真无结果无法区分
- **位置**：`xhs_api.py:178-198`
- **问题**：`search()` 重试 3 次后返回空列表，调用方无法判断是限流还是真无结果
- **修复**：新增 `search_throttled` / `consecutive_empty` 属性，限流空时标记为 True
- **验证**：语法检查通过

### P0-3 部署脚本硬编码文件列表
- **位置**：`Dockerfile:24`, `build_on_server.sh:36-40`
- **问题**：COPY 和 tar 打包列表是硬编码的，`xhs_api.py`, `gap_runner.py`, `gap_pool.py`, `account_repair.py`, `notifier.py`, `warning_handler.py`, `map_quota.py` 等大量新文件**根本不会被部署到服务器**
- **影响**：服务器跑的是旧代码，本地修复无法生效——这可能是"代码总有很多坑"的重要原因之一
- **修复**：改为 `COPY *.py` 和 `tar ... *.py` 通配符
- **验证**：语法检查通过

### P0-4 cloud_discover 不识别 stalled 状态
- **位置**：`cloud_discover.py:140`
- **问题**：只判断 `rep["status"] != "saturated"`，新增的 stalled 状态会被当作"进行中"，不告警不暂停
- **修复**：增加 stalled 分支，打印告警并通过 notifier/health 推送
- **验证**：语法检查通过

---

## 四、P1 问题（待修复）

### P1-1 run_batch.py：采集到 0 条笔记也算成功
- **位置**：`run_batch.py:117-122`
- **问题**：`X.collect_restaurant()` 返回 0 条笔记时，`rec` 仍被写入，`added += 1`。"采集了 0 条"被算作"成功采集了 1 家"
- **影响**：产出统计虚高，无法区分"真的采到了"和"空跑了"
- **建议**：0 条笔记时标记为 `empty`，不计入 added，单独统计

### P1-2 candidate_apply.py：直接检查单个 AMAP_KEY
- **位置**：`candidate_apply.py:150`
- **问题**：`if not AF.AMAP_KEY` 直接检查环境变量单个 key，但地图 key 已由 `map_quota` 池管理（`AMAP_KEYS`），单 key 检查可能误判为"未配置"
- **影响**：坐标补齐可能被错误跳过

### P1-3 cloud_phone_fill.py：直接检查单个 key
- **位置**：`cloud_phone_fill.py:91-92`
- **问题**：`has_tencent = bool(os.environ.get("TENCENT_MAP_KEY"))` 同样检查单 key，与 map_quota 池不同步

### P1-4 cloud_coord_fill.py：直接检查单个 key
- **位置**：`cloud_coord_fill.py:34-35`
- **问题**：同上

### P1-5 cloud_review_fill.py：不走 map_quota 池
- **位置**：`cloud_review_fill.py:49,66-82`
- **问题**：直接用单个 `AMAP_KEY` 调用高德 API，不走 `map_quota` 配额仲裁，与 `cloud_amap_fill` 共享月配额但无协调
- **影响**：两个脚本可能同时吃光高德月配额，互相不知道
- **建议**：接入 map_quota.acquire() 仲裁

### P1-6 account_a / account_b 实为同一账号
- **位置**：cookie 文件 + `account_identities.json`
- **问题**：两个 cookie 的 web_session 身份段相同（均以 `040069b80633608cd2f1` 开头），同账号多设备互顶
- **影响**：并行采集池设计失效，两个 worker 互相干扰
- **状态**：account_b 明天用另一个账号重登

### P1-7 本地代码大量未提交
- **位置**：项目根目录
- **问题**：git status 显示 8 个修改文件 + 15+ 个新文件未 commit，包括核心模块
- **影响**：本地与部署版本不同步，无法追溯变更

---

## 五、P2 问题（待修复）

### P2-1 cloud_discover.py：subprocess check=True 无异常处理
- **位置**：`cloud_discover.py:78-84`
- **问题**：`run_gate` / `run_apply` 用 `check=True`，失败会抛异常崩溃整个脚本，无 try/except 兜底

### P2-2 run_batch.py：subprocess check=True 无异常处理
- **位置**：`run_batch.py:128-132`
- **问题**：转换/入库失败会崩溃，已采集数据可能未处理

### P2-3 无采集产出端到端统计
- **问题**：采集任务跑完后只有脚本级日志，没有"本次新入库 N 条"的统一报告
- **建议**：在 progress_broadcast 中增加各采集任务的产出统计

### P2-4 common.py：DEFAULT_APP 硬编码本地路径
- **位置**：`common.py:26-29`
- **问题**：`DEFAULT_APP` 硬编码了 `/Users/hubowen/Desktop/...`，容器中靠环境变量回退，但如果环境变量没设会尝试读不存在的路径
- **建议**：容器中应优先用环境变量，本地路径仅作 fallback

### P2-5 self_evolve.py：notifier.info cadence=0
- **位置**：`self_evolve.py:142`
- **问题**：`cadence=0` 意味着每次都推，虽然每天只跑一次影响不大，但不符合 notifier 的节流设计

### P2-6 progress_broadcast.py：绕过 notifier 直接调私有方法
- **位置**：`progress_broadcast.py:12`
- **问题**：直接调用 `health._telegram` / `health._feishu_app` 等私有方法，绕过 notifier 的分级/去重/冷却
- **影响**：每 10 分钟强制推送一次，可能造成打扰

### P2-7 cloud_hours_fill.py：配额管理不一致
- **位置**：`cloud_hours_fill.py`
- **问题**：调用 `map_helpers` 的函数，但 map_helpers 内部是否走 map_quota 池需要确认；如果不走，与其他补齐脚本共享配额无仲裁

---

## 六、跨模块关联性发现

### 发现 1：地图 key 管理存在"两套体系"
- `map_quota.py` 建立了统一 key 池 + 配额仲裁 + POI 缓存
- 但 `cloud_review_fill.py`、`candidate_apply.py`、`cloud_phone_fill.py`、`cloud_coord_fill.py` 仍直接读单个 `AMAP_KEY` / `TENCENT_MAP_KEY`
- **结论**：map_quota 池没有被全量接入，配额管理是碎片化的

### 发现 2：部署与开发不同步是系统性风险
- Dockerfile 和 build_on_server.sh 的硬编码列表意味着：**任何不在列表里的新文件都不会被部署**
- 这解释了为什么"代码总有很多坑"——可能本地修了但服务器没更新
- 已修复为通配符，但需要确认服务器上的当前版本

### 发现 3："虚假通过"有多个入口
- 采集空转 → 假饱和（已修复）
- run_batch 0 条也算成功（P1-1）
- 账号探测用 user/me 但搜索可能被限流（account_repair.probe 只查 user/me）
- **结论**：需要在所有采集入口加"产出真实性校验"

---

## 七、修复优先级建议

### 立即（本轮已完成）
- [x] P0-1 ~ P0-4 全部修复

### 下一轮（建议尽快）
- [ ] P1-1 run_batch 0 条不算成功（影响产出统计真实性）
- [ ] P1-5 cloud_review_fill 接入 map_quota 池（防止配额争抢）
- [ ] P1-2 ~ P1-4 统一地图 key 检查方式
- [ ] P1-7 git commit 所有修改

### 后续
- [ ] P2 全部问题
- [ ] account_b 重登（明天）
- [ ] 部署验证：确认服务器代码已更新

---

## 八、部署验证清单

修复部署后，需验证：
1. [ ] 服务器上 `xhs_api.py` 包含 `search_throttled` 属性
2. [ ] 服务器上 `discovery_engine.py` 包含 `EMPTY_STALL_LIMIT`
3. [ ] 服务器上 `gap_runner.py` 包含 stalled 处理
4. [ ] 服务器上 `cloud_discover.py` 包含 stalled 分支
5. [ ] 采集日志中出现"空转检测"字样时，确实停止了该叶子而非继续跑到 saturated
6. [ ] notifier 能收到 stalled 告警
