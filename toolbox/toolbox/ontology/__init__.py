"""M4 本体库（PRD v2.2 §5）：本体包 = 结构化配置包（YAML+JSON 目录包）。

v1 内核（Phase 0）：
- verify：pack.yaml 合法（pack.schema.json）+ 六件套文件存在 + YAML/JSON 可解析。
- install：登记到包注册表 ledger（name/version/sha256/installed_at），幂等拒绝重复。
- list：读 ledger。

v2（后续）：semver + 复制部署 + rollback；v3：包继承/包市场。
本体包是唯一允许业务词的地方；包外代码 grep 业务词不得命中。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..schema import load_schema

# 六件套：pack.yaml files 段必须引用且文件必须存在
REQUIRED_FILE_KEYS = (
    "taxonomy",
    "keyword_roots",
    "scoring_rules",
    "regression_set",
    "source_plan",
    "schemas",
)


class PackError(ValueError):
    """本体包不合法。"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def pack_sha256(pack_dir: Path, pack: dict[str, Any]) -> str:
    """聚合 SHA：pack.yaml + files 引用的全部文件，按相对路径排序后拼接每行 'relpath sha256' 再 hash。"""
    lines: list[str] = []
    files = pack.get("files", {})
    flat: list[Path] = [pack_dir / "pack.yaml"]
    for key in REQUIRED_FILE_KEYS:
        rel = files.get(key)
        if isinstance(rel, str):
            flat.append(pack_dir / rel)
        elif isinstance(rel, list):
            flat.extend(pack_dir / r for r in rel)
    for p in sorted(flat, key=lambda x: str(x.relative_to(pack_dir))):
        rel = str(p.relative_to(pack_dir))
        lines.append(f"{rel} {_sha256_file(p)}")
    digest = hashlib.sha256()
    digest.update("\n".join(lines).encode("utf-8"))
    return digest.hexdigest()


def load_pack(pack_dir: str | Path) -> dict[str, Any]:
    """读 pack.yaml 并校验 pack.schema.json。返回 pack dict。"""
    p = Path(pack_dir)
    pack_file = p / "pack.yaml"
    if not pack_file.is_file():
        raise PackError(f"缺少 pack.yaml: {pack_file}")
    try:
        data = yaml.safe_load(pack_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackError(f"pack.yaml 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise PackError("pack.yaml 顶层必须是对象")
    from jsonschema import Draft202012Validator

    errors = [
        f"{list(e.path)}: {e.message}"
        for e in Draft202012Validator(load_schema("pack")).iter_errors(data)
    ]
    if errors:
        raise PackError("pack.yaml 未通过 pack.schema.json: " + "; ".join(errors))
    return data


def verify_pack(pack_dir: str | Path) -> list[str]:
    """校验本体包，返回错误列表（空 = 通过）。"""
    errors: list[str] = []
    p = Path(pack_dir)
    try:
        pack = load_pack(p)
    except PackError as exc:
        return [str(exc)]
    files = pack.get("files", {})
    for key in REQUIRED_FILE_KEYS:
        rel = files.get(key)
        if rel is None:
            errors.append(f"files.{key} 缺失")
            continue
        if isinstance(rel, list):
            for r in rel:
                if not (p / r).is_file():
                    errors.append(f"files.{key} 文件不存在: {r}")
        elif not (p / rel).is_file():
            errors.append(f"files.{key} 文件不存在: {rel}")
    # YAML/JSON 可解析性
    for rel in [files.get(k) for k in ("taxonomy", "scoring_rules", "source_plan")]:
        if rel and isinstance(rel, str) and (p / rel).is_file():
            try:
                yaml.safe_load((p / rel).read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                errors.append(f"{rel} 解析失败: {exc}")
    for rel in [files.get(k) for k in ("keyword_roots", "regression_set")]:
        if rel and isinstance(rel, str) and (p / rel).is_file():
            try:
                json.loads((p / rel).read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{rel} 解析失败: {exc}")
    return errors


@dataclass(frozen=True)
class InstalledPack:
    name: str
    version: str
    sha256: str
    installed_at: str
    source: str


def install_pack(pack_dir: str | Path, ledger_path: str | Path) -> InstalledPack:
    """登记本体包到 ledger（幂等：同 name+version 已装则拒绝）。"""
    p = Path(pack_dir)
    ledger = Path(ledger_path)
    errors = verify_pack(p)
    if errors:
        raise PackError("verify 未通过: " + "; ".join(errors))
    pack = load_pack(p)
    name, version = pack["name"], pack["version"]
    records = _read_ledger(ledger)
    if any(r["name"] == name and r["version"] == version for r in records["installed"]):
        raise PackError(f"{name}@{version} 已安装（幂等拒绝重复登记）")
    entry = {
        "name": name,
        "version": version,
        "sha256": pack_sha256(p, pack),
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(p),
    }
    records["installed"].append(entry)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return InstalledPack(**entry)


def list_packs(ledger_path: str | Path) -> list[dict[str, Any]]:
    """读取 ledger 已安装包列表。"""
    return list(_read_ledger(Path(ledger_path))["installed"])


def _read_ledger(ledger: Path) -> dict[str, Any]:
    if not ledger.is_file():
        return {"schemaVersion": "0.1.0", "installed": []}
    try:
        data = json.loads(ledger.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackError(f"ledger 解析失败 {ledger}: {exc}") from exc
    if not isinstance(data, dict) or "installed" not in data:
        raise PackError(f"ledger 结构非法: {ledger}")
    return data
