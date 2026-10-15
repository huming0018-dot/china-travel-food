# PRD-ROADMAP.md — 按模块的任务队列（一次一个任务）

> 队首即当前任务。每完成一个任务：更新状态 → 更新 `MODULES-NAV.md` → 再取下一个。
> 状态：⬜ 未开始 / 🟡 进行中 / 🔒 卡外部 / ✅ 完成。

## 任务队列

| # | 模块 | 任务 | 状态 | 备注 |
|---|---|---|---|---|
| 1 | — | **Phase 0：toolbox 包骨架 + 四层契约 + Manifest 规范 + CLI 脚手架 + 导航地图**（本分支） | ✅ 完成 | commit e5acb0b + 本 commit；仓库结构见 `MODULES-NAV.md` §三 |
| 2 | M4 | Phase 0b：`packs/food-cn-v2` 本体包骨架（taxonomy/词根/评分/回归集/源矩阵/schema 六件套）+ ontology verify/install/ledger | ✅ 完成 | 本体包允许业务词；toolbox 代码业务词零命中（v2.2 §5 CI 红线） |
| 3 | M1 | Phase 1a：crawler 连接器插件化骨架（entry_points 注册 + 源注册表 schema） | ⬜ | |
| 4 | M2 | Phase 1b：cleaner 骨架 + 迁入已验证 `entity_align.py`（契约对齐 clean.schema） | ⬜ | 已验证件：ctfs-m2-entity-align/ |
| 5 | M3 | Phase 1c：scorer 骨架 + 迁入已验证 scorer/ods_evidence/normalize_ocr（契约对齐 scored.schema） | ⬜ | 已验证件：ROOT04R1 + M3-B4-NORMALIZED-01 |
| 6 | M0 | Phase 2a：storage 四层读写层（SQLite 起步，PostgreSQL 后置）+ lineage | ⬜ | |
| 7 | M6 | Phase 2b：auditor 只读体检/覆盖/回归/发布闸门骨架 | ⬜ | |
| 8 | M7 | Phase 2c：deliverer 只读回环 HTTP + 前端/飞书消费骨架 | ⬜ | m7-pg-readonly 已验证修复可继承 |
| 9 | M5 | Phase 3：orchestrator DAG/断点续跑/cron 骨架 | ⬜ | |
| 10 | — | **硬验收**：新建 nj-food 项目 = 复制 Manifest 改 city + 装 food-cn 本体包，工具零改动跑通全链路 | ⬜ | PRD §6.4/§10.1 |

## 验收口径（每个任务通用）

- 交付 = 实际源码 + 相对路径 diff + 文件 full SHA + 实际测试日志；合成测试明确标 SYNTHETIC。
- 业务词 grep 校验通过；密钥零硬编码；audit gate fail 禁入交付层。
- 未独立审查不宣称完成；M8/M9 不发明。
