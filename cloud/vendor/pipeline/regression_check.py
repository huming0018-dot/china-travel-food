#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regression_check.py — sourcing 机制回归检查（确定性、可复跑、只读）。

把用户历轮点名/亲测店（research/regression_set.json）当作断言：命中=当前库能匹配到；
未命中=机制仍漏，需定位断点修机制后重跑，**绝不手工补店**。
匹配复用 authority_sitemap 的 core/_distinct/make_matcher（繁简异体、通用业态前后缀）。

用法：
  python regression_check.py                 # 检查，落 regression_check.json；有 miss 退出码 1
  python regression_check.py --show-missing  # 只打印未命中清单
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), "/app/pipeline", "/app/cloud"):
    if p not in sys.path:
        sys.path.insert(0, p)
import common as C            # noqa: E402
import authority_sitemap as S  # noqa: E402


def regression_path():
    env = pathlib.Path(sys.argv[0]).resolve()
    for cand in (S.PROJ / "research" / "regression_set.json",
                 pathlib.Path("/app/research/regression_set.json"),
                 pathlib.Path("/app/data/regression_set.json"),
                 pathlib.Path("/app/data/authority/regression_set.json")):
        if cand.exists():
            return cand
    raise SystemExit("找不到 regression_set.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-missing", action="store_true")
    args = ap.parse_args()

    book = json.loads(regression_path().read_text(encoding="utf-8"))
    assertions = book["assertions"]

    rests = C.fetch_all("restaurants", "id,name,name_en,aliases,status,district")
    virt = []
    for r in rests:
        virt.append(r)
        for al in (r.get("aliases") or []):
            if al:
                rr = dict(r); rr["name"] = al; rr["name_en"] = None; virt.append(rr)
    matcher = S.make_matcher(virt)

    hits, misses = [], []
    for a in assertions:
        names = [a["name"]] + (a.get("aliases") or [])
        cores = []
        for n in names:
            c = S.core(n)
            if c and c not in cores:
                cores.append(c)
        m, conf = matcher(cores)
        rec = {"name": a["name"], "scene": a.get("scene"),
               "expected_path": a.get("expected_path"), "match_conf": conf,
               "matched_id": m["id"] if m else None,
               "matched_name": m["name"] if m else None,
               "matched_status": m["status"] if m else None,
               "was_hit": a.get("hit")}
        (hits if (conf in ("exact", "strong") and m) else misses).append(rec)

    out = {"total": len(assertions), "hits": len(hits), "misses": len(misses),
           "hit": hits, "missing": misses}
    (S.AUTH / "regression_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"回归检查：{len(hits)}/{len(assertions)} 命中，{len(misses)} 未命中")
    shown = misses if args.show_missing else hits + misses
    for r in shown:
        tag = "✓" if r in hits else "✗"
        extra = f"-> id {r['matched_id']} {r['matched_name']}({r['match_conf']})" if r in hits \
            else f"（期望路径 {r['expected_path']}）"
        print(f"  {tag} {r['name']} [{r.get('scene')}] {extra}")
    print("\n已落 regression_check.json")
    sys.exit(0 if not misses else 1)


if __name__ == "__main__":
    main()
