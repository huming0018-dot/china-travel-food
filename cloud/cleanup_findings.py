#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanup_findings.py — 清洗 findings.jsonl（确定性、可复跑、幂等）。

安全口径（避免误杀运营公司本名≠品牌的正常证据）：
  D1 investor/price：仅当证据【点名别家在库餐饮品牌、且未出现本店】(gate.brand_contradiction)
     才判错挂丢弃；自证缺失但未点名别家 → 保留。
  D2 分店店（店名括号内有分店后缀）的 price 证据，reason 必须含该分店后缀，
     否则是别家分店价 → 丢弃。
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core
import gate_apply as G

LEDGER = pathlib.Path("/app/data/post_record")
FP = LEDGER / "findings.jsonl"


def main():
    rests = core.fetch_all("restaurants", "id,name")
    names = {r["id"]: r["name"] for r in rests}
    P = core.pipeline_common()
    brand_index = G.build_brand_index(rests, P)
    rows = [json.loads(l) for l in FP.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept, dropped = [], []
    for d in rows:
        rid, fld = d.get("restaurant_id"), d.get("field")
        sname = names.get(rid, "")
        text = (d.get("reason") or "") + " " + str(d.get("value") or "")
        if fld in ("investor_info", "price_avg"):
            other = G.brand_contradiction(sname, text, brand_index, rid, P)
            if other:
                dropped.append((rid, fld, d.get("value"), f"D1 other={other}"))
                continue
            m = re.search(r"[（(]([^（）()]+店|[^（）()]+分店|[^（）()]+首店)[)）]", sname)
            if fld == "price_avg" and m:
                branch = m.group(1)
                bcore = P.cjk_norm(re.sub(r"(分店|店)$", "", branch))
                rc = P.cjk_norm(d.get("reason") or "")
                if len(bcore) >= 2 and bcore not in rc:
                    dropped.append((rid, fld, d.get("value"), f"D2 branch≠{branch}"))
                    continue
        kept.append(d)
    FP.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in kept) + "\n",
                  encoding="utf-8")
    print(f"findings {len(rows)} -> {len(kept)}；dropped {len(dropped)}")
    for x in dropped:
        print("  DROP", x)
    print("CLEANUP_DONE")


if __name__ == "__main__":
    main()
