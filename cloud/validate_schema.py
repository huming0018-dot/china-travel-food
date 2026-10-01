#!/usr/bin/env python3
# validate_schema.py — 非阻断校验：DB vs spec 漂移清单
import json, pathlib, sys
sys.path.insert(0, "/app/pipeline")
import common as C

SPEC = pathlib.Path("/app/cloud/docs/db_schema_spec.json")


def main():
    spec = json.loads(SPEC.read_text())
    drift = []
    for table, rule in spec["tables"].items():
        try:
            rows = C.fetch_all(f"/{table}", "*", page=1)
        except Exception as e:
            drift.append(f"{table}: fetch fail {e}")
            continue
        if not rows: continue
        enums = rule.get("enums", {})
        for col, allowed in enums.items():
            if col not in rows[0]: continue
            vals = set(r.get(col) for r in C.fetch_all(f"/{table}", col))
            bad = vals - set(allowed) - {None}
            if bad:
                drift.append(f"{table}.{col} 违规值: {bad}")
    print(json.dumps({"drift": drift, "n": len(drift)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
