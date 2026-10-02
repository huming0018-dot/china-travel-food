# CODE_AUDIT_V3 — 激进精简方案（2026-10-02）

> 方法：Lean Code Refactor Step3 —— 算总账 + 识别过度工程 + 精简路线
> 范围决策：聚焦「众包回流体系」相关核心模块（用户点名），不摊大饼重写存量 81 个调用方

## 总账

| 范围 | 行数 | 处置 |
|---|---|---|
| cloud/*.py 全量 | 26685 | 非本轮目标（vendor 管线是历史资产，动它风险大收益小） |
| 众包回流相关核心 | notifier 222 + common_core 259 + crowd_* ~1100 | ✅ 本轮优化对象 |
| 新增 tracking 报告 | 0 → ~200 | ✅ 本轮实现 |

## 识别出的过度工程 / 精简点

### P0-1：双公共层并存（common_core 259 行 vs vendor/common 578 行）
- 现状：config/req/fetch_all/log/notify 两套实现，81 个文件 import vendor common，17 个 import common_core
- 判定：**不动存量**（兼容风险），新代码一律走 common_core —— tracking 已示范
- 动作：文档固化「新代码唯一底座 = common_core」约定，写入 DEV_STANDARD

### P0-2：tracking 报告功能（本轮新增，已按 Lean 原则写）
- 单文件 ~200 行，只依赖 common_core + notifier，无重复 HTTP/分页/脱敏
- 落盘 JSONL 可回溯 + notifier.info 心跳节流（cadence 3600 不刷屏）

### P1-1：硬编码路径治理
- 245 处 `/app/` 硬编码（vendor 外）——存量不动，但**新代码一律 `core.config("FOOD_DATA_DIR")`**
- tracking 已用环境变量

### P1-2：print vs 结构化日志
- 104 文件未接 notifier —— 存量不动，新代码用 `core.log`

## 精简原则（Ponytail 风格，本轮执行）

1. **YAGNI**：不为未来扩展写框架——tracking 只有 1 个文件、4 个函数
2. **一个模块一件事**：tracking 只做「聚合+渲染+落盘+推送」
3. **能函数不写类**：tracking 全部函数式
4. **硬编码 > 过度抽象**：不建 tracking 配置系统，直接常量 CADENCE
5. **统一底座**：新代码 import common_core as core，不重复造轮子

## 验收标准

- [x] tracking 报告：dry-run 输出正确（任务池/回流/参与者/配额）
- [x] 安全测试 T1-T7 全过（None/恶意输入/超长/除零/缺字段/落盘失败）
- [x] 复用 notifier（唯一通知出口）不重复造轮子
- [x] 复用 common_core（统一底座）不重复实现 HTTP/分页
- [ ] 提交 git + 服务器同步 + STATUS 更新
