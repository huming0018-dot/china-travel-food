# M7 PostgreSQL read-only consumption · 0.5.1 candidate

The public consumer previously rejected PostgreSQL storage. It now opens an existing compatible `ctfs_` schema with `read_only=True`, checks required relations and the contract marker, enables and verifies database read-only transaction state, and rejects all three writer methods. Opening performs no DDL or migrations. Missing storage fails closed; initialization errors expose only safe error categories and close the connection.

`toolbox serve` takes manifest paths as positional arguments:

```sh
toolbox serve projects/food/manifest.yaml projects/software/manifest.yaml --dir packs --port 18790
```

Credentials stay in the named environment variable on the execution host. A remote PostgreSQL connection still requires certificate verification. The existing writer mode and SQLite consumer remain supported.

The candidate was installed as a real wheel in a separate cloud environment. An independent review verified all 46 package files against source and wheel; two real projects (six Shanghai discovery cards and two official software releases) used the same public SDK and CLI. Three original RAW records and their acquisition identity were retained. Database write attempts were rejected; four actual HTML/JSON responses matched an independent read-only SDK derivation, with unchanged record counts and hashes during consumption. Original failed validation receipts remain preserved.

This is engineering PostgreSQL on loopback, not a production Supabase migration, public PG deployment, or completion of the full PRD. The existing 0.5.0 production release stays fixed. `runtime-version-map.json` records that frozen release; `runtime-version-map-0.5.1-candidate.json` records this candidate.
