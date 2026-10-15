"""M0 存储层（PRD §5.1）。

四层：RAW（不可变原始）→ ODS（标准化）→ DW（评分结果）→ APP（审计/交付视图）。
- 项目表前缀：sh_ / nj_（按项目 manifest.storage.table_prefix）。
- 血缘：ODS parent 必须 RAW；DW parent 必须 ODS(version>=1+hash)。
- Phase 0：分层常量 + 契约引用；SQLite/PostgreSQL 读写层 Phase 2a 实现。
"""

from __future__ import annotations

# 四层标识（与 schemas/*.schema.json 的 layer enum 保持一致）
RAW = "RAW"
ODS = "ODS"
DW = "DW"
APP = "APP"
LAYERS = (RAW, ODS, DW, APP)
