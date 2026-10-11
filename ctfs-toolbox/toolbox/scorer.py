"""Pack-defined deterministic scoring, admission and provenance."""
from __future__ import annotations
import copy
import math
from .bindings import BindingError, binding, utc
from .pack_schema import evidence_fields

class ScorerError(ValueError):
    pass

def number(value, label, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ScorerError(label + " must be finite numeric data")
    if minimum is not None and value < minimum:
        raise ScorerError(label + " is below minimum")
    return value

class Scorer:
    OPERATORS = frozenset(("sources", "refs", "coverage", "recency"))
    VALIDATIONS = frozenset(("coverage_ok", "quote_ok", "hash_ok", "classification_ok", "pointer_ok"))
    def __init__(self, contract, as_of, tool_version, manifest=None):
        self.contract, self.as_of, self.tool_version = contract, as_of, tool_version
        self.manifest = manifest
        try:
            self.clock = utc(as_of, "as_of")
            self.bound = binding(contract, as_of, tool_version, manifest)
        except BindingError as exc: raise ScorerError(str(exc)) from exc
        scoring = contract.rubric.get("scoring")
        if not isinstance(scoring, dict): raise ScorerError("rubric.scoring missing")
        self.parts, self.weights = scoring.get("parts"), scoring.get("weights", {})
        if not isinstance(self.parts, list) or not self.parts or not isinstance(self.weights, dict):
            raise ScorerError("scoring weights/parts malformed")
        self.threshold = number(scoring.get("threshold"), "threshold")
        self.hard_blocks = scoring.get("hard_blocks", [])
        names = [p.get("name") if isinstance(p, dict) else None for p in self.parts]
        if any(n not in self.OPERATORS for n in names) or len(set(names)) != len(names):
            raise ScorerError("unknown or duplicate scoring operator")
        if not isinstance(self.hard_blocks, list) or any(n not in names for n in self.hard_blocks):
            raise ScorerError("unknown hard-block operator")
        if any(n not in names for n in self.weights): raise ScorerError("weight names have no operator")
        admission = contract.rubric.get("admission", {})
        if not isinstance(admission, dict): raise ScorerError("admission malformed")
        self.rules = admission.get("rules", [])
        if not isinstance(self.rules, list): raise ScorerError("admission rules malformed")
        for rule in self.rules:
            if not isinstance(rule, dict) or rule.get("pass") not in self.VALIDATIONS or not isinstance(rule.get("id"), str):
                raise ScorerError("unknown admission rule")
        self.fact_fields = set(evidence_fields(contract))

    def score(self, ods_records):
        if not isinstance(ods_records, list): raise ScorerError("ODS records must be list")
        return [self._score_one(rec) for rec in ods_records]

    def _score_one(self, rec):
        payload = rec.get("payload", rec.get("content"))
        if not isinstance(payload, dict): raise ScorerError("ODS content missing")
        if "score" in payload or "passed" in payload or "score" in rec or "passed" in rec:
            raise ScorerError("caller supplied score/passed")
        try:
            current = binding(self.contract, self.as_of, self.tool_version, self.manifest)
        except BindingError as exc: raise ScorerError(str(exc)) from exc
        if current != self.bound: raise ScorerError("binding changed during scoring")
        if payload.get("as_of") != self.as_of: raise ScorerError("ODS as_of differs")
        for field in ("identity", "draft", "classification", "validation", "scope", "unknowns", "provenance"):
            if not isinstance(payload.get(field), dict): raise ScorerError("ODS normalized mapping missing: " + field)
        for field in ("evidence", "sources"):
            if not isinstance(payload.get(field), list) or any(not isinstance(item, dict) for item in payload[field]):
                raise ScorerError("ODS normalized list missing: " + field)
        provenance = payload.get("provenance", {})
        if (provenance.get("tool_version") != self.tool_version or
            provenance.get("pack_id") != self.contract.pack_id or provenance.get("pack_version") != self.contract.version):
            raise ScorerError("ODS tool/pack differs")
        parts, reasons, blocked = {}, [], []
        for part in self.parts:
            name = part["name"]
            value = self._value(name, payload, part)
            weight = number(self.weights.get(name, part.get("weight", 1)), "weight", 0)
            minimum = number(part.get("min", 0), "minimum")
            hard = part.get("hard", False)
            if type(hard) is not bool: raise ScorerError("hard must be boolean")
            required = hard or name in self.hard_blocks
            reason = f"{name}: value={value}; weight={weight}; minimum={minimum}; required={required}"
            parts[name] = {"value": value, "weight": weight, "reason": reason}
            reasons.append(reason)
            if required and value < minimum: blocked.append(name)
        validation = payload.get("validation", {})
        admission = []
        for rule in self.rules:
            passed = validation.get(rule["pass"]) is True
            admission.append({"id": rule["id"], "check": rule["pass"], "passed": passed})
            if not passed: blocked.append("admission:" + rule["id"])
        total = sum(part["value"]*part["weight"] for part in parts.values())
        number(total, "total score")
        passed = total >= self.threshold and not blocked
        output = copy.deepcopy(payload)
        output["score"] = {"total": total, "passed": passed, "parts": parts,
                           "reasons": reasons, "blocked": blocked, "admission": admission}
        output["scope"] = copy.deepcopy(payload.get("scope", {}))
        output["scope"]["as_of"] = self.as_of
        output["scope"]["unknowns"] = copy.deepcopy(payload.get("unknowns", {}))
        output["provenance"] = {"tool": "scorer", "tool_version": self.tool_version,
           "pack_id": self.contract.pack_id, "pack_version": self.contract.version,
           "config_fingerprint": self.bound["fingerprint"], "binding": self.bound}
        return {"project_id": rec["project_id"], "layer": "dw", "kind": "scored_candidate",
                "payload": output, "lineage": copy.deepcopy(rec.get("lineage", {}))}

    def _value(self, name, payload, part):
        if name == "sources":
            ids = payload.get("identity", {}).get("source_id", [])
            if not isinstance(ids, list) or any(not isinstance(s, str) or not s for s in ids):
                raise ScorerError("source IDs malformed")
            return len(set(ids))
        if name == "refs": return len(payload.get("evidence", []))
        if name == "coverage":
            draft = payload.get("draft", {})
            expected = {f for f in self.fact_fields if f in draft and draft[f] not in (None, "", [], {})}
            covered = {e.get("field") for e in payload.get("evidence", []) if isinstance(e, dict)}
            return len(expected & covered)/len(expected) if expected else 0.0
        if name == "recency":
            horizon = number(part.get("horizon_days"), "horizon_days", 0)
            if horizon <= 0: raise ScorerError("horizon_days must be positive")
            sources = payload.get("sources")
            if not isinstance(sources, list) or not sources: raise ScorerError("source times missing")
            try: times = [utc(s.get("retrieved_at"), "source.retrieved_at") for s in sources]
            except (BindingError, AttributeError) as exc: raise ScorerError("source time invalid") from exc
            if any(t > self.clock for t in times): raise ScorerError("source time follows as_of")
            age = (self.clock-max(times)).total_seconds()/86400
            return max(0.0, 1.0-age/horizon)
        raise ScorerError("unknown scoring operator")
