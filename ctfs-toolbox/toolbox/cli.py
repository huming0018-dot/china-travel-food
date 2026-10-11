"""CTFS Toolbox CLI: toolbox init / validate / crawl / pack / clean / score / audit.

0.4.0: storage backend sqlite|postgres via storage_factory (never silently
downgrades to sqlite); clean/score/audit run the pack-driven M2/M3/M6 modules
and write versioned ODS/DW/APP records with pinned parent_ref hashes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__
from .auditor import Auditor, AuditorError
from .cleaner import Cleaner, CleanerError
from .crawler import Crawler, CrawlerError
from .manifest import Manifest, ManifestError
from .ontology import OntologyManager, PackError
from .pack_schema import load_pack
from .schema import SchemaError, validate_against
from .scorer import Scorer, ScorerError
from .storage_factory import make_storage
from .writer import WriterError, append, record_id
from .stages import Stages

_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _as_of_default() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_init(args: argparse.Namespace) -> int:
    import yaml
    project_id = args.project_id
    root = Path(args.dir).resolve()
    if not _PROJECT_ID_RE.fullmatch(project_id) or not root.is_dir():
        print("init FAILED: invalid project_id or target directory", file=sys.stderr)
        return 2
    projects = root / "projects"
    project_dir = projects / project_id
    if projects.is_symlink() or project_dir.is_symlink() or project_dir.exists():
        print("init FAILED: refusing existing project or symlink", file=sys.stderr)
        return 2
    backend = getattr(args, "backend", "sqlite")
    if backend not in ("sqlite", "postgres"):
        print("init FAILED: unsupported backend", file=sys.stderr)
        return 2
    if backend == "postgres":
        if not args.pg_dsn_env or not args.pg_schema:
            print("init FAILED: postgres backend requires --pg-dsn-env and --pg-schema", file=sys.stderr)
            return 2
        if not re.fullmatch(r"^[A-Z][A-Z0-9_]{0,63}$", args.pg_dsn_env):
            print("init FAILED: --pg-dsn-env must be an env-var NAME (uppercase)", file=sys.stderr)
            return 2
        if not re.fullmatch(r"^ctfs_[a-z0-9_]{1,48}$", args.pg_schema):
            print("init FAILED: --pg-schema must match ^ctfs_[a-z0-9_]{1,48}$", file=sys.stderr)
            return 2
        storage = {"backend": "postgres",
                   "postgres": {"dsn_env": args.pg_dsn_env, "schema": args.pg_schema}}
    else:
        storage = {"backend": "sqlite", "path": "data/store.sqlite"}
    data = {
        "schemaVersion": "0.4.0",
        "project": {"project_id": project_id, "name": project_id,
                    "domain": args.domain, "region": args.region},
        "storage": storage,
        "crawler": {"connector": "http-public", "timeout_seconds": 30.0,
                    "max_requests": 8, "max_bytes": 8000000,
                    "per_request_max_bytes": 1000000},
        "ontology": {"packs": []},
        "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                      for k in ("raw", "clean", "scored", "audit")},
        "raw": {"sources": []},
    }
    try:
        validate_against("manifest", data)
    except SchemaError as exc:
        print("init FAILED: " + str(exc), file=sys.stderr)
        return 2
    projects.mkdir(exist_ok=True)
    project_dir.mkdir(exist_ok=False)
    with (project_dir / "manifest.yaml").open("x", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"initialized {project_id} at {project_dir} (manifest 0.4.0, backend {backend})")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        manifest = Manifest.load(args.manifest)
    except ManifestError as exc:
        print(f"MANIFEST INVALID: {exc}", file=sys.stderr)
        return 2
    print(f"MANIFEST OK: project={manifest.project_id} domain={manifest.domain} "
          f"region={manifest.region} schemaVersion={manifest.schema_version}")
    if args.data_layer:
        layer = args.data_layer
        if layer not in ("raw", "clean", "scored", "audit"):
            print(f"unknown data layer {layer!r}", file=sys.stderr)
            return 2
        try:
            data = json.loads(Path(args.data_file).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"data file error: {exc}", file=sys.stderr)
            return 2
        try:
            validate_against(layer, data)
        except SchemaError as exc:
            print(f"DATA INVALID ({layer}): {exc}", file=sys.stderr)
            return 2
        print(f"DATA OK ({layer}): {args.data_file}")
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    try:
        manifest = Manifest.load(args.manifest)
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        crawler = Crawler(manifest, storage)
        try:
            summaries = crawler.crawl(args.source_id)
        finally:
            crawler.close()
            storage.close()
    except (ManifestError, CrawlerError, Exception) as exc:  # noqa: BLE001
        if isinstance(exc, (ManifestError, CrawlerError)):
            print(f"CRAWL FAILED: {exc}", file=sys.stderr)
            return 2
        raise
    for s in summaries:
        state = "OK" if s["ok"] else f"FAIL({s['error_kind']})"
        extra = f" sha256={s['sha256']} raw_id={s['raw_id']}" if s["ok"] else f" error={s['error']}"
        print(f"[{state}] {s['source_id']} {s['connector']} {s['url']} code={s['code']} "
              f"bytes={s['bytes']}{extra}")
    return 0


def _stage(args, operation):
    storage = None
    try:
        manifest = Manifest.load(args.manifest)
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        contract = load_pack(args.dir, args.pack_id)
        stages = Stages(manifest, contract, storage, args.as_of)
        if operation == "clean":
            rows = stages.clean(args.raw_id)
            result = [{"record_id": r["record_id"], "version": r["version"], "hash": r["content_hash"]} for r in rows]
        elif operation == "score":
            r = stages.score(args.ods_id, args.ods_version)
            result = {"record_id": r["record_id"], "version": r["version"], "hash": r["content_hash"], "score": r["content"]["score"]}
        else:
            r = stages.audit(args.raw_id, args.dw_id, args.dw_version)
            result = {"passed": r["passed"], "findings": r["findings"], "record_id": r["audit"]["record_id"], "version": r["audit"]["version"], "hash": r["audit"]["content_hash"]}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 3 if operation == "audit" and not result["passed"] else 0
    except Exception as exc:
        print(operation.upper()+" FAILED: "+type(exc).__name__, file=sys.stderr)
        return 2
    finally:
        if storage is not None: storage.close()

def cmd_clean(args): return _stage(args, "clean")
def cmd_score(args): return _stage(args, "score")
def cmd_audit(args): return _stage(args, "audit")


def cmd_pack_install(args: argparse.Namespace) -> int:
    try:
        om = OntologyManager(Path(args.dir).resolve())
        result = om.install(Path(args.source), args.pack_id, args.version)
    except (PackError, Exception) as exc:  # noqa: BLE001
        if isinstance(exc, PackError):
            print(f"PACK INSTALL FAILED: {exc}", file=sys.stderr)
            return 2
        raise
    print(f"pack installed: {result['pack_id']}@{result['version']} active={result['active']} "
          f"files={len(result['files'])}")
    return 0


def cmd_pack_verify(args: argparse.Namespace) -> int:
    try:
        om = OntologyManager(Path(args.dir).resolve())
        result = om.verify(args.pack_id, args.version)
    except PackError as exc:
        print(f"PACK VERIFY FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"pack verified: {result['pack_id']}@{result['version']}")
    return 0


def cmd_pack_list(args: argparse.Namespace) -> int:
    om = OntologyManager(Path(args.dir).resolve())
    packs = om.list_packs()
    if not packs:
        print("no packs installed")
        return 0
    for p in packs:
        print(f"{p['pack_id']} versions={','.join(p['versions'])} active={p['active']}")
    return 0


def cmd_pack_rollback(args: argparse.Namespace) -> int:
    try:
        om = OntologyManager(Path(args.dir).resolve())
        result = om.rollback(args.pack_id, args.version)
    except PackError as exc:
        print(f"PACK ROLLBACK FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"pack rolled back: {result['pack_id']} {result['from']} -> {result['to']} "
          f"kept={','.join(result['kept'])}")
    return 0


def cmd_run(args):
    from .jobs import Jobs
    storage = jobs = None
    try:
        manifest = Manifest.load(args.manifest)
        selected = manifest.ontology.get("packs", [])
        if len(selected) != 1: raise ValueError("exactly one configured pack required")
        contract = load_pack(Path(args.dir), selected[0])
        storage = make_storage(manifest.to_dict(), manifest.path.parent)
        jobs = Jobs(manifest, contract, storage, args.as_of)
        result = jobs.status(args.job_id) if args.command == "job" else jobs.run(args.job_id, args.pause_after)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("JOB FAILED: "+type(exc).__name__, file=sys.stderr)
        return 3
    finally:
        if jobs is not None: jobs.close()
        if storage is not None: storage.close()

def cmd_serve(args):
    from .consumer import serve
    try: serve(args.manifests, args.dir, args.as_of, args.port)
    except Exception as exc:
        print("SERVE FAILED: "+type(exc).__name__, file=sys.stderr)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="toolbox", description="CTFS modular data toolbox")
    parser.add_argument("--version", action="version", version=f"ctfs-toolbox {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create a project manifest skeleton (0.4.0)")
    p_init.add_argument("project_id")
    p_init.add_argument("--domain", required=True)
    p_init.add_argument("--region", required=True)
    p_init.add_argument("--backend", choices=("sqlite", "postgres"), default="sqlite")
    p_init.add_argument("--pg-dsn-env", help="env-var NAME holding the PG DSN")
    p_init.add_argument("--pg-schema", help="ctfs_* schema name (postgres backend)")
    p_init.add_argument("--dir", default=".", help="toolbox root (default: cwd)")
    p_init.set_defaults(func=cmd_init)

    p_val = sub.add_parser("validate", help="validate a manifest (and optional data layer)")
    p_val.add_argument("manifest")
    p_val.add_argument("--data-layer", choices=("raw", "clean", "scored", "audit"))
    p_val.add_argument("--data-file")
    p_val.set_defaults(func=cmd_validate)

    p_crawl = sub.add_parser("crawl", help="run manifest sources through connectors")
    p_crawl.add_argument("manifest")
    p_crawl.add_argument("--source-id", help="crawl only this manifest source")
    p_crawl.set_defaults(func=cmd_crawl)

    p_clean = sub.add_parser("clean", help="RAW -> ODS (pack-driven cleaner)")
    p_clean.add_argument("manifest")
    p_clean.add_argument("--raw-id", required=True)
    p_clean.add_argument("--pack-id", required=True)
    p_clean.add_argument("--as-of", required=True)
    p_clean.add_argument("--dir", default=".", help="pack store root")
    p_clean.set_defaults(func=cmd_clean)

    p_score = sub.add_parser("score", help="ODS -> DW (pack-driven scorer)")
    p_score.add_argument("manifest")
    p_score.add_argument("--ods-id", required=True)
    p_score.add_argument("--ods-version", type=int)
    p_score.add_argument("--pack-id", required=True)
    p_score.add_argument("--as-of", required=True)
    p_score.add_argument("--dir", default=".", help="pack store root")
    p_score.set_defaults(func=cmd_score)

    p_audit = sub.add_parser("audit", help="RAW+DW -> exact APP audit")
    p_audit.add_argument("manifest")
    p_audit.add_argument("--raw-id", required=True)
    p_audit.add_argument("--dw-id", required=True)
    p_audit.add_argument("--dw-version", type=int)
    p_audit.add_argument("--pack-id", required=True)
    p_audit.add_argument("--as-of", required=True)
    p_audit.add_argument("--dir", default=".", help="pack store root")
    p_audit.set_defaults(func=cmd_audit)

    p_pack = sub.add_parser("pack", help="ontology pack operations")
    p_pack_sub = p_pack.add_subparsers(dest="pack_cmd", required=True)
    p_inst = p_pack_sub.add_parser("install", help="install an immutable pack version")
    p_inst.add_argument("source")
    p_inst.add_argument("--pack-id")
    p_inst.add_argument("--version")
    p_inst.add_argument("--dir", default=".")
    p_inst.set_defaults(func=cmd_pack_install)
    p_ver = p_pack_sub.add_parser("verify", help="verify pack SHA index and contract")
    p_ver.add_argument("pack_id")
    p_ver.add_argument("--version")
    p_ver.add_argument("--dir", default=".")
    p_ver.set_defaults(func=cmd_pack_verify)
    p_lst = p_pack_sub.add_parser("list", help="list installed packs")
    p_lst.add_argument("--dir", default=".")
    p_lst.set_defaults(func=cmd_pack_list)
    p_rbk = p_pack_sub.add_parser("rollback", help="switch active pack version")
    p_rbk.add_argument("pack_id")
    p_rbk.add_argument("version")
    p_rbk.add_argument("--dir", default=".")
    p_rbk.set_defaults(func=cmd_pack_rollback)

    p_run = sub.add_parser("run", help="execute the built-in durable crawl/clean/score/audit/deliver DAG")
    p_run.add_argument("manifest")
    p_run.add_argument("--job-id", required=True)
    p_run.add_argument("--as-of", required=True)
    p_run.add_argument("--dir", required=True, help="verified pack store root")
    p_run.add_argument("--pause-after", choices=("crawl", "clean", "score", "audit", "deliver"))
    p_run.set_defaults(func=cmd_run)
    p_job = sub.add_parser("job", help="read exact durable job attempts")
    p_job.add_argument("manifest")
    p_job.add_argument("--job-id", required=True)
    p_job.add_argument("--as-of", required=True)
    p_job.add_argument("--dir", required=True)
    p_job.set_defaults(func=cmd_run)
    p_serve = sub.add_parser("serve", help="serve current independently gated reports on loopback only")
    p_serve.add_argument("manifests", nargs="+")
    p_serve.add_argument("--as-of", default=None, help="optional fixed evaluation time; otherwise use each gated report time")
    p_serve.add_argument("--dir", required=True)
    p_serve.add_argument("--port", type=int, default=18790)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
