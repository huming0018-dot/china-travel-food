"""M2 Cleaner: RAW -> ODS, fully driven by the pack contract. (P2-REPAIR-03)

The cleaner ALWAYS consumes the RAW record exactly as the storage layer
returns it (payload may be bytes / str / dict) and verifies the actual stored
bytes BEFORE parsing:

- bytes/str  -> SHA256 of those exact bytes must equal raw content_hash and
                source_hash; then STRICT JSON parse (duplicate keys rejected,
                NaN/Infinity rejected). Never re-wraps into a dict first.
- dict       -> fixture/tests only: canonical bytes of the dict must match the
                stored content_hash; then the same code path applies.

Identity / source shapes follow REPAIR-03:
- identity gains source_record_id and carries source_id (distinct publisher
  ids) + source_version_ids (version ids);
- `sources` is the deduplicated metadata of the actually-referenced source
  versions {version_id, source_id, url, retrieved_at, canonical_body_sha256}
  WITHOUT repeating bodies;
- validation outputs strict booleans coverage_ok/quote_ok/hash_ok/
  classification_ok (software mode: pointer_ok), plus fact/classification
  field lists and their pointers, and raw_hash_scope/raw_retained.

Conflicts are rejected: duplicate candidate id, duplicate source version_id
with different content, evidence revision != candidate revision.
Optional unknown fields (hours/menu/price/business_relation/taste/published_at)
are declared in the pack (optional + default unknown); a missing optional
pointer yields "unknown", never an error or a fabricated value. Required fact
fields missing / enum / minimum / maxItems / unknown type / strict bool-int /
False vs 0 are all enforced. Pointer evidence binds the field's own pointer to
the real node (software: re-resolve from the parsed root; cuisines: exact
Unicode slice). Zero business fields here: every field name comes from the pack.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from jsonschema import Draft202012Validator, FormatChecker

from toolbox.pack_schema import PackContract, evidence_fields, classification_fields, resolve_pointer
from toolbox.validators import ValidatorError, canonical_hash_check, unicode_quote_check, iso_date, text


class CleanerError(ValueError):
    pass


@dataclass(frozen=True)
class CleanOptions:
    as_of: str                 # fixed as_of from manifest/input; never local time
    tool_version: str
    max_quote_len: int = 5000


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(payload: dict) -> bytes:
    """Canonical JSON bytes for dict fixtures (must match stored content_hash)."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _non_finite(value, field: str):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise CleanerError(f"field {field}: non-finite float rejected")
    if isinstance(value, list):
        for v in value:
            _non_finite(v, field)
    if isinstance(value, dict):
        for v in value.values():
            _non_finite(v, field)


def _check_constraints(value, schema: dict, field: str):
    if not isinstance(schema,dict):raise CleanerError(f'field {field}: schema must be mapping')
    try:
        Draft202012Validator.check_schema(schema)
        errors=list(Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(value))
    except Exception as exc:raise CleanerError(f'field {field}: invalid schema') from exc
    if errors:raise CleanerError(f'field {field}: schema validation rejected {errors[0].validator}')


def _coerce_by_schema(value, schema: dict, field: str):
    """Strict declared-schema validation, then limited normalization.

    The declared ``type`` is authoritative and checked FIRST: a value whose
    runtime kind disagrees with the declared type is rejected regardless of
    its own shape (e.g. declared string but value is a list, declared array
    but value is a dict). Unknown schema types are rejected. bool is never
    accepted as int, and False/0 are not interchangeable. Constraints
    (enum/min/max/length/count) always run after type validation.
    """
    _non_finite(value, field)
    if not isinstance(schema, dict):
        raise CleanerError(f"field {field}: schema must be an object")
    _check_constraints(value,schema,field)
    t = schema.get("type")
    if t is None:
        # No declared type: constraints only (e.g. enum on a bare value).
        _check_constraints(value, schema, field)
        return value
    if t == "boolean":
        if type(value) is not bool:
            raise CleanerError(f"field {field}: expected boolean, got {type(value).__name__}")
        _check_constraints(value, schema, field)
        return value
    if t == "integer":
        if type(value) is not int:
            raise CleanerError(f"field {field}: expected integer, got {type(value).__name__}")
        _check_constraints(value, schema, field)
        return value
    if t == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CleanerError(f"field {field}: expected number, got {type(value).__name__}")
        _check_constraints(value, schema, field)
        return value
    if t == "string":
        if not isinstance(value, str):
            raise CleanerError(f"field {field}: expected string, got {type(value).__name__}")
        coerced = text(value, field, limit=schema.get("maxLength", 1000), optional=True)
        _check_constraints(coerced, schema, field)
        return coerced
    if t == "array":
        if not isinstance(value, list):
            raise CleanerError(f"field {field}: expected array, got {type(value).__name__}")
        items = schema.get("items", {})
        out = [_coerce_by_schema(v, items, f"{field}[]") for v in value]
        _check_constraints(out, schema, field)
        return out
    if t == "object":
        if not isinstance(value, dict):
            raise CleanerError(f"field {field}: expected object, got {type(value).__name__}")
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        return {k: _coerce_by_schema(v, props.get(k, {}), f"{field}.{k}")
                for k, v in value.items()}
    raise CleanerError(f"field {field}: unknown schema type {t!r} rejected")


def _normalize_classification(value, field: str, schema: dict):
    if "enum" in schema:
        if value not in schema["enum"]:
            raise CleanerError(f"classification {field}: {value!r} not allowed")
    return value


def _strict_json_loads(data: bytes) -> dict:
    """Strict JSON parse of the RAW payload bytes.

    Rejects duplicate keys (object_pairs_hook) and the non-finite constants
    NaN / Infinity / -Infinity (parse_constant). Nested objects are covered.
    """
    def _dup_hook(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise CleanerError(f"duplicate JSON key {k!r}")
            out[k] = v
        return out

    def _no_constant(token: str):
        raise CleanerError(f"non-finite JSON constant {token!r} rejected")

    try:
        root = json.loads(data.decode("utf-8"), object_pairs_hook=_dup_hook,
                          parse_constant=_no_constant)
    except UnicodeDecodeError as exc:
        raise CleanerError("raw payload is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise CleanerError(f"raw payload is not strict JSON: {exc}") from exc
    if not isinstance(root, dict):
        raise CleanerError("raw payload root must be an object")
    _non_finite(root,"RAW")
    return root


class Cleaner:
    """RAW -> ODS records. Storage writes are performed by the caller (CLI/SDK)."""

    def __init__(self, contract: PackContract, options: CleanOptions | None = None,
                 *, as_of: str | None = None, tool_version: str | None = None,
                 max_quote_len: int = 5000):
        if options is None:
            if not as_of or not tool_version:
                raise CleanerError("Cleaner needs as_of + tool_version (or options)")
            options = CleanOptions(as_of=as_of, tool_version=tool_version,
                                   max_quote_len=max_quote_len)
        self.contract = contract
        self.options = options
        self._pointers = contract.pointers.get("pointers", {})
        self._fact_fields = set(evidence_fields(contract))
        self._cls_fields = set(classification_fields(contract))
        self._quote_mode = bool(contract.validation.get("unicode_quote", {}).get("enabled", True))
        self._pointer_mode = bool(contract.validation.get("json_pointer_evidence", {}).get("enabled", False))
        if self._quote_mode == self._pointer_mode:
            raise CleanerError(f"pack {contract.pack_id}: exactly one of unicode_quote/json_pointer_evidence must be enabled")
        if self._fact_fields & self._cls_fields:
            raise CleanerError(f"pack {contract.pack_id}: fact and classification fields overlap")
        fields = contract.fields
        identity = fields.get("identity") or {}
        self._id_pointer = identity.get("candidate_id_pointer", "/id")
        self._rev_path = identity.get("candidate_revision_path", "/revision")
        self._title_field = identity.get("title_field")
        if not isinstance(self._title_field, str) or not self._title_field:
            raise CleanerError(f"pack {contract.pack_id}: identity.title_field required")
        sc = fields.get("source_contract") or {}
        self._src_path = sc.get("source_versions_path", "/source_versions")
        self._src_id_field = sc.get("source_id_field", "source_id")
        self._ver_id_field = sc.get("version_id_field", "version_id")
        self._body_field = sc.get("body_field", "canonical_body")
        self._hash_field = sc.get("hash_field", "canonical_body_sha256")
        self._retrieved_field = sc.get("retrieved_at_field", "retrieved_at")
        self._ev_source_key = sc.get("evidence_source_key", "source_version_id")
        self._candidates_path = sc.get("candidates_path", "/candidates")
        self._draft_path = sc.get("candidate_draft_path", "/draft")
        self._evidence_path = sc.get("candidate_evidence_path", "/evidence")
        self._publisher_id_field = sc.get("publisher_id_field", self._src_id_field)
        url_cfg = sc.get("source_url_field", ["url", "source_url"])
        self._url_fields = [url_cfg] if isinstance(url_cfg, str) else list(url_cfg or [])
        self._publisher_source_id = sc.get("publisher_source_id")
        raw_env = sc.get("raw_envelope")
        if raw_env is not None and not isinstance(raw_env, dict):
            raise CleanerError(f"pack {contract.pack_id}: raw_envelope must be an object")
        self._raw_env = raw_env
        self._source_id_mode = sc.get("source_id_mode")
        # validation semantics from the pack (executed downstream; preserved here)
        v = contract.validation
        mscope = v.get("machine_scope") or {}
        self._scope_path = mscope.get("candidate_scope_path", "/scope")
        self._allowed_scope = mscope.get("allowed", [])
        if not isinstance(self._allowed_scope, list) or not all(isinstance(s, str) for s in self._allowed_scope):
            raise CleanerError(f"pack {contract.pack_id}: machine_scope.allowed must be list[str]")
        self._scope_default = mscope.get("default")
        if self._scope_default is not None and not isinstance(self._scope_default, str):
            raise CleanerError(f"pack {contract.pack_id}: machine_scope.default must be a string or null")
        esem = v.get("evidence_semantics") or {}
        self._evidence_semantics = esem
        self._independent_sources = esem.get("independent_sources", "distinct_source_version_id")
        self._editorial_never_diner = bool(esem.get("editorial_source_never_diner", False))
        unk = v.get("unknown_fields") or {}
        self._unknown_default = unk.get("default", "unknown")
        h = v.get("hash") or {}
        self._raw_hash_scope = h.get("raw_hash_scope", "source_bytes")
        self._raw_retained = bool(h.get("raw_retained", False))

    def _scope_block(self, kind: str | None) -> dict:
        """Unified machine-scope block (M3 contract): payload.scope is a dict,
        never None; kind carries the candidate scope (or the pack machine
        scope default), the rest is pack configuration verbatim."""
        if not isinstance(kind, str) or not kind:
            raise CleanerError("payload scope kind must be a non-empty string")
        return {
            "kind": kind,
            "evidence_semantics": self._evidence_semantics,
            "raw_hash_scope": self._raw_hash_scope,
            "original_http_retained": self._raw_retained,
        }

    def _unknowns_from(self, node: dict, label: str) -> dict:
        """Extract pack-declared unknown fields from a node (draft for
        cuisines, root JSON for software); missing optional ones resolve to
        the pack default, never fabricated as known."""
        out = {}
        for field, spec in self._unknown_fields_specs().items():
            try:
                value = resolve_pointer(node, spec["pointer"])
            except ValueError:
                value = None
            if value in (None, "", [], {}) or (isinstance(value, float)
                                               and (math.isnan(value) or math.isinf(value))):
                out[field] = spec.get("default", self._unknown_default)
            else:
                out[field] = value
        return out

    # ---- public ----
    def clean(self, raw_record: dict) -> list[dict]:
        payload = raw_record.get("payload")
        content_hash = raw_record.get("content_hash")
        source_hash = raw_record.get("source_hash")
        if isinstance(payload, bytes):
            root = self._consume_bytes(payload, content_hash, source_hash)
        elif isinstance(payload, str):
            root = self._consume_bytes(payload.encode("utf-8"), content_hash, source_hash)
        elif isinstance(payload, dict):
            # fixture path: canonical bytes must match the stored content_hash
            try: actual = _sha256(_canonical_bytes(payload))
            except (ValueError,UnicodeError) as exc:raise CleanerError("dict fixture is not finite UTF-8 JSON") from exc
            self._check_stored_hash(actual, content_hash, source_hash)
            root = payload
        else:
            raise CleanerError("raw payload must be bytes, str or an object")
        if self._pointer_mode:
            return [self._clean_official(root, raw_record)]
        try:
            candidates = resolve_pointer(root, self._candidates_path)
        except ValueError as exc:
            raise CleanerError(f"candidates path {self._candidates_path}: {exc}") from exc
        if not isinstance(candidates, list):
            raise CleanerError("payload candidates must be a list")
        sources = self._source_map(root)
        if self._quote_mode:
            self._check_source_bytes(sources)
        records = []
        seen_ids = set()
        for idx, cand in enumerate(candidates):
            rec = self._clean_candidate(root, cand, idx, raw_record, sources)
            identity = rec["payload"]["identity"]
            cid = identity["source_record_id"]
            if cid in seen_ids:
                raise CleanerError(f"duplicate candidate id {cid!r}")
            seen_ids.add(cid)
            records.append(rec)
        return records

    # ---- internals: raw consumption ----
    def _consume_bytes(self, data: bytes, content_hash, source_hash) -> dict:
        actual = _sha256(data)
        self._check_stored_hash(actual, content_hash, source_hash)
        return _strict_json_loads(data)

    def _check_stored_hash(self, actual: str, content_hash, source_hash):
        for label,value in (("content_hash",content_hash),("source_hash",source_hash)):
            if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
                raise CleanerError("RAW "+label+" must be SHA256 of stored bytes")
            if value!=actual:raise CleanerError("RAW "+label+" mismatch")

    # ---- internals: cuisines (unicode quote) mode ----
    def _source_map(self, payload: dict) -> dict[str, dict]:
        try:
            srcs = resolve_pointer(payload, self._src_path)
        except ValueError as exc:
            raise CleanerError(f"source_versions path {self._src_path}: {exc}") from exc
        if not isinstance(srcs, list):
            raise CleanerError("source_versions must be a list (original bundle contract)")
        out = {}
        for s in srcs:
            if not isinstance(s, dict):
                raise CleanerError("source_versions item must be an object")
            vid = s.get(self._ver_id_field)
            if not isinstance(vid, str) or not vid:
                raise CleanerError(f"source item missing {self._ver_id_field}")
            if vid in out and out[vid] != s:
                raise CleanerError(f"duplicate source version_id {vid!r} with different content")
            out[vid] = s
        return out

    def _source_url(self, src: dict):
        for key in self._url_fields:
            val = src.get(key)
            if isinstance(val, str) and val:
                return val
        return None

    def _clean_candidate(self, bundle: dict, cand: dict, idx: int, raw_record: dict,
                         sources: dict[str, dict]) -> dict:
        if not isinstance(cand, dict):
            raise CleanerError(f"candidate {idx}: must be an object")
        draft = resolve_pointer(cand, self._draft_path) if self._draft_path else cand
        if not isinstance(draft, dict):
            raise CleanerError(f"candidate {idx}: draft must be an object")
        evidence_raw = resolve_pointer(cand, self._evidence_path) if self._evidence_path else cand.get("evidence")
        if not isinstance(evidence_raw, list):
            raise CleanerError(f"candidate {idx}: evidence must be a list")

        # original candidate id / revision (pack-configured paths, kept as-is)
        try:
            candidate_id = resolve_pointer(cand, self._id_pointer)
        except ValueError as exc:
            raise CleanerError(f"candidate {idx}: id pointer {self._id_pointer}: {exc}") from exc
        if not isinstance(candidate_id, str) or not candidate_id:
            raise CleanerError(f"candidate {idx}: id must be a non-empty string")
        revision = resolve_pointer(cand, self._rev_path) if self._rev_path else 1
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise CleanerError(f"candidate {idx}: revision must be a positive int")

        if self._quote_mode:
            self._check_evidence(sources, evidence_raw)

        fact_draft = {}
        for field, spec in self._field_map().items():
            if field in self._cls_fields:
                continue
            try:
                value = resolve_pointer(draft, spec["pointer"])
            except ValueError as exc:
                raise CleanerError(f"draft.{field}: {exc}") from exc
            fact_draft[field] = _coerce_by_schema(value, spec.get("schema", {}), field)

        cls_draft = {}
        for field in self._cls_fields:
            spec = self._field_map().get(field, {})
            if not spec:
                continue
            try:
                value = resolve_pointer(draft, spec["pointer"])
            except ValueError as exc:
                raise CleanerError(f"draft.{field}: {exc}") from exc
            cls_draft[field] = _normalize_classification(
                _coerce_by_schema(value, spec.get("schema", {}), field), field,
                spec.get("schema", {}))

        unknown_fields = self._unknowns_from(draft, f"candidate {idx}")

        # machine discovery scope: candidate scope is the kind; it must be in
        # the pack allow-list. Missing scope is a hard error (never None).
        scope_kind = None
        if self._scope_path:
            try:
                scope_kind = resolve_pointer(cand, self._scope_path)
            except ValueError:
                try:
                    scope_kind = resolve_pointer(draft, self._scope_path)
                except ValueError:
                    scope_kind = None
            if scope_kind is not None and self._allowed_scope and scope_kind not in self._allowed_scope:
                raise CleanerError(f"candidate {idx}: scope {scope_kind!r} not allowed by pack {self.contract.pack_id}")
        if scope_kind is None:
            scope_kind = self._scope_default
        scope = self._scope_block(scope_kind)

        # de-duplicate evidence by (source_version_id, field, start, end)
        seen_ev = set()
        evidence_out = []
        for e in evidence_raw:
            if not isinstance(e, dict):
                raise CleanerError(f"candidate {idx}: evidence entry must be an object")
            key = (e.get(self._ev_source_key), e.get("field"), e.get("start"), e.get("end"))
            if key in seen_ev:
                continue
            seen_ev.add(key)
            ev_rev = e.get("revision")
            if ev_rev is not None and (not isinstance(ev_rev, int) or isinstance(ev_rev, bool)
                                       or ev_rev != revision):
                raise CleanerError(
                    f"candidate {idx}: evidence revision {ev_rev!r} conflicts with candidate revision {revision}")
            if "source_record_revision" in e:
                claimed_revision=e["source_record_revision"]
                if type(claimed_revision) is not int or claimed_revision!=revision:
                    raise CleanerError(f"candidate {idx}: evidence source_record_revision conflicts with candidate revision")
            entry = dict(e)
            entry.setdefault("source_record_revision", revision)
            vid = e.get(self._ev_source_key)
            src = sources.get(vid) if isinstance(vid, str) else None
            if src is not None:
                retrieved = src.get(self._retrieved_field)
                if isinstance(retrieved, str) and retrieved:
                    entry["retrieved_at"] = retrieved
                sid = src.get(self._src_id_field)
                if isinstance(sid, str) and sid:
                    entry["source_id"] = sid
                sk = src.get("source_kind")
                if isinstance(sk, str) and sk:
                    entry["source_kind"] = sk
            evidence_out.append(entry)
        if self._quote_mode:
            self._check_fact_coverage(draft, evidence_out)

        # publisher ids (distinct source_id of referenced sources) vs version ids
        publisher_ids = sorted({
            e.get("source_id") for e in evidence_out
            if isinstance(e.get("source_id"), str)
        })
        version_ids = sorted({
            e.get(self._ev_source_key) for e in evidence_out
            if isinstance(e.get(self._ev_source_key), str)
        })

        sources_out = []
        seen_src = set()
        for e in evidence_out:
            vid = e.get(self._ev_source_key)
            if not isinstance(vid, str) or vid in seen_src:
                continue
            seen_src.add(vid)
            src = sources.get(vid)
            if src is None:
                continue
            sources_out.append({
                "version_id": vid,
                "source_id": src.get(self._src_id_field),
                "url": self._source_url(src),
                "retrieved_at": src.get(self._retrieved_field),
                "canonical_body_sha256": src.get(self._hash_field),
            })

        metadata = {}
        for field,spec in self.contract.fields.get("source_contract",{}).get("candidate_metadata",{}).items():
            if not isinstance(field,str) or not isinstance(spec,dict) or not isinstance(spec.get("pointer"),str):
                raise CleanerError("candidate metadata mapping malformed")
            try: metadata[field]=resolve_pointer(cand,spec["pointer"])
            except ValueError:
                if spec.get("optional") is not True:raise CleanerError("required candidate metadata missing")
                metadata[field]=None
        validation = self._validation_block(draft, evidence_out)

        return {
            "project_id": raw_record["project_id"],
            "layer": "ods",
            "kind": "candidate",
            "payload": {
                "identity": {
                    "source_record_id": candidate_id,
                    "source_record_revision": revision,
                    "candidate_id": candidate_id,
                    "title": fact_draft.get(self._title_field),
                    "source_id": publisher_ids,
                    "source_version_ids": version_ids,
                },
                "metadata": metadata,
                "classification": cls_draft,
                "draft": fact_draft,
                "unknowns": unknown_fields,
                "sources": sources_out,
                "scope": scope,
                "validation": validation,
                "evidence": evidence_out,
                "as_of": self.options.as_of,
                "provenance": {
                    "tool": "cleaner",
                    "tool_version": self.options.tool_version,
                    "pack_id": self.contract.pack_id,
                    "pack_version": self.contract.version,
                },
            },
            "lineage": raw_record["lineage"],
        }

    # ---- internals: software (json pointer evidence) mode ----
    def _env(self, raw_record: dict, key: str):
        """Resolve RAW-envelope source metadata via pack-configured pointers
        (e.g. /source_url against the RAW record returned by Storage.read),
        falling back to the record key when the pack does not configure one.
        Never fabricates values."""
        if self._raw_env:
            ptr = self._raw_env.get(key)
            if isinstance(ptr, str) and ptr:
                try:
                    return resolve_pointer(raw_record, ptr)
                except ValueError as exc:
                    raise CleanerError(f"raw envelope {key} pointer {ptr}: {exc}") from exc
        return raw_record.get(key)

    def _clean_official(self, root: dict, raw_record: dict) -> dict:
        """Software mode: RAW payload is the official JSON; evidence is
        auto-generated from pack pointers, each bound to its own pointer and
        the real node re-resolved from the parsed root; RAW bytes hash was
        already verified in clean() (never re-serialized to fake an HTTP hash)."""
        fact_draft = {}
        evidence = []
        for field, spec in self._field_map().items():
            if field in self._cls_fields:
                continue
            try:
                value = resolve_pointer(root, spec["pointer"])
            except ValueError as exc:
                raise CleanerError(f"draft.{field}: {exc}") from exc
            coerced = _coerce_by_schema(value, spec.get("schema", {}), field)
            fact_draft[field] = coerced
            if coerced not in (None, "", [], {}):
                evidence.append({"field": field, "pointer": spec["pointer"],
                                 "value": coerced})
        if not evidence:
            raise CleanerError("official payload has no pointer-backed fact fields")
        for e in evidence:
            node = resolve_pointer(root, e["pointer"])
            if node != e["value"]:
                raise CleanerError(f"pointer {e['pointer']} does not resolve to its evidence value")
        rid = self._env(raw_record, "record_id")
        source_url = self._env(raw_record, "source_url")
        retrieved_at = self._env(raw_record, "captured_at")
        content_hash = self._env(raw_record, "content_hash")
        source_id = None
        if self._source_id_mode == "from_source_url":
            source_id = source_url if isinstance(source_url, str) and source_url else None
        elif self._publisher_source_id:
            source_id = self._publisher_source_id
        if isinstance(retrieved_at, str) and retrieved_at:
            iso_date(retrieved_at, "source.retrieved_at")
        version_ids = [rid] if isinstance(rid, str) and rid else []
        sources = [{
            "version_id": rid,
            "source_id": source_id,
            "url": source_url,
            "retrieved_at": retrieved_at,
            "canonical_body_sha256": content_hash,
        }] if version_ids else []
        validation = self._validation_block(fact_draft, evidence)
        return {
            "project_id": raw_record["project_id"],
            "layer": "ods",
            "kind": "candidate",
            "payload": {
                "identity": {
                    "source_record_id": rid or "latest",
                    "source_record_revision": 1,
                    "candidate_id": rid or "latest",
                    "title": fact_draft.get(self._title_field),
                    "source_id": [source_id] if source_id else [],
                    "source_version_ids": version_ids,
                },
                "classification": {},
                "draft": fact_draft,
                "unknowns": self._unknowns_from(root, "official payload"),
                "sources": sources,
                "scope": self._scope_block(self._scope_default),
                "validation": validation,
                "evidence": evidence,
                "as_of": self.options.as_of,
                "provenance": {
                    "tool": "cleaner",
                    "tool_version": self.options.tool_version,
                    "pack_id": self.contract.pack_id,
                    "pack_version": self.contract.version,
                },
            },
            "lineage": raw_record["lineage"],
        }

    # ---- internals: shared ----
    def _validation_block(self, draft: dict, evidence: list[dict]) -> dict:
        covered = set()
        for e in evidence:
            f = e.get("field") if isinstance(e, dict) else None
            if isinstance(f, str):
                covered.add(f)
        field_map = self._field_map()
        fact_pointers = {f: field_map[f]["pointer"] for f in self._fact_fields if f in field_map}
        cls_pointers = {f: field_map[f]["pointer"] for f in self._cls_fields if f in field_map}
        coverage_ok = all(
            draft.get(f) in (None, "", [], {}) or f in covered
            for f in self._fact_fields)
        classification_ok = True  # enum failures already raised while cleaning
        block = {
            "coverage_ok": bool(coverage_ok),
            "hash_ok": True,       # raw bytes hash verified in clean()/consumption
            "classification_ok": bool(classification_ok),
            "fact_fields": sorted(self._fact_fields),
            "classification_fields": sorted(self._cls_fields),
            "fact_field_pointers": fact_pointers,
            "classification_field_pointers": cls_pointers,
            "raw_hash_scope": self._raw_hash_scope,
            "raw_retained": self._raw_retained,
        }
        if self._quote_mode:
            block["quote_ok"] = True   # exact Unicode slices verified in _check_evidence
        else:
            block["pointer_ok"] = True  # pointers re-resolved in _clean_official
        return block

    def _field_map(self) -> dict:
        """Fact + classification fields only (evidence_fields ∪
        classification.fields). Unknown fields are read separately and never
        enter the fact draft."""
        wanted = self._fact_fields | self._cls_fields
        out = {}
        mapping = self.contract.fields.get("mapping", {})
        for key, spec in mapping.items():
            if key.startswith("source_") or key.startswith("evidence_"):
                continue
            if not isinstance(spec, dict) or "field" not in spec or "pointer" not in spec:
                raise CleanerError(f"pack {self.contract.pack_id}: bad field mapping {key}")
            if spec["field"] not in wanted:
                continue
            schema_ref=spec.get("schema_ref") or spec["pointer"]
            if schema_ref not in self._pointers or not isinstance(self._pointers[schema_ref],dict):
                raise CleanerError("field schema reference missing: "+str(schema_ref))
            if spec["field"] in out:raise CleanerError("duplicate field mapping")
            out[spec["field"]] = {"pointer":spec["pointer"],"schema":self._pointers[schema_ref]}
        if set(out)!=wanted:raise CleanerError("fact/classification field mapping incomplete")
        return out

    def _unknown_fields_specs(self) -> dict:
        """Fields the pack declares unknown-able; kept verbatim from the draft,
        never coerced, never treated as verified facts. Missing optional fields
        resolve to the pack default ("unknown"); missing required ones fail."""
        out = {}
        mapping = self.contract.fields.get("mapping", {})
        for key, spec in mapping.items():
            if not isinstance(spec, dict) or "field" not in spec or "pointer" not in spec:
                continue
            if spec["field"] in (self._fact_fields | self._cls_fields):
                continue
            out[spec["field"]] = {
                "pointer": spec["pointer"],
                "optional": bool(spec.get("optional", False)),
                "default": spec.get("default", self._unknown_default),
            }
        return out

    # ---- internals: evidence verification (cuisines) ----
    def _check_evidence(self, sources: dict[str, dict],
                        evidence: list[dict]) -> None:
        for e in evidence:
            vid = e.get(self._ev_source_key)
            if not isinstance(vid, str) or not vid:
                raise CleanerError("evidence entry missing source_version_id")
            src = sources.get(vid)
            if src is None:
                raise CleanerError(f"evidence references unknown source_version_id {vid!r}")
            body = src.get(self._body_field)
            if not isinstance(body, str):
                raise CleanerError("source canonical_body must be a string")
            start = e.get("start")
            end = e.get("end")
            quote = e.get("quote")
            if not isinstance(start, int) or isinstance(start, bool) or start < 0:
                raise CleanerError("evidence start must be a non-negative int")
            if not isinstance(end, int) or isinstance(end, bool) or end <= start:
                raise CleanerError("evidence end must be an int > start")
            if not isinstance(quote, str) or len(quote) > self.options.max_quote_len:
                raise CleanerError("evidence quote must be a bounded string")
            try:
                unicode_quote_check(body, start, end, quote)
            except ValidatorError as exc:
                raise CleanerError(str(exc)) from exc

    def _check_source_bytes(self, sources: dict[str, dict]) -> None:
        for vid, src in sources.items():
            body = src.get(self._body_field)
            if not isinstance(body, str):
                raise CleanerError(f"source {vid}: canonical_body must be a string")
            declared = src.get(self._hash_field)
            if not isinstance(declared, str):
                raise CleanerError(f"source {vid}: canonical_body_sha256 missing")
            try:
                canonical_hash_check(body, declared, label=f"source {vid}")
            except ValidatorError as exc:
                raise CleanerError(str(exc)) from exc
            retrieved = src.get(self._retrieved_field)
            if isinstance(retrieved, str) and retrieved:
                iso_date(retrieved, "source.retrieved_at")

    def _check_fact_coverage(self, draft: dict, evidence: list[dict]) -> None:
        covered = set()
        for e in evidence:
            f = e.get("field") if isinstance(e, dict) else None
            if isinstance(f, str):
                covered.add(f)
        for field in self._fact_fields:
            value = draft.get(field)
            if value in (None, "", [], {}):
                continue
            if field not in covered:
                raise CleanerError(f"nonempty fact field {field!r} lacks evidence coverage")
