"""Ontology packs (M4, P1-REPAIR-02): pure-data, versioned, immutable packs
outside the wheel.

A pack lives under <toolbox-root>/packs/<pack_id>/<version>/ and contains only
data files (YAML/JSON): contract metadata, field mappings, JSON pointers,
validation parameters, admission rubric and regression expectations. The core
toolbox package contains no food / Shanghai business fields; all domain shape
comes from pack data.

Contract (review gate):
- install pre-validates the whole pack (extensions, symlinks, flat files,
  required fields, schema, finite numbers, no dynamic operation keys, no
  out-of-bounds paths) BEFORE staging; an invalid pack never leaves an
  installed target and never loses the original versions/index;
- install copies into a NEW immutable version; same pack_id+version already
  present is rejected (same-version content cannot be overwritten);
- staging is atomic (temp dir + os.replace); index writes are atomic
  (tmp + os.replace) so concurrent installs cannot drop versions;
- verify rejects extra files, missing/tampered files, index path / version /
  pack_id escapes and symlinks;
- load and rollback verify the target pack first; a tampered pack is never
  activated or loaded; historical versions are kept.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
import fcntl
from pathlib import Path
from typing import Any

import yaml

from .schema import SchemaError, load_schema, validate_against
from .validators import stamp

PACK_SCHEMA_NAME = "pack"
INDEX_SCHEMA_VERSION = "pack-index/0.1"
PACK_CONTRACT_VERSION = "0.1.0"
VERSION_RE = r"^[0-9]+\.[0-9]+\.[0-9]+$"
PACK_ID_RE = r"^[a-z0-9][a-z0-9-]{0,63}$"
_ALLOWED_SUFFIXES = (".yaml", ".yml", ".json")
_DYNAMIC_KEYS = ("eval", "exec", "command", "template", "callback")


class PackError(Exception):
    """Pack contract, tamper or boundary violation."""


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackError(f"invalid YAML {path.name}: {exc}") from exc


def _reject_constant(name: str) -> None:
    raise PackError(f"non-finite number in JSON {name}")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          parse_constant=lambda c: _reject_constant(c))
    except PackError:
        raise
    except json.JSONDecodeError as exc:
        raise PackError(f"invalid JSON {path.name}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_finite(value: Any, where: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise PackError(f"non-finite number at {where}")


def _check_no_dynamic_keys(data: Any, where: str = "") -> None:
    _check_finite(data, where)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in _DYNAMIC_KEYS:
                raise PackError(f"dynamic operation key {k!r} at {where or 'root'}")
            _check_no_dynamic_keys(v, f"{where}/{k}")
            _check_finite(v, f"{where}/{k}")
    elif isinstance(data, list):
        for i, v in enumerate(data):
            _check_no_dynamic_keys(v, f"{where}[{i}]")


class OntologyManager:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.packs_dir = self.root / "packs"
        self.packs_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _index_lock(self, pack_id):
        self._check_pack_id(pack_id)
        parent = self.packs_dir / pack_id
        if parent.is_symlink():
            raise PackError("pack directory cannot be a symlink")
        parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(parent / ".index.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    # ---- index helpers ----
    def _index_path(self, pack_id: str) -> Path:
        self._check_pack_id(pack_id)
        p = self.packs_dir / pack_id / "index.json"
        if p.is_symlink():
            raise PackError(f"index is a symlink: {p}")
        return p

    @staticmethod
    def _check_pack_id(pack_id: str) -> None:
        if not isinstance(pack_id, str) or not re.fullmatch(PACK_ID_RE, pack_id):
            raise PackError(f"invalid pack_id {pack_id!r}")

    @staticmethod
    def _check_version(version: str) -> None:
        if not isinstance(version, str) or not re.fullmatch(VERSION_RE, version):
            raise PackError(f"invalid version {version!r}")

    def _read_index(self, pack_id: str) -> dict:
        p = self._index_path(pack_id)
        if not p.exists():
            raise PackError(f"pack {pack_id} not installed")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PackError(f"pack index corrupt: {exc}") from exc
        if data.get("pack_id") != pack_id:
            raise PackError("index pack_id mismatch")
        return data

    def _write_index(self, pack_id: str, index: dict) -> None:
        dest = self._index_path(pack_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, dest)  # atomic; concurrent installs cannot drop versions

    def _pack_version_dir(self, pack_id: str, version: str) -> Path:
        self._check_pack_id(pack_id)
        self._check_version(version)
        d = self.packs_dir / pack_id / version
        if d.is_symlink() or self.packs_dir.joinpath(pack_id).is_symlink():
            raise PackError(f"pack path is a symlink: {d}")
        resolved = d.resolve()
        if not resolved.is_relative_to(self.packs_dir.resolve()):
            raise PackError(f"pack path escapes packs root: {d}")
        return d

    # ---- install ----
    def install(self, source_dir: Path, pack_id: str | None = None,
                version: str | None = None) -> dict:
        src = Path(source_dir).resolve()
        if not src.is_dir():
            raise PackError(f"pack source directory not found: {src}")
        # pre-validate the whole source before any staging
        meta_path = src / "pack.yaml"
        if not meta_path.is_file():
            raise PackError("pack source must contain pack.yaml")
        meta = _load_yaml(meta_path)
        if not isinstance(meta, dict) or "pack" not in meta:
            raise PackError("pack.yaml must contain a 'pack' mapping")
        pack = meta["pack"]
        pid = pack_id or pack.get("pack_id")
        ver = version or pack.get("version")
        self._check_pack_id(pid)
        self._check_version(ver)
        if pack.get("pack_id") != pid or str(pack.get("version")) != ver:
            raise PackError("pack.yaml metadata does not match requested install ids")
        _check_no_dynamic_keys(meta)
        # validate contract schema now (before anything is written)
        try:
            validate_against(PACK_SCHEMA_NAME, pack)
        except SchemaError as exc:
            raise PackError(f"pack contract violation: {exc}") from exc

        staged: dict[str, bytes] = {}
        seen: set[str] = set()
        for child in sorted(src.iterdir()):
            if child.is_symlink():
                raise PackError(f"pack source contains a symlink: {child.name}")
            if not child.is_file():
                raise PackError(f"pack source must be flat files only: {child.name}")
            if child.suffix.lower() not in _ALLOWED_SUFFIXES:
                raise PackError(f"pack source must be YAML/JSON only: {child.name}")
            data = child.read_bytes()
            if not data:
                raise PackError(f"empty pack file: {child.name}")
            if child.suffix.lower() in (".yaml", ".yml"):
                _load_yaml(child)  # parse check; dynamic keys/finite numbers
                _check_no_dynamic_keys(_load_yaml(child))
            else:
                _check_no_dynamic_keys(_load_json(child))
            staged[child.name] = data
            seen.add(child.name)
        contract_files = (
            pack.get("contract", {}).get("fields", {}).get("file"),
            pack.get("contract", {}).get("pointers", {}).get("file"),
            pack.get("contract", {}).get("validation", {}).get("file"),
            pack.get("contract", {}).get("rubric", {}).get("file"),
            pack.get("contract", {}).get("expectations", {}).get("file"),
        )
        missing = [f for f in contract_files if f not in seen]
        if missing:
            raise PackError(f"pack contract references missing files: {missing}")
        for name in contract_files:
            child = src / name
            if child.suffix.lower() in (".yaml", ".yml"):
                parsed = _load_yaml(child)
                _check_no_dynamic_keys(parsed)
            else:
                _check_no_dynamic_keys(_load_json(child))

        # immutable versions: same pack_id + version already present -> reject.
        # The whole index read-modify-write is guarded by a lock so concurrent
        # installs of distinct versions never lose an index entry.
        with self._index_lock(pid):
            index = {}
            if self._index_path(pid).exists():
                index = self._read_index(pid)
                if ver in index.get("versions", {}):
                    raise PackError(f"version {ver} of pack {pid} already installed (immutable)")
            dest = self._pack_version_dir(pid, ver)
            if dest.exists():
                raise PackError(f"target pack version directory already exists: {dest}")

            # atomic staging: temp dir then rename; failure never leaves a half pack
            tmp_stage = Path(tempfile.mkdtemp(prefix=f".stage-{pid}-{ver}-",
                                              dir=self.packs_dir / pid))
            try:
                for name, data in staged.items():
                    (tmp_stage / name).write_bytes(data)
                files = {name: _sha256_file(tmp_stage / name) for name in staged}
                _validate_contract(tmp_stage / "pack.yaml")
                os.replace(tmp_stage, dest)
            except Exception:
                shutil.rmtree(tmp_stage, ignore_errors=True)
                raise

            versions = dict(index.get("versions", {}))
            for v in versions.values():
                v["active"] = False  # newest installed version becomes active
            versions[ver] = {
                "installed_at": stamp(),
                "active": True,
                "files": files,
            }
            index = {"schema_version": INDEX_SCHEMA_VERSION, "pack_id": pid,
                     "versions": versions}
            self._write_index(pid, index)
        return {"pack_id": pid, "version": ver, "installed": True,
                "active": True, "files": files}

    # ---- verify ----
    def verify(self, pack_id: str, version: str | None = None) -> dict:
        index = self._read_index(pack_id)
        versions = index.get("versions", {})
        if version is None:
            version = next((v for v, d in versions.items() if d.get("active")), None)
        if version is None or version not in versions:
            raise PackError(f"pack {pack_id} has no installed version to verify")
        self._check_version(version)
        ver_dir = self._pack_version_dir(pack_id, version)
        if not ver_dir.is_dir():
            raise PackError(f"tamper: pack version directory missing {ver_dir}")
        # extra files rejected
        expected = set(versions[version].get("files", {}))
        present = {c.name for c in ver_dir.iterdir()}
        extras = present - expected
        if extras:
            raise PackError(f"tamper: unexpected extra files {sorted(extras)}")
        for rel, expected_hash in versions[version].get("files", {}).items():
            rp = Path(rel)
            if rp.is_absolute() or ".." in rp.parts:
                raise PackError(f"tamper: index path escapes pack version: {rel}")
            f = ver_dir / rel
            resolved = f.resolve()
            if f.is_symlink() or not resolved.is_relative_to(ver_dir.resolve()):
                raise PackError(f"tamper: path escapes or symlink {rel}")
            if not f.is_file():
                raise PackError(f"tamper: file missing {rel}")
            if _sha256_file(f) != expected_hash:
                raise PackError(f"tamper: file hash mismatch {rel}")
        _validate_contract(ver_dir / "pack.yaml")
        return {"pack_id": pack_id, "version": version, "verified": True}

    # ---- list ----
    def list_packs(self) -> list[dict]:
        out = []
        if not self.packs_dir.is_dir():
            return out
        for entry in sorted(self.packs_dir.iterdir()):
            if not entry.is_dir() or entry.is_symlink():
                continue
            idx = entry / "index.json"
            if not idx.is_file():
                continue
            try:
                index = json.loads(idx.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            versions = index.get("versions", {})
            out.append({
                "pack_id": index.get("pack_id", entry.name),
                "versions": sorted(versions),
                "active": next((v for v, d in versions.items() if d.get("active")), None),
            })
        return out

    # ---- rollback ----
    def rollback(self, pack_id: str, version: str) -> dict:
        with self._index_lock(pack_id):
            index = self._read_index(pack_id)
            versions = index.get("versions", {})
            self._check_version(version)
            if version not in versions:
                raise PackError(f"version {version} of pack {pack_id} not installed")
            current = next((v for v, d in versions.items() if d.get("active")), None)
            if current == version:
                raise PackError(f"version {version} is already active")
            # a tampered target pack must never be activated
            self.verify(pack_id, version)
            for v in versions:
                versions[v]["active"] = (v == version)
            self._write_index(pack_id, index)
            return {"pack_id": pack_id, "from": current, "to": version,
                    "kept": sorted(versions)}

    # ---- load (for domain adapters; read-only) ----
    def load(self, pack_id: str) -> dict:
        with self._index_lock(pack_id):
            self.verify(pack_id)  # tampered active pack is never loaded
            index = self._read_index(pack_id)
            version = next((v for v, d in index.get("versions", {}).items() if d.get("active")), None)
            if version is None:
                raise PackError(f"pack {pack_id} has no active version")
            ver_dir = self._pack_version_dir(pack_id, version)
            return {
                "pack_id": pack_id,
                "version": version,
                "pack": _load_yaml(ver_dir / "pack.yaml"),
                "fields": _load_yaml(ver_dir / "fields.yaml"),
                "pointers": json.loads((ver_dir / "pointers.json").read_text(encoding="utf-8")),
                "validation": _load_yaml(ver_dir / "validation.yaml"),
                "rubric": _load_yaml(ver_dir / "rubric.yaml"),
                "expectations": _load_yaml(ver_dir / "expectations.yaml"),
            }


def _validate_contract(pack_yaml: Path) -> None:
    meta = _load_yaml(pack_yaml)
    pack = meta.get("pack") if isinstance(meta, dict) else None
    if not isinstance(pack, dict):
        raise PackError("pack.yaml must contain a 'pack' mapping")
    try:
        validate_against(PACK_SCHEMA_NAME, pack)
    except SchemaError as exc:
        raise PackError(f"pack contract violation: {exc}") from exc
