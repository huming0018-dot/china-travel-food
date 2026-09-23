#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收口修复：3家坐标/正名、3家私厨notes、3家私房菜补菜系；写后回读。"""
import sys
import time

PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, PIPE)
import common as C  # noqa: E402


def patch(rid, fields):
    r = C.req("PATCH", f"/restaurants?id=eq.{rid}", json=fields)
    return r.status_code in (200, 204)


def add_rc(rid, cid):
    ex = C.req("GET", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}").json()
    if ex:
        return "exists"
    r = C.req("POST", "/restaurant_cuisines", json={"restaurant_id": rid, "cuisine_id": cid})
    return r.status_code in (200, 201, 204)


print("=== A 坐标/正名 ===")
print("1857 野人先生", patch(1857, {"location": C.point_ewkt(121.45398, 31.216415)}))
print("1856 泽田本家", patch(1856, {
    "name": "泽田本家·铜锣烧(美罗城店)",
    "address": "徐汇区肇嘉浜路1111号美罗城2-1C、2-1C-1室",
    "location": C.point_ewkt(121.439994, 31.193192)}))
print("1853 苹果花园", patch(1853, {
    "address": "浦东新区塘桥街道南泉路1260号",
    "phone": "18116051793",
    "location": C.point_ewkt(121.522505, 31.212214)}))

print("\n=== B 私厨 notes（无公开坐标）===")
note = "预约制/无招牌私厨，公开源无精确坐标，按宁空不猜留空。"
for rid in (584, 1846, 1854):
    old = C.req("GET", f"/restaurants?id=eq.{rid}&select=notes").json()[0].get("notes") or ""
    if note not in old:
        patch(rid, {"notes": (old + " " + note).strip()})
    print("notes", rid)

print("\n=== C 补菜系 ===")
print("1845 黄公子 -> 254 海派融合:", add_rc(1845, 254))
print("1848 作故 -> 44 融合菜:", add_rc(1848, 44))
print("1849 叶叶菩提 -> 44 融合菜:", add_rc(1849, 44))

time.sleep(0.4)
print("\n=== 回读验证 ===")
for rid in (1857, 1856, 1853):
    r = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,name,address,phone,location").json()[0]
    print(rid, r["name"], "| loc", bool(C.parse_location(r["location"])), "| phone", r.get("phone"))
cuis = {c["id"]: c for c in C.fetch_all("cuisines", "id,name,dimension")}
for rid in (1845, 1848, 1849):
    cids = {x["cuisine_id"] for x in
            C.req("GET", f"/restaurant_cuisines?restaurant_id=eq.{rid}&select=cuisine_id").json()}
    print(rid, [(c, cuis[c]["name"], cuis[c]["dimension"]) for c in sorted(cids) if c in cuis])
