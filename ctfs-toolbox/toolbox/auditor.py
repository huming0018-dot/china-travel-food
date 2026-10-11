"""M6 independently derives the exact stored chain from immutable RAW bytes."""
from __future__ import annotations
from .bindings import BindingError, binding, canonical, digest
from .cleaner import Cleaner, CleanerError
from .scorer import Scorer, ScorerError

class AuditorError(ValueError):
    pass

class AuditResult:
    def __init__(self, passed, findings, audit_record):
        self.passed, self.findings, self.audit_record = passed, findings, audit_record

class Auditor:
    def __init__(self, contract, as_of, tool_version, storage, project_id):
        self.contract, self.as_of, self.tool_version = contract, as_of, tool_version
        self.storage, self.project_id = storage, project_id

    def audit(self, manifest, raw_id, dw_id, dw_version=None):
        findings, refs, bound = [], {}, None
        try:
            data = manifest.to_dict() if hasattr(manifest, "to_dict") else manifest
            if data.get("project_id") != self.project_id:
                raise AuditorError("manifest project differs")
            bound = binding(self.contract, self.as_of, self.tool_version, manifest)
            pid = self.project_id
            raw = self.storage.read(pid, "RAW", raw_id)
            configured = data.get("raw", {}).get("sources", [])
            if not isinstance(configured, list) or not any(isinstance(source, dict) and source.get("url") == raw.get("source_url") for source in configured):
                raise AuditorError("RAW source URL outside Manifest source allow-list")
            dw = self.storage.read(pid, "DW", dw_id, dw_version)
            if dw_version is not None and dw.get("version") != dw_version:
                raise AuditorError("exact DW version differs")
            parent = dw.get("parent_ref", {})
            if parent.get("layer") != "ODS" or parent.get("project_id") != pid:
                raise AuditorError("DW parent project/layer differs")
            ods = self.storage.read(pid, "ODS", parent.get("record_id"), parent.get("version"))
            def ref(row, layer):
                result = {"project_id": pid, "layer": layer, "record_id": row["record_id"], "hash": row["content_hash"]}
                if layer != "RAW": result["version"] = row["version"]
                return result
            refs = {"raw": ref(raw, "RAW"), "ods": ref(ods, "ODS"), "dw": ref(dw, "DW")}
            if canonical(parent) != canonical(refs["ods"]):
                findings.append("DW exact parent differs from ODS")
            if canonical(ods.get("parent_ref")) != canonical(refs["raw"]):
                findings.append("supplied RAW is not the exact ODS parent")
            for layer, row in (("ODS", ods), ("DW", dw)):
                if self.storage.verify_lineage(pid, layer, row["record_id"], row["version"]) is not True:
                    findings.append(layer + " lineage invalid")
            records = Cleaner(self.contract, as_of=self.as_of, tool_version=self.tool_version).clean(raw)
            stored = ods.get("content", {}).get("identity", {})
            key = (stored.get("source_record_id"), stored.get("source_record_revision"))
            if not isinstance(key[0], (str, int)) or type(key[0]) is bool or type(key[1]) is not int or key[1] < 1:
                raise AuditorError("stored candidate identity invalid")
            matches = [r for r in records if canonical([r["payload"]["identity"].get("source_record_id"), r["payload"]["identity"].get("source_record_revision")]) == canonical(list(key))]
            if len(matches) != 1: raise AuditorError("exact candidate identity/revision not unique in RAW")
            recomputed_ods = matches[0]
            recomputed_dw = Scorer(self.contract, self.as_of, self.tool_version, manifest=manifest).score([recomputed_ods])[0]
            for layer, row, expected in (("ODS", ods, recomputed_ods["payload"]), ("DW", dw, recomputed_dw["payload"])):
                if canonical(row.get("content")) != canonical(expected):
                    findings.append(layer + " full content differs from RAW derivation")
                wrapped = {"schemaVersion": "0.2.0", "project_id": pid, "layer": layer, "record_id": row["record_id"], "parent_ref": row["parent_ref"], "content": expected}
                if row.get("content_hash") != digest(wrapped):
                    findings.append(layer + " hash differs from RAW derivation")
            if recomputed_dw["payload"]["score"].get("passed") is not True:
                findings.append("recomputed admission blocked")
            provenance = dw.get("content", {}).get("provenance", {})
            if canonical(provenance.get("binding")) != canonical(bound) or provenance.get("config_fingerprint") != bound["fingerprint"]:
                findings.append("DW tool/pack/manifest/as_of binding stale or absent")
        except Exception as exc:
            # Driver errors may contain DSNs; report only known contract messages.
            reason = type(exc).__name__ + ": " + str(exc) if isinstance(exc, (AuditorError, CleanerError, ScorerError, BindingError)) else type(exc).__name__
            findings.append("audit failed: " + reason)
        passed = not findings
        audit = {"passed": passed, "findings": findings, "as_of": self.as_of, "refs": refs,
                 "binding": bound, "config_fingerprint": bound["fingerprint"] if bound else None,
                 "manifest_fingerprint": bound["manifest_hash"] if bound else None,
                 "manifest_schema_version": bound["manifest"].get("schemaVersion") if bound else None}
        for name in ("raw", "ods", "dw"):
            audit[name+"_id"] = refs.get(name, {}).get("record_id")
            audit[name+"_version"] = refs.get(name, {}).get("version")
            audit[name+"_hash"] = refs.get(name, {}).get("hash")
        content = {"audit": audit, "provenance": {"tool": "auditor", "tool_version": self.tool_version,
                   "pack_id": self.contract.pack_id, "pack_version": self.contract.version}}
        record = {"project_id": self.project_id, "layer": "app", "kind": "audit", "payload": content,
                  "lineage": {"steps": ["raw", "ods", "dw", "audit"], "captured_at": self.as_of,
                              "tool_versions": [self.tool_version]}}
        return AuditResult(passed, findings, record)
