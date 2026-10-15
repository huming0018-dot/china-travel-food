"""四层数据契约（PRD §5.1/§6.3）：Schema 加载与校验。

层：RAW（M1 写 / M2 读）→ ODS（M2 写 / M3 读）→ DW（M3 写 / M6·M7 读）→ APP（审计/交付视图）。

契约约束（沿用 SDK 实测 shape）：
- 所有层 record_id 字段名是 record_id（非 id）。
- ODS parent_ref.layer 必须 RAW；DW parent_ref.layer 必须 ODS 且 int version>=1 + hash 匹配。
- 时间戳 RFC3339 UTC。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_NAMES = ("raw", "clean", "scored", "audit", "manifest", "pack")

# 血缘约束：目标层 → 允许的 parent 层
PARENT_RULES = {"clean": "RAW", "scored": "ODS"}


class SchemaError(ValueError):
    """契约加载/校验错误。"""


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """按名称加载 JSON Schema（raw/clean/scored/audit/manifest）。"""
    if name not in SCHEMA_NAMES:
        raise SchemaError(f"未知契约: {name!r}（可选 {SCHEMA_NAMES}）")
    path = SCHEMA_DIR / f"{name}.schema.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - 环境相关
        raise SchemaError(f"契约加载失败 {path}: {exc}") from exc


def validate_data(name: str, data: dict[str, Any]) -> list[str]:
    """校验某层数据，返回错误消息列表（空 = 通过）。"""
    validator = Draft202012Validator(load_schema(name))
    return [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(data)]


def check_lineage(name: str, data: dict[str, Any]) -> list[str]:
    """血缘约束：clean 的 parent 必须 RAW；scored 的 parent 必须 ODS(version>=1+hash)。

    仅对含 parent_ref 的记录校验；缺失 parent_ref 不在此报错（由 schema required 管）。
    """
    errors: list[str] = []
    parent = data.get("parent_ref")
    if name not in PARENT_RULES or not isinstance(parent, dict):
        return errors
    want = PARENT_RULES[name]
    if parent.get("layer") != want:
        errors.append(
            f"parent_ref.layer 必须 {want}，实际 {parent.get('layer')!r}"
        )
    if name == "scored":
        version = parent.get("version")
        if not isinstance(version, int) or version < 1:
            errors.append(f"scored parent version 必须 int>=1，实际 {version!r}")
        if not parent.get("hash"):
            errors.append("scored parent 必须携带 hash")
    return errors


def validate_all(names: Iterable[str], data: dict[str, Any]) -> dict[str, list[str]]:
    """批量校验，返回 {层名: 错误列表}。"""
    return {n: validate_data(n, data) for n in names}
