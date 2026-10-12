"""P2 gate tests: Cleaner / Scorer / Auditor / storage factory.

Positive: shanghai-shape bundle matching the ORIGINAL semantic-bundle
contract (source_versions is a LIST; evidence joins by source_version_id;
6 candidates / 25 refs / 3 sources / Akanee revision 2), software official
JSON (raw payload IS the GitHub JSON; evidence auto-generated from pointers),
auditor recompute pass against the real storage chain.
Negative (TASK-P2 + P2-EARLY-FINDINGS): fake quote, bool offsets, body hash
wrong, unknown source_version_id, field without evidence, fake score alone,
fake pass alone, stale audit config mismatch, duplicate identity,
cross-project parent, unknown scoring operator, NaN, same-source quote
duplication must not inflate source/ref counts.
"""
import hashlib
import json
import pathlib
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO / "toolbox"))
sys.path.insert(0, str(REPO))

from toolbox.ontology import OntologyManager, PackError  # noqa: E402
from toolbox.pack_schema import load_pack  # noqa: E402
from toolbox.cleaner import Cleaner, CleanerError  # noqa: E402
from toolbox.scorer import Scorer, ScorerError  # noqa: E402
from toolbox.auditor import Auditor  # noqa: E402
from toolbox.storage_factory import make_storage  # noqa: E402
from toolbox.storage import SqliteStorage, StorageError  # noqa: E402
from toolbox.manifest import Manifest, ManifestError  # noqa: E402
from toolbox.writer import append  # noqa: E402
from toolbox.schema import validate_against, SchemaError  # noqa: E402

import yaml  # noqa: E402

from toolbox import __version__
from toolbox.stages import Stages
TOOL = __version__
AS_OF = "2026-10-12T00:00:00Z"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def payload_sha(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def install_packs(store, pack_id):
    mgr = OntologyManager(store)
    src = REPO / "packs" / pack_id / "0.3.2"
    mgr.install(src)
    return load_pack(store, pack_id)


def bundle_ok():
    """Original bundle shape: source_versions LIST + evidence.source_version_id.

    = 6 candidates / 25 refs / 3 distinct sources; Akanee (first) rev 2,
    others rev 1; duplicates 0.
    """
    body_a = "上海新店 Atelier 玖樓 七月柿 主厨 三道 菜单 平价 手作。"
    body_b = "七月柿 Farm House 主打 时令 蔬菜 慢火 料理 好评。"
    body_c = "Leyas 新店 开业 通知 附 菜单 价格 未知。"
    sources = [
        {"version_id": "s001-v1", "source_id": "s001", "source_kind": "media-opening-news",
         "canonical_body": body_a, "canonical_body_sha256": sha(body_a),
         "retrieved_at": "2026-10-11T06:56:59Z"},
        {"version_id": "s003-v1", "source_id": "s003", "source_kind": "media-roundup",
         "canonical_body": body_b, "canonical_body_sha256": sha(body_b),
         "retrieved_at": "2026-10-11T07:00:00Z"},
        {"version_id": "s007-v1", "source_id": "s007", "source_kind": "media-opening-news",
         "canonical_body": body_c, "canonical_body_sha256": sha(body_c),
         "retrieved_at": "2026-10-11T14:57:50Z"},
    ]
    i_chef = body_a.index("主厨")
    cand = []
    for i in range(6):
        revision = 2 if i == 0 else 1  # Akanee has a revision-2 second summary
        ev = [
            {"source_version_id": "s001-v1", "start": i_chef,
             "end": i_chef + 2, "quote": body_a[i_chef:i_chef + 2], "field": "title"},
            {"source_version_id": "s003-v1", "start": 0, "end": 5,
             "quote": body_b[:5], "field": "summary"},
            {"source_version_id": "s003-v1", "start": 0, "end": 5,
             "quote": body_b[:5], "field": "subject_name"},
            {"source_version_id": "s007-v1", "start": 0, "end": 4,
             "quote": body_c[:4], "field": "feature_keys"},
        ]
        if revision == 2:
            # Akanee: second summary slice from the same source -> one more ref
            ev.insert(1, {"source_version_id": "s003-v1", "start": 6, "end": 11,
                          "quote": body_b[6:11], "field": "summary"})
        cand.append({
            "id": f"candidate-{i}",
            "revision": revision,
            "draft": {"title": f"店{i+1}", "summary": f"关于店{i+1}的简报",
                      "entity_type": "venue",
                      "subject_name": "Atelier 玖樓", "feature_keys": ["时令"],
                      "published_at": "2026-10-11T00:00:00Z",
                      "hours": None, "menu": None, "price": None,
                      "business_relation": None, "taste": None},
            "evidence": ev,
        })
    return {"candidates": cand, "source_versions": sources}


def manifest_of(project_id="p", backend="sqlite"):
    path = pathlib.Path(tempfile.mkdtemp(prefix="p2-mf-")) / "manifest.yaml"
    data = {
        "schemaVersion": "0.4.0",
        "project": {"project_id": project_id, "name": project_id, "domain": "test",
                    "region": "test"},
        "storage": {"backend": backend, "path": "data/store.sqlite"},
        "crawler": {"connector": "snapshot-file", "timeout_seconds": 30.0,
                    "max_requests": 8, "max_bytes": 8000000,
                    "per_request_max_bytes": 1000000},
        "ontology": {"packs": ["cuisines"]},
        "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                      for k in ("raw", "clean", "scored", "audit")},
        "raw": {"sources": [{"source_id":"fixture", "kind":"json", "url":"snapshot://fixture", "connector":"snapshot-file"}, {"source_id":"official", "kind":"json", "url":"https://api.github.com/repos/openai/codex/releases/latest", "connector":"http-public"}]},
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return Manifest.load(path)


def _write_raw(storage, project_id, payload, source_url="snapshot://fixture", batch="b"):
    ph = payload_sha(payload)
    record = {
        "schemaVersion": "0.2.0",
        "project_id": project_id,
        "layer": "RAW",
        "payload": payload,
        "source_url": source_url,
        "source_hash": ph,
        "batch": batch,
        "captured_at": AS_OF,
        "lineage": {"project": project_id, "source_url": source_url,
                    "source_hash": ph, "batch": batch, "captured_at": AS_OF,
                    "steps": ["acquire"], "tool_versions": [TOOL]},
    }
    return storage.write_raw(project_id, record)


def _ods_to_dw(storage, manifest, contract, raw_id, tool=TOOL):
    if tool != TOOL: raise ValueError("test must use actual tool")
    stages=Stages(manifest,contract,storage,AS_OF)
    return [stages.score(row["record_id"],row["version"])["record_id"] for row in stages.clean(raw_id)]


def _fixture_raw(payload):
    # Strict bytes API; negative NaN fixture reaches the real strict JSON parser.
    blob=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=True).encode()
    h=hashlib.sha256(blob).hexdigest()
    return {"project_id":"p","record_id":"fixture-raw","payload":blob,"content_hash":h,"source_hash":h,
        "source_url":"snapshot://fixture","captured_at":AS_OF,
        "lineage":{"project":"p","source_url":"snapshot://fixture","source_hash":h,"batch":"b","captured_at":AS_OF}}


class PackTest(unittest.TestCase):
    def setUp(self):
        self.store = pathlib.Path(tempfile.mkdtemp(prefix="p2-pack-"))
        self.contract = install_packs(self.store, "cuisines")

    def test_cleaner_shanghai_shape(self):
        raw = _fixture_raw(bundle_ok())
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        self.assertEqual(len(recs), 6)
        revs = [r["payload"]["identity"]["source_record_revision"] for r in recs]
        self.assertEqual(revs[0], 2)          # Akanee
        self.assertEqual(set(revs[1:]), {1})
        self.assertEqual(len({json.dumps(r["payload"]["identity"], sort_keys=True)
                              for r in recs}), 6)  # duplicates=0
        refs = [len(r["payload"]["evidence"]) for r in recs]
        self.assertEqual(sum(refs), 25)        # 25 refs
        self.assertEqual(refs[0], 5)
        self.assertEqual(set(refs[1:]), {4})
        self.assertEqual(len(recs[0]["payload"]["identity"]["source_id"]), 3)

    def test_cleaner_same_source_quotes_do_not_inflate_sources(self):
        # a second identical quote from the same source_version_id is dropped
        b = bundle_ok()
        b["candidates"][1]["evidence"].append(
            {"source_version_id": "s003-v1", "start": 0, "end": 5,
             "quote": b["source_versions"][1]["canonical_body"][:5],
             "field": "summary"})
        raw = _fixture_raw(b)
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        self.assertEqual(len(recs[1]["payload"]["evidence"]), 4)
        self.assertEqual(len(recs[1]["payload"]["identity"]["source_id"]), 3)

    def test_cleaner_fake_quote(self):
        b = bundle_ok()
        b["candidates"][0]["evidence"][0]["quote"] = "假quote"
        raw = _fixture_raw(b)
        with self.assertRaises(CleanerError):
            Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)

    def test_cleaner_bool_offsets(self):
        b = bundle_ok()
        b["candidates"][0]["evidence"][0]["start"] = True
        raw = _fixture_raw(b)
        with self.assertRaises(CleanerError):
            Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)

    def test_cleaner_bad_hash(self):
        b = bundle_ok()
        b["source_versions"][0]["canonical_body_sha256"] = "0" * 64
        raw = _fixture_raw(b)
        with self.assertRaises(CleanerError):
            Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)

    def test_cleaner_unknown_source_version(self):
        b = bundle_ok()
        b["candidates"][0]["evidence"][0]["source_version_id"] = "nope-v9"
        raw = _fixture_raw(b)
        with self.assertRaises(CleanerError):
            Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)

    def test_cleaner_field_without_evidence(self):
        b = bundle_ok()
        for e in b["candidates"][0]["evidence"]:
            e["field"] = "feature_keys"  # title becomes uncovered
        raw = _fixture_raw(b)
        with self.assertRaises(CleanerError):
            Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)

    def test_cleaner_entity_type_no_quote_required(self):
        raw = _fixture_raw(bundle_ok())
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        self.assertTrue(all(r["payload"]["classification"]["entity_type"] == "venue"
                            for r in recs))
        # unknowns never enter the fact draft nor become known values
        for r in recs:
            self.assertNotIn("hours", r["payload"]["draft"])
            self.assertIn("hours", r["payload"]["unknowns"])

    def test_cleaner_nan_payload(self):
        b = bundle_ok()
        b["candidates"][0]["draft"]["feature_keys"] = [float("nan")]
        raw = _fixture_raw(b)
        with self.assertRaises(CleanerError):
            Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)

    def test_scorer_rejects_caller_score_or_pass(self):
        raw = _fixture_raw(bundle_ok())
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        recs[0]["payload"]["score"] = 99.0
        with self.assertRaises(ScorerError):
            Scorer(self.contract, as_of=AS_OF, tool_version=TOOL).score(recs)
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        recs[0]["payload"]["passed"] = True
        with self.assertRaises(ScorerError):
            Scorer(self.contract, as_of=AS_OF, tool_version=TOOL).score(recs)

    def test_scorer_unknown_operator(self):
        raw = _fixture_raw(bundle_ok())
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        scoring = dict(self.contract.rubric["scoring"])
        parts = [dict(p) for p in scoring["parts"]]
        parts[0]["name"] = "bogus_operator"
        scoring["parts"] = parts
        import types
        from toolbox.pack_schema import PackContract
        bad_contract = PackContract(pack_id="cuisines", version="x", pack={},
                                    fields=self.contract.fields,
                                    pointers=self.contract.pointers,
                                    validation=self.contract.validation,
                                    rubric={"scoring": scoring},
                                    expectations=self.contract.expectations,
                                    store_root=self.store)
        with self.assertRaises(ScorerError):
            Scorer(bad_contract, as_of=AS_OF, tool_version=TOOL).score(recs)

    def test_scorer_scores_and_fingerprint(self):
        raw = _fixture_raw(bundle_ok())
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        scored = Scorer(self.contract, as_of=AS_OF, tool_version=TOOL).score(recs)
        self.assertEqual(len(scored), 6)
        for s in scored:
            self.assertIn("config_fingerprint", s["payload"]["provenance"])
            self.assertIn("unknowns", s["payload"]["scope"])
        self.assertTrue(all(s["payload"]["score"]["passed"] for s in scored))

    def test_writer_satisfies_public_schemas(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-wr-"))
        manifest = manifest_of()
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        raw_id = _write_raw(storage, manifest.project_id, bundle_ok())
        raw = storage.read(manifest.project_id, "RAW", raw_id)
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        identity = recs[0]["payload"]["identity"]
        rid = f"cand:{identity['source_record_revision']}"
        parent = {"layer": "RAW", "project_id": manifest.project_id,
                  "record_id": raw_id, "hash": raw["content_hash"]}
        version = append(storage, manifest.project_id, "ODS", rid, parent,
                         recs[0]["payload"])
        ods = storage.read(manifest.project_id, "ODS", rid, version)
        wrapped = {"schemaVersion": "0.2.0", "project_id": ods["project_id"],
                   "layer": "ODS", "record_id": ods["record_id"],
                   "parent_ref": ods["parent_ref"], "content": ods["content"]}
        validate_against("clean", wrapped)  # SDK-visible public schema
        storage.close()

    def test_auditor_recompute_pass_then_tamper_fail(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-au-"))
        manifest = manifest_of()
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        raw_id = _write_raw(storage, manifest.project_id, bundle_ok())
        dw_ids = _ods_to_dw(storage, manifest, self.contract, raw_id)
        aud = Auditor(self.contract, as_of=AS_OF, tool_version=TOOL,
                      storage=storage, project_id=manifest.project_id)
        r = aud.audit(manifest, raw_id, dw_ids[0])
        self.assertTrue(r.passed, r.findings)
        # tamper: append a second DW version with altered content -> latest differs
        dw = storage.read(manifest.project_id, "DW", dw_ids[0])
        tampered = dict(dw["content"])
        tampered["score"] = dict(tampered["score"])
        tampered["score"]["total"] = 999.0
        parent = dw["parent_ref"]
        append(storage, manifest.project_id, "DW", dw_ids[0], parent, tampered)
        r2 = aud.audit(manifest, raw_id, dw_ids[0])
        self.assertFalse(r2.passed)
        storage.close()

    def test_auditor_config_change_fails(self):
        manifest=manifest_of();storage=make_storage(manifest.to_dict(),manifest.path.parent)
        try:
            raw_id=_write_raw(storage,manifest.project_id,bundle_ok())
            dw_ids=_ods_to_dw(storage,manifest,self.contract,raw_id)
            data=yaml.safe_load(manifest.path.read_text());data["project"]["region"]="changed"
            manifest.path.write_text(yaml.safe_dump(data));changed=Manifest.load(manifest.path)
            aud=Auditor(self.contract,as_of=AS_OF,tool_version=TOOL,storage=storage,project_id=manifest.project_id)
            self.assertFalse(aud.audit(changed,raw_id,dw_ids[0]).passed)
        finally:storage.close()

    def test_auditor_binds_manifest_and_pack(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-au-"))
        manifest = manifest_of()
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        raw_id = _write_raw(storage, manifest.project_id, bundle_ok())
        dw_ids = _ods_to_dw(storage, manifest, self.contract, raw_id)
        aud = Auditor(self.contract, as_of=AS_OF, tool_version=TOOL,
                      storage=storage, project_id=manifest.project_id)
        r = aud.audit(manifest, raw_id, dw_ids[0])
        payload = r.audit_record["payload"]["audit"]
        self.assertIn("manifest_fingerprint", payload)
        self.assertEqual(payload["manifest_schema_version"], "0.4.0")
        self.assertEqual(payload["dw_version"], 1)
        self.assertEqual(r.audit_record["payload"]["provenance"]["pack_id"], "cuisines")
        storage.close()


class SoftwarePackTest(unittest.TestCase):
    def setUp(self):
        self.store = pathlib.Path(tempfile.mkdtemp(prefix="p2-pack-sw-"))
        self.contract = install_packs(self.store, "software-releases")

    def _official_json(self):
        return {"name": "codex", "tag_name": "v0.61.0",
                "published_at": "2026-10-01T00:00:00Z",
                "html_url": "https://github.com/openai/codex/releases/tag/v0.61.0",
                "body": "release notes body", "assets": []}

    def test_software_cleaner_pointer_evidence_from_raw(self):
        # RAW is the official JSON itself; cleaner auto-generates pointer evidence
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-sw-"))
        manifest = manifest_of(project_id="sw", backend="sqlite")
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        raw_id = _write_raw(storage, "sw", self._official_json(),
                            source_url="https://api.github.com/repos/openai/codex/releases/latest")
        raw = storage.read("sw", "RAW", raw_id)
        recs = Cleaner(self.contract, as_of=AS_OF, tool_version=TOOL).clean(raw)
        self.assertEqual(len(recs), 1)
        payload = recs[0]["payload"]
        self.assertEqual(payload["draft"]["tag_name"], "v0.61.0")
        self.assertEqual(len(payload["evidence"]), 4)
        for e in payload["evidence"]:
            self.assertIn("pointer", e)
            self.assertIn("value", e)
        scored = Scorer(self.contract, as_of=AS_OF, tool_version=TOOL).score(recs)
        self.assertTrue(scored[0]["payload"]["score"]["passed"])
        storage.close()

    def test_software_raw_hash_mismatch_fails(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-sw-"))
        manifest = manifest_of(project_id="sw", backend="sqlite")
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        payload = self._official_json()
        ph = payload_sha(payload)
        record = {
            "schemaVersion": "0.2.0", "project_id": "sw", "layer": "RAW",
            "payload": payload,
            "source_url": "u", "source_hash": "0" * 64, "batch": "b",
            "captured_at": AS_OF,
            "lineage": {"project": "sw", "source_url": "u", "source_hash": ph,
                        "batch": "b", "captured_at": AS_OF,
                        "steps": ["acquire"], "tool_versions": {"toolbox": TOOL},
                        "parent_ref": None},
        }
        with self.assertRaises(StorageError):
            storage.write_raw("sw", record)
        storage.close()


class ManifestContractTest(unittest.TestCase):
    """Manifest 0.4.0 routes to the new contract; 0.3.3 stays on the real
    archived schema; unknown schemaVersion fails closed; postgres config never
    silently downgrades to sqlite."""

    def _write(self, root, data):
        proj = root / "proj"
        proj.mkdir(exist_ok=True)
        mp = proj / "manifest.yaml"
        mp.write_text(yaml.safe_dump(data), encoding="utf-8")
        return mp

    def test_040_postgres_manifest_loads_and_factory_never_silently_sqlite(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-man-"))
        data = {
            "schemaVersion": "0.4.0",
            "project": {"project_id": "proj", "name": "proj", "domain": "test",
                        "region": "test"},
            "storage": {"backend": "postgres",
                        "postgres": {"dsn_env": "CTFS_P2_DSN_UNSET",
                                     "schema": "ctfs_p2test"}},
            "crawler": {"connector": "http-public", "timeout_seconds": 30.0,
                        "max_requests": 2, "max_bytes": 2000000,
                        "per_request_max_bytes": 1000000},
            "ontology": {"packs": ["cuisines"]},
            "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                          for k in ("raw", "clean", "scored", "audit")},
            "raw": {"sources": []},
        }
        mp = self._write(root, data)
        m = Manifest.load(mp)
        self.assertEqual(m.storage["backend"], "postgres")
        self.assertEqual(m.schema_version, "0.4.0")
        with self.assertRaises(StorageError):
            make_storage(m.to_dict(), mp.parent)

    def test_033_archive_still_readable(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-man-"))
        data = {
            "schemaVersion": "0.3.3",
            "project": {"project_id": "proj", "name": "proj", "domain": "test",
                        "region": "test"},
            "storage": {"backend": "sqlite", "path": "data/store.sqlite"},
            "crawler": {"connector": "http-public", "timeout_seconds": 30.0,
                        "max_requests": 2, "max_bytes": 2000000,
                        "per_request_max_bytes": 1000000},
            "ontology": {"packs": ["cuisines"]},
            "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                          for k in ("raw", "clean", "scored", "audit")},
            "raw": {"sources": [{"source_id": "s1", "kind": "http-public",
                                 "url": "https://example.test/x"}]},
        }
        mp = self._write(root, data)
        m = Manifest.load(mp)
        self.assertEqual(m.storage["backend"], "sqlite")
        self.assertEqual(m.schema_version, "0.3.3")

    def test_unknown_version_fails_closed(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-man-"))
        data = {
            "schemaVersion": "9.9.9",
            "project": {"project_id": "proj", "name": "proj", "domain": "test",
                        "region": "test"},
            "storage": {"backend": "sqlite", "path": "data/store.sqlite"},
            "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                          for k in ("raw", "clean", "scored", "audit")},
            "raw": {"sources": []},
        }
        mp = self._write(root, data)
        with self.assertRaises(ManifestError):
            Manifest.load(mp)


class StorageFactoryTest(unittest.TestCase):
    def test_sqlite(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-sf-"))
        m = {"storage": {"backend": "sqlite", "path": "data/store.sqlite"}}
        st = make_storage(m, root)
        self.assertIsInstance(st, SqliteStorage)
        st.close()

    def test_postgres_without_env_never_silently_sqlite(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-sf-"))
        m = {"storage": {"backend": "postgres", "path": "x",
                         "postgres": {"dsn_env": "CTFS_P2_DSN_UNSET",
                                      "schema": "ctfs_p2test"}}}
        with self.assertRaises(StorageError):
            make_storage(m, root)

    def test_postgres_bad_schema_rejected(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-sf-"))
        m = {"storage": {"backend": "postgres", "path": "x",
                         "postgres": {"dsn_env": "CTFS_P2_DSN_UNSET",
                                      "schema": "public"}}}
        with self.assertRaises(StorageError):
            make_storage(m, root)

    def test_unknown_backend_rejected(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="p2-sf-"))
        m = {"storage": {"backend": "mysql", "path": "x"}}
        with self.assertRaises(StorageError):
            make_storage(m, root)


if __name__ == "__main__":
    unittest.main()
