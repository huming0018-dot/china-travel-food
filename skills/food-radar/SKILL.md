---
name: food-radar
description: 懂你口味的找店助手 + 餐饮新鲜事雷达。查新店/首店/联弹客座、按场景给短名单、维护想吃清单与反馈。
version: v3.2
---

# food-radar · 食客助手

**执行规程以 [PROPOSAL.md](PROPOSAL.md) 为依据**（路由、食客判断、输出格式、安全边界）。本文件只做入口索引与本机环境说明。

> 本目录为**待采纳候选**；审阅与沙盒验证以 PROPOSAL.md 为依据。该引用仅定义**文档优先级**，不代表已批准、安装或启用。

## 先读哪份

| 你要做的事 | 读 |
|---|---|
| 怎么判断、怎么输出、什么不做 | **[PROPOSAL.md](PROPOSAL.md)** |
| 记录格式、字段、过期与冲突 | [references/data-contract.md](references/data-contract.md) |
| 资深食客判断维度 | [references/diner-rubric.md](references/diner-rubric.md) |
| 命令怎么敲 | [references/operations.md](references/operations.md) |
| 校验铁律（含踩坑） | [references/validation.md](references/validation.md) |
| 本机工具与实测状态 | [references/environment.md](references/environment.md) |
| **餐厅/主厨/关系网百科卡** | **[references/knowledge-cards.md](references/knowledge-cards.md)** + [knowledge/](knowledge/) |
| **餐饮模式公式（推荐 + 爬虫信号）** | **[references/restaurant-patterns.md](references/restaurant-patterns.md)** |
| **关系图递归法（每次预约如何长图）** | **[references/knowledge-graph-method.md](references/knowledge-graph-method.md)** |
| **工商信息推演（股权→人员变动→开张关张）** | **[references/business-registry-method.md](references/business-registry-method.md)** |

## 三层结构

```
Skill 层      PROPOSAL.md                 意图识别、检索编排、输出形态
数据通路层    scripts/radar.py            记录引擎，纯标准库，零第三方依赖
              scripts/dianping_fetch.py   点评采集（可选增强）
              scripts/doctor.py           按需预检
记录层        radar.py 的 SQLite          餐厅/活动/收藏/反馈，按 surface+actor 隔离
```

**登录采集是可选增强，不阻断主流程。** 公开搜索可用就开工。

## 本机三条通路

```bash
bash scripts/preflight.sh --channel public     # 只查公开检索（默认，永远最简）
bash scripts/preflight.sh --channel dianping   # 点评：需 Playwright + chromium
bash scripts/preflight.sh --channel media      # 小红书/抖音：需 Node + MediaCrawler
```

按本次任务只查需要的通道。**缺一个可选工具不会让公开检索停工。**

## 三条不可妥协

1. **采集失败 ≠ 无餐厅 / 已闭店。** 统一返回 `channel_unverified`，并写明 `not proof of zero shops`。
2. **"正在营业 / 有位 / 不用排队"是三件事**，分别标注；查不到就写 `未确认`，不编。
3. **组合无解时直接说无解**，不硬凑平庸选项。

## 本机实测状态（2026-10-18）

| 通路 | 状态 |
|---|---|
| 公开搜索 | ✅ |
| 大众点评 | ✅ 实测可用（当霁 4.7/98评/¥388、ONCUE 4.8/375评/¥1064 均由此采出） |
| 抖音 | ✅ 需 Node（**JDK 无效**：Nashorn 已随 JDK 15+ 移除） |
| 小红书 | ⚠️ 登录态已过期，需重扫 |
| 定时订阅 | ❌ 未做。`changes` 只是增量日志，**不含调度器** |

细节与踩坑见 `references/environment.md`。
