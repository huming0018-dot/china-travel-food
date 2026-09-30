#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud/kol_context_backfill.py — 023 执行后：从 posts.summary+title 确定性回填 mentions.context。

规则（宁空不假）：
  - 在 post 的 title+summary 中定位 mentioned_raw，取前后 40 字窗口作为 context；
  - 定位不到（如连锁后缀、噪声碎片）→ context 留空 NULL，绝不编。
  - 幂等：已写过 context 的行跳过；默认 dry-run，--apply 才 PATCH。
用法：python3 kol_context_backfill.py [--apply]
"""
import argparse, sys
sys.path.insert(0, "/app/pipeline")
import common as C

W = 40
def window(text, name):
    if not text or not name: return None
    i = text.find(name)
    if i < 0: return None
    return text[max(0, i-W):i+len(name)+W]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    posts = {p["id"]: p for p in C.fetch_all("food_kol_posts", "id,title,summary", order_col="id")}
    ments = C.fetch_all("food_kol_mentions", "id,post_id,mentioned_raw,context", order_col="id")
    filled_now = sum(1 for m in ments if m.get("context"))
    todo, derivable = [], 0
    for m in ments:
        if m.get("context"): continue
        p = posts.get(m["post_id"])
        if not p: continue
        ctx = window((p.get("title") or "") + "\n" + (p.get("summary") or ""), m["mentioned_raw"])
        if ctx:
            derivable += 1
            todo.append((m["id"], ctx))
    print(f"mentions 总数={len(ments)} 已有context={filled_now} 可推导={derivable} 无可推导留空={len(ments)-filled_now-derivable}")
    if args.apply:
        ok = 0
        for mid, ctx in todo:
            r = C.req("PATCH", f"/food_kol_mentions?id=eq.{mid}", json={"context": ctx})
            if r.status_code in (200, 204): ok += 1
            else: print("FAIL", mid, r.status_code, r.text[:120])
        print(f"APPLY: PATCH {ok}/{len(todo)}")
        rb = C.fetch_all("food_kol_mentions", "id,context", order_col="id")
        print("回读: context 非空 =", sum(1 for m in rb if m.get("context")), "/", len(rb))

if __name__ == "__main__":
    main()
