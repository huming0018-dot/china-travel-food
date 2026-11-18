# 历史研究材料

本目录保存美食项目的历史调查、候选和处理结果，不是当前运行入口或跨项目工具。

已退出根层 5 个旧批处理：`_apply_omakase_soba.py`（固定餐厅/菜系 ID 修复）、`_apply_summaries.py`（25 段按行序回填）、`_resolve_conflicts.py`（整批 conflict 改 new）、`merge_enrich.py`（旧补强合并及指定分店拆分）、`merge_reevidence.py`（2026-09-23 旧评分/证据裁决）。后两者有实际项目逻辑，但依赖旧批次输入和个人路径，不作为现行流程继续维护。

保留 `_plan.json`、`_plan_final.json`、`_25brief.md`、`authority/omakase_attach_list.json` 及其余既有数据/报告，供追溯旧决策；不代表当前事实，不可直接重放。`_mine25.jsonl`、`accepted_fanout.jsonl`、`enrich/raw_*_enrich.jsonl`、`reevidence/raw_*_reev.jsonl` 在本次基线不存在。固定修复/摘要常量仅留 Git 历史，不另复制为数据资产。

源码恢复点：`419f9bddede5c8ce232ba87d126c45cf0599eac1`。本次仅退出历史入口，未修改生产或重新验证餐厅信息。

覆盖历史批次：退出 `coverage/_gen_authority_rows.py` 与 `coverage/batch8/_b8_upsert.py`、`_b8_verify.py`。前者 34 行静态名单与既有 `registry_rows_authority.jsonl` 完全一致；后两者仅重放/检查 2026-09-30 固定 3 店和 ID。名单、候选、覆盖报告和账本保留为历史资料，不代表当前覆盖率、来源许可或已验证采集能力。恢复点：`9a175118a4d6d72dabb2ec92ab5ac5c9d668cef8`。
