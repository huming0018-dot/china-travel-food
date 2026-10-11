"""P2-REPAIR-03 self-verification: M2 Cleaner bytes-first + pack 0.3.2 + factory.

Runs standalone (`python tests/test_p2_repair03_cleaner.py`) or under pytest.
Covers the REPAIR-03 contract:
- RAW payload consumed as the exact stored BYTES; SHA256 must equal
  content_hash and source_hash BEFORE parsing; strict JSON (no duplicate keys,
  no NaN/Infinity); dict fixtures must match their canonical stored hash.
- identity gains source_record_id; source_id = distinct publisher ids;
  source_version_ids = version ids; `sources` deduplicated metadata without
  bodies; validation strict booleans + fact/classification field pointers +
  raw_hash_scope/raw_retained.
- Conflicts rejected; optional unknown fields -> "unknown"; enum/minimum/
  maxItems/unknown-type/strict bool-int/False!=0 enforced; pointer evidence
  binds field pointer to real node; scope allow-list.
- storage_factory: sqlite existing-symlink/../absolute refused; PG env NAME
  + ctfs_ namespace enforced.
"""
from __future__ import annotations
from toolbox import __version__

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from toolbox.cleaner import Cleaner, CleanerError  # noqa: E402
from toolbox.ontology import OntologyManager  # noqa: E402
from toolbox.pack_schema import load_pack  # noqa: E402
from toolbox.storage import SqliteStorage, StorageError  # noqa: E402
from toolbox.storage_factory import make_storage  # noqa: E402

PACK_ROOT = pathlib.Path(__file__).resolve().parents[1] / "packs"
PASS = 0


def ok(name: str):
    global PASS
    PASS += 1
    print(f"ok {PASS:>3} {name}")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def make_store():
    root = pathlib.Path(tempfile.mkdtemp(prefix="ctfs-repair03-store-"))
    mgr = OntologyManager(root)
    mgr.install(PACK_ROOT / "cuisines" / "0.3.2")
    mgr.install(PACK_ROOT / "software-releases" / "0.3.2")
    return root


def raw_record(payload, project: str = "shanghai-c3", rid: str = "raw-1",
               url: str = "https://example.org/source", captured: str = "2026-10-11T06:56:59Z",
               content_hash=None, source_hash=None):
    if content_hash is None:
        content_hash = sha(payload) if isinstance(payload, (bytes, str)) else sha(json_bytes(payload))
    if source_hash is None:
        source_hash = content_hash
    lineage = {
        "project": project, "source_url": url, "source_hash": source_hash,
        "batch": "b1", "captured_at": captured, "steps": [], "tool_versions": [],
    }
    return {
        "record_id": rid, "project_id": project, "layer": "raw",
        "payload": payload, "content_hash": content_hash, "source_hash": source_hash,
        "source_url": url, "batch": "b1", "captured_at": captured, "lineage": lineage,
    }


def make_bundle() -> dict:
    body1 = "Atelier 玖樓 is a quiet venue where 七月柿 Farm House serves produce and Leyas opens late."
    body2 = "A second report describes the same quiet venue in more detail across several paragraphs."
    body3 = "Third independent editorial source confirms the venue and the farm-house dishes."
    srcs = [
        {"version_id": "s001-v1", "source_id": "s001", "source_kind": "ugc",
         "canonical_body": body1,
         "canonical_body_sha256": sha(body1.encode("utf-8")),
         "retrieved_at": "2026-10-11T06:56:59Z", "url": "https://a.example/post/1"},
        {"version_id": "s002-v1", "source_id": "s002", "source_kind": "media-roundup",
         "canonical_body": body2,
         "canonical_body_sha256": sha(body2.encode("utf-8")),
         "retrieved_at": "2026-10-10T08:00:00Z"},
        {"version_id": "s003-v1", "source_id": "s003", "source_kind": "official-guide",
         "canonical_body": body3,
         "canonical_body_sha256": sha(body3.encode("utf-8")),
         "retrieved_at": "2026-10-09T09:00:00Z"},
    ]
    q1 = "Atelier 玖樓 is a quiet venue"
    s1 = body1.index(q1)
    q2 = "quiet venue in more detail"
    s2 = body2.index(q2)
    q3 = "confirms the venue"
    s3 = body3.index(q3)
    q4 = "in more detail across several paragraphs"
    s4 = body2.index(q4)
    q5 = "serves produce"
    s5 = body1.index(q5)
    c1 = {
        "id": "c1", "revision": 1, "scope": "discovery_candidate",
        "draft": {"title": "Atelier 玖樓", "summary": "quiet venue",
                  "subject_name": "Atelier 玖樓", "feature_keys": ["quiet", "venue"],
                  "entity_type": "venue"},
        "evidence": [
            {"source_version_id": "s001-v1", "field": "title", "start": s1, "end": s1 + len(q1), "quote": q1, "revision": 1},
            {"source_version_id": "s002-v1", "field": "summary", "start": s2, "end": s2 + len(q2), "quote": q2, "revision": 1},
            {"source_version_id": "s003-v1", "field": "subject_name", "start": s3, "end": s3 + len(q3), "quote": q3, "revision": 1},
            {"source_version_id": "s002-v1", "field": "feature_keys", "start": s4, "end": s4 + len(q4), "quote": q4, "revision": 1},
        ],
    }
    c2 = {
        "id": "c2", "revision": 2, "scope": "private_lead",
        "draft": {"title": "七月柿 Farm House", "summary": "serves produce",
                  "subject_name": "七月柿", "feature_keys": ["produce"],
                  "entity_type": "item"},
        "evidence": [
            {"source_version_id": "s001-v1", "field": "title", "start": body1.index("七月柿"), "end": body1.index("七月柿") + len("七月柿"), "quote": "七月柿", "revision": 2},
            {"source_version_id": "s001-v1", "field": "subject_name", "start": body1.index("七月柿"), "end": body1.index("七月柿") + len("七月柿"), "quote": "七月柿", "revision": 2},
            {"source_version_id": "s001-v1", "field": "summary", "start": s5, "end": s5 + len(q5), "quote": q5, "revision": 2},
            {"source_version_id": "s001-v1", "field": "feature_keys", "start": body1.index("produce"), "end": body1.index("produce") + len("produce"), "quote": "produce", "revision": 2},
        ],
    }
    return {"source_versions": srcs, "candidates": [c1, c2]}


def test_bytes_positive():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    raw = raw_record(json_bytes(bundle))
    records = Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version="0.4.0-repair03").clean(raw)
    assert len(records) == 2, len(records)
    p1 = records[0]["payload"]
    assert p1["identity"]["source_record_id"] == "c1"
    assert p1["identity"]["source_record_revision"] == 1
    assert p1["identity"]["candidate_id"] == "c1"
    assert p1["identity"]["title"] == "Atelier 玖樓"
    assert p1["identity"]["source_id"] == ["s001", "s002", "s003"], p1["identity"]
    assert p1["identity"]["source_version_ids"] == ["s001-v1", "s002-v1", "s003-v1"]
    assert p1["scope"]["kind"] == "discovery_candidate"
    assert p1["scope"]["evidence_semantics"]["independent_sources"] == "distinct_source_id"
    assert p1["scope"]["raw_hash_scope"] == "snapshot_file_bytes"
    assert p1["scope"]["original_http_retained"] is False
    assert p1["unknowns"]["hours"] == "unknown"
    assert p1["unknowns"]["published_at"] == "unknown"
    assert p1["unknowns"]["taste"] == "unknown"
    src = p1["sources"]
    assert len(src) == 3
    by_vid = {s["version_id"]: s for s in src}
    assert by_vid["s001-v1"]["url"] == "https://a.example/post/1"
    assert by_vid["s002-v1"]["url"] is None  # never fabricated
    assert by_vid["s001-v1"]["canonical_body_sha256"] == sha(make_bundle()["source_versions"][0]["canonical_body"].encode())
    assert "canonical_body" not in by_vid["s001-v1"]
    v = p1["validation"]
    assert v["coverage_ok"] is True and v["quote_ok"] is True and v["hash_ok"] is True
    assert v["classification_ok"] is True
    assert sorted(v["fact_fields"]) == ["feature_keys", "subject_name", "summary", "title"]
    assert v["classification_fields"] == ["entity_type"]
    assert v["fact_field_pointers"]["title"] == "/title"
    assert v["raw_hash_scope"] == "snapshot_file_bytes"
    assert v["raw_retained"] is False
    p2 = records[1]["payload"]
    assert p2["identity"]["source_record_revision"] == 2
    assert p2["identity"]["source_id"] == ["s001"]
    assert p2["unknowns"]["hours"] == "unknown"
    ok("bytes-positive cuisines: identity/sources/validation/unknowns/scope")


def test_dict_fixture_hash():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    raw = raw_record(bundle)  # dict payload; canonical hash must match
    records = Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    assert len(records) == 2
    ok("dict-fixture: canonical stored hash matches")


def test_hash_mismatch():
    store = make_store()
    contract = load_pack(store, "cuisines")
    raw = raw_record(json_bytes(make_bundle()))
    raw["content_hash"] = "0" * 64
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("hash-mismatch rejected")
        return
    raise AssertionError("hash mismatch was not rejected")


def test_dup_key_rejected():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    text = json.dumps(bundle, ensure_ascii=False, sort_keys=True).replace(
        '"id": "c1"', '"id": "c1", "id": "c1x"', 1)
    raw = raw_record(text.encode("utf-8"))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError as exc:
        assert "duplicate JSON key" in str(exc), exc
        ok("duplicate-key rejected")
        return
    raise AssertionError("duplicate key was not rejected")


def test_nan_inf_rejected():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    text = json.dumps(bundle, ensure_ascii=False, sort_keys=True).replace(
        '"entity_type": "venue"', '"entity_type": NaN', 1)
    raw = raw_record(text.encode("utf-8"))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError as exc:
        assert "non-finite" in str(exc) or "duplicate" in str(exc), exc
        ok("NaN rejected")
        return
    raise AssertionError("NaN was not rejected")


def test_bad_quote_rejected():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["evidence"][0]["quote"] = "wrong quote text"
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("bad-quote rejected")
        return
    raise AssertionError("bad quote was not rejected")


def test_duplicate_candidate_id():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][1]["id"] = "c1"
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError as exc:
        assert "duplicate candidate id" in str(exc), exc
        ok("duplicate-candidate-id rejected")
        return
    raise AssertionError("duplicate candidate id was not rejected")


def test_duplicate_version_id_conflict():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    dup = dict(bundle["source_versions"][0])
    dup["canonical_body"] = dup["canonical_body"] + " CHANGED"
    bundle["source_versions"].append(dup)
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError as exc:
        assert "duplicate source version_id" in str(exc), exc
        ok("duplicate-version-id-conflict rejected")
        return
    raise AssertionError("duplicate version_id with different content was not rejected")


def test_evidence_revision_conflict():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["evidence"][0]["revision"] = 2
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError as exc:
        assert "revision" in str(exc), exc
        ok("evidence-revision conflict rejected")
        return
    raise AssertionError("evidence revision conflict was not rejected")


def test_missing_required_field():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    del bundle["candidates"][0]["draft"]["title"]
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("missing-required-field rejected")
        return
    raise AssertionError("missing required fact field was not rejected")


def test_enum_violation():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["draft"]["entity_type"] = "not-a-venue"
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("enum violation rejected")
        return
    raise AssertionError("enum violation was not rejected")


def test_minimum_revision():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["revision"] = 0
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("minimum(revision) rejected")
        return
    raise AssertionError("revision 0 was not rejected")


def test_maxitems_violation():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["draft"]["feature_keys"] = [f"k{i}" for i in range(41)]
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("maxItems violation rejected")
        return
    raise AssertionError("maxItems violation was not rejected")


def test_unknown_type_rejected():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["draft"]["feature_keys"] = [1]
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("unknown item type rejected")
        return
    raise AssertionError("int item in string array was not rejected")


def test_bool_int_strict():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["revision"] = True
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("strict bool!=int rejected")
        return
    raise AssertionError("bool revision was not rejected")


def test_false_not_zero():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["draft"]["feature_keys"] = [False]
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("False not coerced to string rejected")
        return
    raise AssertionError("bool item was not rejected")


def test_scope_not_allowed():
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["scope"] = "paid_promotion"
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError as exc:
        assert "scope" in str(exc), exc
        ok("scope not in allow-list rejected")
        return
    raise AssertionError("disallowed scope was not rejected")


def test_software_official():
    store = make_store()
    contract = load_pack(store, "software-releases")
    sw = {"name": "codex", "tag_name": "v0.12.0",
          "published_at": "2026-10-01T00:00:00Z",
          "html_url": "https://github.com/openai/codex/releases/tag/v0.12.0",
          "assets": []}
    raw = raw_record(json_bytes(sw), project="official-release-watch",
                     rid="raw-codex",
                     url="https://api.github.com/repos/openai/codex/releases/latest",
                     captured="2026-10-12T01:00:00Z")
    records = Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    assert len(records) == 1
    p = records[0]["payload"]
    assert p["identity"]["source_record_id"] == "raw-codex"
    assert p["identity"]["source_record_revision"] == 1
    assert p["identity"]["title"] == "codex"
    assert p["identity"]["source_id"] == ["https://api.github.com/repos/openai/codex/releases/latest"]
    assert p["identity"]["source_version_ids"] == ["raw-codex"]
    assert p["sources"][0]["source_id"] == "https://api.github.com/repos/openai/codex/releases/latest"
    assert p["sources"][0]["url"] == "https://api.github.com/repos/openai/codex/releases/latest"
    assert p["sources"][0]["retrieved_at"] == "2026-10-12T01:00:00Z"
    assert p["sources"][0]["canonical_body_sha256"] == raw["content_hash"]
    v = p["validation"]
    assert v["pointer_ok"] is True and v["coverage_ok"] is True and v["hash_ok"] is True
    assert v["raw_hash_scope"] == "http_response_bytes" and v["raw_retained"] is True
    assert "quote_ok" not in v
    assert p["draft"]["name"] == "codex"
    assert p["scope"]["kind"] == "official_release"
    assert p["scope"]["evidence_semantics"]["independent_sources"] == "single_official_publisher"
    assert p["scope"]["raw_hash_scope"] == "http_response_bytes"
    assert p["scope"]["original_http_retained"] is True
    # pack-declared unknown fields are extracted, never an empty "all known"
    assert p["unknowns"]["compatibility"] == "unknown"
    assert p["unknowns"]["security_assessment"] == "unknown"
    ok("software-official: pointer evidence, identity, sources, validation")


def test_software_bad_type():
    store = make_store()
    contract = load_pack(store, "software-releases")
    sw = {"name": "n8n", "tag_name": 123,
          "published_at": "2026-10-01T00:00:00Z",
          "html_url": "https://github.com/n8n-io/n8n/releases/tag/v1"}
    raw = raw_record(json_bytes(sw), project="official-release-watch", rid="raw-n8n")
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        ok("software bad type rejected")
        return
    raise AssertionError("software int tag_name was not rejected")


def test_software_bytes_hash_scope():
    store = make_store()
    contract = load_pack(store, "software-releases")
    sw = {"name": "n8n", "tag_name": "v1.0.0",
          "published_at": "2026-10-02T00:00:00Z",
          "html_url": "https://github.com/n8n-io/n8n/releases/tag/v1.0.0"}
    raw = raw_record(json_bytes(sw), project="official-release-watch", rid="raw-n8n")
    records = Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    p = records[0]["payload"]
    # hash_ok must come from the ACTUAL bytes, never a re-serialized hash
    assert p["validation"]["hash_ok"] is True
    ok("software bytes hash verified (no re-serialization)")


def test_software_no_fabricated_source_id():
    """Missing RAW source_url yields empty source_id, never a fabricated
    'official' id, and body published_at is not used as collection time."""
    store = make_store()
    contract = load_pack(store, "software-releases")
    sw = {"name": "n8n", "tag_name": "v1.1.0",
          "published_at": "2026-10-03T00:00:00Z",
          "html_url": "https://github.com/n8n-io/n8n/releases/tag/v1.1.0"}
    raw = raw_record(json_bytes(sw), project="official-release-watch",
                     rid="raw-n8n", url=None, captured="2026-10-12T02:00:00Z")
    records = Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    p = records[0]["payload"]
    assert p["identity"]["source_id"] == [], p["identity"]["source_id"]
    assert p["sources"][0]["source_id"] is None
    assert p["sources"][0]["retrieved_at"] == "2026-10-12T02:00:00Z"
    # never a fabricated "official" publisher id (scope kind "official_release"
    # is a separate pack default and is legitimate)
    assert p["identity"]["source_id"] != ["official"]
    assert all(s.get("source_id") != "official" for s in p["sources"])
    ok("software missing source_url: no fabricated source id")


def test_candidate_missing_scope_rejected():
    """A candidate without a scope cannot produce a None scope: M3 requires
    payload.scope to be a dict, so a missing candidate scope is a hard error
    when the pack has no default."""
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0].pop("scope", None)
    contract.validation["machine_scope"].pop("default",None)
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
        raise AssertionError("missing candidate scope was not rejected")
    except CleanerError:
        pass
    ok("missing candidate scope rejected (scope never None)")


def test_factory_sqlite_escape():
    proj = pathlib.Path(tempfile.mkdtemp(prefix="ctfs-repair03-proj-"))
    for rel in ("../evil.db", "/abs/db.sqlite", "a/../../b.sqlite"):
        try:
            make_storage({"storage": {"backend": "sqlite", "path": rel}}, proj)
        except StorageError:
            pass
        else:
            raise AssertionError(f"sqlite path {rel!r} was not rejected")
    ok("factory sqlite ../ and absolute rejected")


def test_factory_sqlite_existing_symlink():
    proj = pathlib.Path(tempfile.mkdtemp(prefix="ctfs-repair03-proj-"))
    outside = proj.parent / "outside-target.sqlite"
    outside.write_bytes(b"")
    link = proj / "db-link.sqlite"
    link.symlink_to(outside)
    try:
        make_storage({"storage": {"backend": "sqlite", "path": "db-link.sqlite"}}, proj)
    except StorageError:
        ok("factory sqlite existing symlink rejected")
        return
    raise AssertionError("existing symlink at db path was not rejected")


def test_factory_pg_env_name_and_namespace():
    proj = pathlib.Path(tempfile.mkdtemp(prefix="ctfs-repair03-proj-"))
    try:
        make_storage({"storage": {"backend": "postgres",
                                  "postgres": {"dsn_env": "bad-name", "schema": "ctfs_x"}}}, proj)
    except StorageError:
        pass
    else:
        raise AssertionError("invalid dsn_env name was not rejected")
    try:
        make_storage({"storage": {"backend": "postgres",
                                  "postgres": {"dsn_env": "CTFS_DSN", "schema": "public"}}}, proj)
    except StorageError:
        pass
    else:
        raise AssertionError("non-ctfs schema was not rejected")
    try:
        make_storage({"storage": {"backend": "postgres",
                                  "postgres": {"dsn_env": "CTFS_DSN_UNSET", "schema": "ctfs_pilot"}}}, proj)
    except StorageError as exc:
        assert "not set" in str(exc), exc
    else:
        raise AssertionError("missing DSN env was not rejected")
    ok("factory pg env NAME + ctfs_ namespace enforced")


def test_storage_roundtrip_bytes():
    """End-to-end with the REAL storage: write RAW bytes -> read -> clean."""
    store = make_store()
    contract = load_pack(store, "cuisines")
    db = pathlib.Path(tempfile.mkdtemp(prefix="ctfs-repair03-db-")) / "pilot.sqlite"
    st = SqliteStorage(db)
    bundle = make_bundle()
    payload_bytes = json_bytes(bundle)
    lineage = {
        "project": "shanghai-c3", "source_url": "https://example.org/bundle.json",
        "source_hash": sha(payload_bytes), "batch": "b1",
        "captured_at": "2026-10-11T06:56:59Z", "steps": [], "tool_versions": [],
    }
    rid = st.write_raw("shanghai-c3", {
        "schemaVersion": "0.2.0", "project_id": "shanghai-c3", "layer": "RAW",
        "payload": payload_bytes,
        "source_url": "https://example.org/bundle.json",
        "source_hash": sha(payload_bytes), "batch": "b1",
        "captured_at": "2026-10-11T06:56:59Z", "lineage": lineage,
    })
    raw = st.read("shanghai-c3", "RAW", rid)
    assert isinstance(raw["payload"], bytes), type(raw["payload"])
    records = Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    assert len(records) == 2
    assert records[0]["payload"]["validation"]["hash_ok"] is True
    st.close()
    ok("storage roundtrip: RAW bytes read back and cleaned with hash_ok")


def test_declared_string_value_list_rejected():
    """Declared schema type is authoritative: string field with a list value is rejected."""
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["draft"]["summary"] = ["quiet", "venue"]
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
        raise AssertionError("declared string field accepted a list value")
    except CleanerError:
        pass
    ok("declared string field rejects list value")


def test_declared_array_value_dict_rejected():
    """Declared array field with a dict value is rejected (not silently recursed)."""
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["draft"]["feature_keys"] = {"quiet": True}
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
        raise AssertionError("declared array field accepted a dict value")
    except CleanerError:
        pass
    ok("declared array field rejects dict value")


def test_unknown_schema_type_rejected():
    """Unknown declared schema types are rejected, not silently tolerated."""
    store = make_store()
    contract = load_pack(store, "cuisines")
    bundle = make_bundle()
    bundle["candidates"][0]["draft"]["summary"] = "quiet venue"
    bundle["candidates"][0]["draft"]["entity_type"] = "venue"
    raw = raw_record(json_bytes(bundle))
    try:
        Cleaner(contract, as_of="2026-10-12T00:00:00Z", tool_version=__version__).clean(raw)
    except CleanerError:
        pass
    # mutation of pointers requires a pack copy; verify at schema level directly
    from toolbox.cleaner import _coerce_by_schema
    try:
        _coerce_by_schema("x", {"type": "banana"}, "probe")
        raise AssertionError("unknown schema type accepted")
    except CleanerError:
        pass
    ok("unknown schema type rejected")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nP2-REPAIR-03 self-verification: {PASS} checks passed, 0 failed")


if __name__ == "__main__":
    main()
