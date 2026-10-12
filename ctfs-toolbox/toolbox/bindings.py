"""Deterministic bindings for actual tool bytes, complete packs and manifests."""
from __future__ import annotations
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
from . import __version__
from .ontology import OntologyManager
from rfc3339_validator import validate_rfc3339

class BindingError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def utc(value, label="timestamp"):
    if not isinstance(value, str) or not validate_rfc3339(value.upper()):
        raise BindingError(label + " must be RFC3339 UTC")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    if parsed.utcoffset() != dt.timedelta(0):
        raise BindingError(label + " must use UTC")
    return parsed

def tool_manifest():
    root = Path(__file__).parent
    files = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in (".py", ".json"):
            if p.is_symlink():
                raise BindingError("tool resource symlink")
            files[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    deps = {}
    for name in ("PyYAML", "jsonschema", "rfc3339-validator", "psycopg"):
        try: deps[name] = metadata.version(name)
        except metadata.PackageNotFoundError: deps[name] = None
    return {"version": __version__, "files": files, "dependencies": deps}

def pack_manifest(contract):
    loaded = OntologyManager(contract.store_root).load(contract.pack_id)
    if loaded["version"] != contract.version:
        raise BindingError("pack active version changed")
    names = ("pack", "fields", "pointers", "validation", "rubric", "expectations")
    data = {name: getattr(contract, name) for name in names}
    if canonical(data) != canonical({name: loaded[name] for name in names}):
        raise BindingError("contract differs from installed pack")
    folder = Path(contract.store_root).resolve()/"packs"/contract.pack_id/contract.version
    hashes = {}
    for name in ("pack.yaml", "fields.yaml", "pointers.json", "validation.yaml", "rubric.yaml", "expectations.yaml"):
        path = folder/name
        if path.is_symlink(): raise BindingError("pack resource symlink")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"pack_id": contract.pack_id, "version": contract.version,
            "files": hashes, "data_hash": digest(data)}

def binding(contract, as_of, tool_version, manifest=None):
    utc(as_of, "as_of")
    if tool_version != __version__:
        raise BindingError("claimed tool version differs from actual package")
    data = manifest.to_dict() if hasattr(manifest, "to_dict") else manifest
    if data is not None and not isinstance(data, dict):
        raise BindingError("manifest binding must be a mapping")
    file_hash = None
    if hasattr(manifest, "path"):
        from .manifest import Manifest
        fresh = Manifest.load(manifest.path)
        if canonical(fresh.to_dict()) != canonical(data):
            raise BindingError("manifest object differs from current file")
        file_hash = hashlib.sha256(Path(manifest.path).read_bytes()).hexdigest()
    value = {"as_of": as_of, "tool": tool_manifest(), "pack": pack_manifest(contract),
             "manifest": data, "manifest_hash": digest(data) if data is not None else None,
             "manifest_file_hash": file_hash}
    return {"fingerprint": digest(value), **value}
