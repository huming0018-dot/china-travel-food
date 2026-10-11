"""Shared public SDK/CLI stage operations; exact version references throughout."""
from __future__ import annotations
from . import __version__
from .auditor import Auditor
from .cleaner import Cleaner
from .scorer import Scorer
from .writer import append, record_id

def exact_ref(row, layer):
    result = {"project_id": row["project_id"], "layer": layer, "record_id": row["record_id"], "hash": row["content_hash"]}
    if layer != "RAW": result["version"] = row["version"]
    return result

class Stages:
    def __init__(self, manifest, contract, storage, as_of):
        self.manifest, self.contract, self.storage, self.as_of = manifest, contract, storage, as_of
        self.pid = manifest.project_id
    def _write(self, layer, kind, parent, content, schema_kind=None):
        identity = content.get("identity") or parent["content"]["identity"]
        rid = record_id(kind, self.contract.pack_id, identity["source_record_revision"], identity["source_record_id"])
        version = append(self.storage, self.pid, layer, rid, exact_ref(parent, "RAW" if layer == "ODS" else "ODS" if layer == "DW" else "DW"), content, schema_kind)
        return self.storage.read(self.pid, layer, rid, version)
    def clean(self, raw_id):
        raw = self.storage.read(self.pid, "RAW", raw_id)
        records = Cleaner(self.contract, as_of=self.as_of, tool_version=__version__).clean(raw)
        return [self._write("ODS", "cand", raw, rec["payload"]) for rec in records]
    def score(self, ods_id, ods_version=None):
        ods = self.storage.read(self.pid, "ODS", ods_id, ods_version)
        rec = Scorer(self.contract, self.as_of, __version__, manifest=self.manifest).score([ods])[0]
        return self._write("DW", "dw", ods, rec["payload"])
    def audit(self, raw_id, dw_id, dw_version=None):
        dw = self.storage.read(self.pid, "DW", dw_id, dw_version)
        result = Auditor(self.contract, self.as_of, __version__, self.storage, self.pid).audit(self.manifest, raw_id, dw_id, dw["version"])
        audit = self._write("APP", "audit", dw, result.audit_record["payload"], "audit")
        return {"passed": result.passed, "findings": result.findings, "audit": audit}
