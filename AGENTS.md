# AGENTS.md — 本仓库的编码代理约束

> 面向在本仓库工作的 AI 编码代理（Codex / Cursor / Claude Code / 豆包等）。人类读者以 `MODULES-NAV.md` 与 `PRD-ROADMAP.md` 为准。

## 项目是什么

CTFS 模块化数据中台：一套领域无关的数据工具箱（M0–M7 八个独立工具模块）+ 项目声明（Manifest）+ 本体包（领域知识）。规格源 = `CTFS模块化数据中台PRD v2.1`。跨项目复用是唯一硬验收：新建项目只复制 Manifest、装本体包，工具零改动。

## 硬约束（违反即拒绝合并）

1. **一次只做一个任务**。从 `PRD-ROADMAP.md` 队首取任务；不得顺手做相邻模块的工作。完成即更新 `MODULES-NAV.md` 状态。
2. **模块独立性**：模块不得 import 其他模块实现；共享走 `storage`/`schemas` 契约。依赖只允许 项目→工具。
3. **业务词红线**：`toolbox/toolbox/` 与 `packs/` 代码内 grep 不得出现"菜系/商圈/人均"等业务词；领域知识只存在于 Manifest + Ontology Pack。
4. **契约先行**：改数据形状先改 `toolbox/schemas/*.json`；以 SDK 实测 shape 为准（如 `record_id` 非 `id`、exact_ref 键为 `hash`、OCR 在 `content.ocr_artifact.results` 嵌套）。
5. **确定性**：清洗/评分/审计必须确定性、可复算、幂等；禁止 caller 传 score/pass；时间戳 RFC3339 UTC。
6. **真实可溯宁空不假**：无来源不编造；unknown 就标 unknown；captured/import 时间不等于 pub time；源作者陈述不等于 Owner 实际体验。
7. **密钥零硬编码**：一律走 gitignored `deploy.env`；代码中不得出现任何凭据。
8. **不发明模块**：M8/M9 不存在；新模块必须先进 PRD 修订。
9. **旧资产冻结**：`ctfs-toolbox/`（0.5.x）、`cloud/`、`app/` 为冻结资产，只读参照，不追加新脚本；新代码一律进 `toolbox/`。

## 工作流（每个任务）

1. 读 `PRD-ROADMAP.md` 当前任务 → 读 `MODULES-NAV.md` 对应模块规格与 PRD 对应章节。
2. 最小实现（Ponytail full 默认）：先问"需要存在吗/仓库已有吗/标准库够吗"。
3. 每个非平凡逻辑留一个可运行检查（`assert` 自检或 `tests/test_*.py`，不引框架除非已有）。
4. 交付 = 实际源码 + 相对路径 diff + 文件 SHA + 实际测试日志；不重跑旧链、不补造日志。
5. 独立审查通过（或按项目规定）后才允许合入；未审查不宣称完成。

## 命令

- 冒烟：`cd toolbox && python3 -m unittest discover -s tests -v`
- CLI 冒烟：`python3 -m toolbox.cli schema list` / `toolbox init --help`（见 `toolbox/README.md`）

## 安全

- 禁止：rm 删除共享数据/缓存；执行地图/phone_fill/地理 API 脚本；访问其他任务目录与凭据；公开上传 RAW/OCR/数据库/凭据。
- 推送：任何 push 前确认分支与范围；Phase 0 骨架与导航类文档可在授权分支推送，数据类产物一律不进仓库。
