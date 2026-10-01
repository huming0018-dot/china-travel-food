#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_chef_seed.py — 把外部「主厨候选池（推演、非官方）」以 is_seed=true 的
未证实假设导入 lead_hypotheses（绝不直写 chefs / restaurant_chefs 事实表）。

输入：极简 JSON 数组，元素 {chef_name, restaurant, city}。
  - 有 restaurant → relation=worked_at, object=餐厅；
  - 无 restaurant → relation=related_to, object=null（待关联门店）。
全部 status=hypothesized / known=推断 / confidence=0.20 / 无来源，
之后由 chef_snowball + prove 取证，过 hae_engine 闸门才可能晋升。

用法（容器内先 . /app/cloud/env.sh）：
  python3 ingest_chef_seed.py --input pool.json            # dry-run
  python3 ingest_chef_seed.py --input pool.json --apply    # 幂等 upsert 假设表
"""
import argparse
import datetime
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import hae_engine as H  # noqa: E402

SEED_VERSION = "chefseed-v1"


def convert(records):
    today = datetime.date.today().isoformat()
    rows = []
    for rec in records:
        name = (rec.get("chef_name") or "").strip()
        if not name:
            continue
        rest = (rec.get("restaurant") or "").strip()
        city = (rec.get("city") or "上海").strip()
        if rest:
            rel, obj = "worked_at", rest
            claim = (f"候选主厨「{name}」曾/现任于「{rest}」（{city}）；"
                     f"来源为外部推演主厨池、非官方、未核实，待取证。")
        else:
            rel, obj = "related_to", None
            claim = (f"候选主厨「{name}」在{city}餐饮圈、未关联门店；"
                     f"外部推演主厨池、非官方、未核实，待取证。")
        row = {
            "subject_type": "chef", "subject_name": name,
            "relation": rel, "object": obj, "when": None,
            "claim_text": claim, "confidence": 0.20,
            "known_vs_inferred": "推断", "status": "hypothesized",
            "evidence": [], "confirmed_source_urls": [], "confirm_voices": 0,
            "model_consensus": "single",
            "confirm_queries": [f"{name} {rest} 上海 主厨 履历".strip(),
                                f"{name} {rest} 招牌菜 师承".strip()],
            "falsify_queries": [f"{name} 查无此人 辟谣",
                                f"{rest or name} 上海 不存在 关店"],
            "is_seed": True,
            "proposed_by": {
                "channel": "user/chef-candidate-pool",
                "anchor_tier": "未分级候选",
                "prompt_hash": SEED_VERSION, "date": today,
                "source_note": "外部《主厨库自主迭代》推演候选池，非官方；禁止直接当事实，需取证过闸",
            },
        }
        rows.append(H.norm_row(row))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    records = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    rows = convert(records)
    print(f"候选记录 {len(records)} 条 → 生成假设 {len(rows)} 条（is_seed=true）")
    for r in rows[:8]:
        print("  -", r["subject_name"], r["relation"], r["object"] or "")
    if len(rows) > 8:
        print(f"  … 其余 {len(rows)-8} 条")
    res = H.upsert_rows(rows, apply=args.apply)
    print("upsert:", json.dumps(res, ensure_ascii=False))
    if not args.apply:
        print("[dry-run] 加 --apply 写入假设表。")


if __name__ == "__main__":
    main()
