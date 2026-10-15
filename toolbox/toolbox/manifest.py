"""Manifest 规范（PRD §6.1）：项目声明的加载与校验。

- project_id 正则：^[a-z0-9][a-z0-9-]{0,63}$（沿用 0.5.x 契约）。
- schemaVersion 分档：0.2.0 / 0.3.2 / 0.3.3 / 0.4.0（0.5.x 沿革保留）。
- 校验以 schemas/manifest.schema.json 为准（jsonschema）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SCHEMA_VERSIONS = ("0.2.0", "0.3.2", "0.3.3", "0.4.0")


class ManifestError(ValueError):
    """Manifest 不合法。"""


@dataclass(frozen=True)
class Manifest:
    """已校验的 Manifest。"""

    project_id: str
    raw: dict[str, Any]
    path: Path | None = field(default=None)


def load_manifest(path: str | Path) -> Manifest:
    """读取并校验 Manifest，返回不可变对象。

    Raises:
        ManifestError: 文件缺失 / YAML 解析失败 / 未通过 schema / project_id 非法。
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - 环境相关
        raise ManifestError(f"manifest 不可读: {p} ({exc})") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest YAML 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest 顶层必须是对象")

    project_id = data.get("project")
    if not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id):
        raise ManifestError(
            f"project_id 非法: {project_id!r}（须匹配 {PROJECT_ID_RE.pattern}）"
        )
    version = data.get("schemaVersion")
    if version not in SCHEMA_VERSIONS:
        raise ManifestError(f"schemaVersion 非法: {version!r}（支持 {SCHEMA_VERSIONS}）")
    return Manifest(project_id=project_id, raw=data, path=p)


def validate_manifest(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """用 manifest.schema.json 校验 dict，返回错误消息列表（空 = 通过）。"""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema)
    return [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(data)]
