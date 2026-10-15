# CTFS 模块化数据中台 · 模块导航地图

> 规格源：`CTFS模块化数据中台PRD v2.1`（§4 模块总览矩阵 / §5 M0–M7 规格定义 / §7 仓库结构 / §8 路线图）。
> 本文件是仓库内**唯一的模块导航**。模块 = 独立可调用工具；项目 = 只通过 Manifest + 本体包调用工具的产品。
> 开发纪律：**按 PRD 分模块单独开发，一次只做一个任务**。每完成一个任务更新本表状态后，才进入下一个。

## 一、心智模型

```
┌─────────────────────────────────────────────────────────────┐
│  projects/  （每个项目 = manifest.yaml + 引用的本体包）          │
│  ┌─────────────┐    ┌──────────────────────────────────┐     │
│  │ shanghai-food│   │  tools（M1–M7 八个独立工具模块）     │     │
│  │ nj-food      │──▶│  crawler cleaner scorer ontology  │     │
│  │ sh-housing   │   │  orchestrator auditor deliverer    │     │
│  └─────────────┘    └──────────────┬───────────────────┘     │
│                                    │ 依赖只允许 项目→工具      │
│                                    ▼                        │
│                            M0 storage 四层底座               │
│                            (RAW→ODS→DW→APP + lineage)       │
└─────────────────────────────────────────────────────────────┘
```

- **领域知识全部外置**：Manifest（项目声明）+ Ontology Pack（分类法/词根/评分规则/回归集）。工具代码内禁止出现"菜系/商圈/人均"等业务词（验收红线）。
- **跨项目复用是唯一硬验收**：新建南京美食 = 复制 Manifest 改 city + 装已有 food 本体包，工具零改动跑通全链路。

## 二、模块总览（M0–M7）

| 模块 | PRD 章节 | 代码位置 | 状态 | 当前任务 |
|---|---|---|---|---|
| **M0 存储层** | §5.1 | `toolbox/toolbox/storage/` + `toolbox/schemas/` | 🟡 Phase 0 骨架 | 四层契约（raw/clean/scored/audit）已立；SQLite/PostgreSQL 读写层待 Phase 2 |
| **M1 采集器** | §5.2 | `toolbox/toolbox/crawler/` | 🟡 Phase 0 骨架 | 连接器插件化（entry_points）+ 信源注册表 + 召回引擎，Phase 1 开发 |
| **M2 清洗器** | §5.3 | `toolbox/toolbox/cleaner/` | 🟡 Phase 0 骨架 | 实体解析/字段校验/去重；`entity_align.py` 已验证件待迁入 |
| **M3 评分器** | §5.4 | `toolbox/toolbox/scorer/` | 🟡 Phase 0 骨架 | 多维评分/污染检测/准入；scorer/ods_evidence/normalize_ocr 已验证件待迁入 |
| **M4 本体库** | §5.5 | `toolbox/toolbox/ontology/` + `packs/` | 🟡 Phase 0 骨架 | food-cn-v2 / housing-sh-v1 本体包骨架待建（含评分 rubric） |
| **M5 编排器** | §5.6 | `toolbox/toolbox/orchestrator/` | 🟡 Phase 0 骨架 | DAG 编排/断点续跑/定时（cron+CLI 起步，Prefect 后置） |
| **M6 审计器** | §5.7 | `toolbox/toolbox/auditor/` | 🟡 Phase 0 骨架 | 只读体检/覆盖审计/回归集/发布闸门 |
| **M7 交付器** | §5.8 | `toolbox/toolbox/deliverer/` | 🟡 Phase 0 骨架 | 只读回环 HTTP + 前端/飞书消费；m7-pg-readonly 已验证修复可继承 |

> **不存在 M8/M9**（PRD 只定义 M0–M7）。任何"新模块"必须先过 PRD 修订，禁止在代码里发明。

## 三、仓库结构（PRD §7）

```
仓库根（china-travel-food）
├── MODULES-NAV.md          ← 本导航地图（唯一权威）
├── AGENTS.md               ← 编码代理约束（一次一任务）
├── PRD-ROADMAP.md          ← 按模块的任务队列与状态
├── toolbox/                ← 独立 Python 包（pip install toolbox）【PRD Phase 0 新建】
│   ├── pyproject.toml
│   ├── toolbox/
│   │   ├── cli.py          ← 统一入口 `toolbox <module> <action> --project <name>`
│   │   ├── manifest.py     ← Manifest 加载与校验
│   │   ├── schema.py       ← 四层契约加载与校验
│   │   ├── crawler/        ← M1
│   │   ├── cleaner/        ← M2
│   │   ├── scorer/         ← M3
│   │   ├── ontology/       ← M4
│   │   ├── orchestrator/   ← M5
│   │   ├── auditor/        ← M6
│   │   ├── deliverer/      ← M7
│   │   └── storage/        ← M0
│   ├── schemas/            ← 数据契约（raw/clean/scored/audit/manifest JSON Schema）
│   ├── templates/          ← `toolbox init` 项目模板（manifest.yaml）
│   └── tests/
├── projects/               ← 各项目 manifest.yaml（Phase 1 起建立）
├── packs/                  ← 本体包（food-cn-v2 / housing-sh-v1，Phase 1 起建立）
├── ctfs-toolbox/           ← 【冻结资产】0.5.x 旧工具箱，只读参照，不在此追加新脚本
├── cloud/                  ← 【冻结资产】业务采集脚本（北星体系 legacy）
└── app/                    ← 【冻结资产】前端
```

## 四、模块规格速查（PRD §5 摘要）

- **M0 存储**：四层 RAW/ODS/DW/APP + lineage；项目表前缀 `sh_`/`nj_`；RAW 不可变；ODS parent 必须 RAW；DW parent 必须 ODS（int version≥1 + hash 匹配）。
- **M1 采集**：连接器插件化（entry_points 注册）；bounded snapshot-file / http-public 源；来源回执（source_kind/auth_level/covers/reliability）；请求预算。
- **M2 清洗**：raw→clean 确定性；实体解析（多信号三桶 AUTO/REVIEW/PHONE）；字段校验与事实主张（value+source_url+captured_at）；地址 GCJ02、电话规范。
- **M3 评分**：多维评分 + 软广污染 + 准入 gate；rubric 全部来自本体包；确定性、可解释；禁止 caller 传 score/pass。
- **M4 本体**：taxonomy/词根/评分规则/回归集/source_plan/schema 六件套，semver 版本化。
- **M5 编排**：DAG 依赖只允许 项目→工具；断点续跑；cron+CLI 起步。
- **M6 审计**：只读回环；覆盖/回归/证据/发布闸门；gate fail 禁入交付层。
- **M7 交付**：只读 HTTP + 前端/飞书；慢查询与空回退。

## 五、开发规则（硬约束）

1. **一次只做一个任务**：从 `PRD-ROADMAP.md` 队首取任务，完成（源码+diff+SHA+测试+独立审查）并更新本表后才取下个。
2. 模块 = 独立工具：任何模块不得 import 其他模块的实现细节；共享能力走 storage/schema 契约。
3. 业务词红线：grep 校验工具代码目录不得出现"菜系/商圈/人均"等业务词。
4. 密钥零硬编码：一律走 gitignored `deploy.env`。
5. 云上铁律（PRD §11）：开发/调度/采集/推送在 deuce 云电脑与腾讯云容器；本地 Mac 仅管理入口。
6. 契约先行：先落 `schemas/` 再写实现；真实 shape 以 SDK 实测为准，纸面 schema 不权威。
