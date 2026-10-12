# CTFS reusable data toolbox 0.5.0

The toolbox executes project Manifests and pure data ontology packs. It preserves original RAW bytes and derives versioned ODS, DW and exact APP audits through public SDK/CLI interfaces. Business field names, pointers, labels, admission rules and scoring parameters live in packs rather than project Python scripts.

## Implemented interfaces

- M0: validated Manifest, strict layered Data 0.2 records, SQLite storage and optional isolated PostgreSQL storage.
- M1: bounded `snapshot-file` and `http-public` acquisition, durable source receipts and request budgets. Failed or unknown acquisition is retained rather than silently repeated.
- M2/M4: pure configuration driven cleaning for Unicode quotation evidence and official JSON pointer evidence. Exact original candidate identity and revision, source metadata, declared types and unknowns are preserved.
- M3: deterministic configuration driven score, admission rules, explicit reasons and fixed UTC evaluation time. Caller supplied score or pass values are rejected.
- M6: independent recomputation from retained RAW through the exact ODS/DW chain. Tool resource bytes, dependency versions, complete Manifest bytes, pack files and evaluation time bind the audit.

M5 implements a durable built-in serial DAG with exact outputs, process locks, pause/resume and retained unknown external attempts. M7 implements independently gated immutable JSON/HTML publications and a read-only loopback HTTP consumer. Stage acceptance and the final second-project proof require the separately recorded fixed-version real execution and independent review receipts.

## Install and use

Python 3.12 or newer is required. Install the frozen wheel; optional PostgreSQL support uses the `postgres` extra. Storage credentials are supplied only through a named environment variable, never a Manifest value.

Install a pack with `toolbox pack install PATH --dir STORE`. Check `toolbox --help` and each subcommand for the exact required options. The common CLI exposes `crawl`, `clean`, `score` and `audit`. Cleaning, scoring and auditing require the same fixed `--as-of` UTC timestamp and verified pack store `--dir`. Exact ODS/DW versions can be pinned explicitly.

The public `Stages(manifest, contract, storage, as_of)` adapter writes standards compliant layers for both project domains. `clean(raw_id)`, `score(ods_id, ods_version)` and `audit(raw_id, dw_id, dw_version)` preserve exact parent references. Identical reruns are idempotent. Failed audit produces a retained failure record and cannot become a delivered view.

## Bounded real validation

This checkpoint reuses retained original bytes without new external requests: six Shanghai discovery candidates with 25 Unicode references across three editorial sources, and two independent official release RAW responses. Both domains pass SQLite RAW/ODS/DW/APP audit persistence and reopening; the two software inputs also pass one new isolated PostgreSQL namespace. Actual run receipts and frozen wheel identity are kept outside source code.

Shanghai entries are discovery leads. Editorial references are not independent diners, and current hours, menus, prices, commercial relationships and personal taste remain unknown. Original HTTP responses of historical editorial sources were not retained; canonical source body hashes and snapshot bytes must not be labeled original HTTP hashes.

The software pack evaluates official release metadata. Compatibility, security assessment and asset contents remain unverified. No release assets are downloaded.

PostgreSQL validation is an isolated loopback engineering fixture with TLS false. It does not establish production Supabase, RLS or TLS acceptance. No original user feedback, production databases, past versions or existing application services are modified by this checkpoint.

## Common durable pipeline and consumer

Install a pure pack with `toolbox pack install PACK_PATH --dir PACK_STORE`. Execute `toolbox run MANIFEST --job-id ID --as-of UTC --dir PACK_STORE`; read durable state with `toolbox job` using the same options. Built-in stages are crawl, clean, score, audit and deliver. `--pause-after clean` pauses after a durable clean stage; rerunning the same job resumes it. Completed outputs are revalidated against exact references. Failed or unknown external acquisition is never automatically resent. A changed Manifest, pack, tool or evaluation time cannot resume an old job.

Use `toolbox serve MANIFEST_A MANIFEST_B --dir PACK_STORE --port 18790` to serve each latest independently gated publication. Omit `--as-of` to use the per-project fixed evaluation time retained in its publication receipt. The service binds only 127.0.0.1. Every report request reloads configuration and verifies RAW/DW/audit/view references and immutable report bytes. HTTP reading uses SQLite mode=ro and never creates missing databases; this consumer version explicitly rejects PostgreSQL reads rather than falling back. Earlier PostgreSQL storage verification is a separate capability.

Historical publications and exact job attempts are retained independently of the latest report pointer. Projects introduce only Manifests and pure six-file ontology packs; no per-project Python transformations or templates are loaded.
