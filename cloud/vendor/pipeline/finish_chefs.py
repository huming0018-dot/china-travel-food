#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finish_chefs.py — 补全剩余主厨和关联"""
import sys, datetime, requests
sys.path.insert(0, "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline")
import common as C

TODAY = datetime.date.today().isoformat()
H = {**C.headers(), "Prefer": "return=representation"}
BASE = C.BASE

def post(path, data):
    return requests.post(BASE + path, headers=H, json=data, timeout=45)

# Get existing chefs
existing = C.req("GET", "/chefs?select=id,name").json()
chef_id_map = {row["name"]: row["id"] for row in existing}
print(f"Existing chefs: {len(chef_id_map)}")

from build_chefs import CHEFS, ASSOCIATIONS

missing = [c for c in CHEFS if c["name"] not in chef_id_map]
print(f"Missing chefs to insert: {len(missing)}")

batch = []
for c in missing:
    row = {
        "name": c["name"], "name_en": c.get("name_en", ""),
        "title": c.get("title", ""), "bio": c.get("bio", ""),
        "origin": c.get("origin", ""),
        "culinary_background": c.get("culinary_background", ""),
        "signature_style": c.get("signature_style", ""),
        "reputation": c.get("reputation", ""),
        "group_id": c.get("group_id"),
        "restaurants_owned": c.get("restaurants_owned", []),
        "data_updated_at": TODAY, "last_tracked_at": TODAY,
    }
    batch.append(row)
    if len(batch) >= 10:
        r = post("/chefs", batch)
        if r.status_code in (200, 201):
            for row in r.json():
                chef_id_map[row["name"]] = row["id"]
            print(f"  Inserted {len(batch)}")
        else:
            print(f"  ERROR {r.status_code}: {r.text[:300]}")
        batch = []
if batch:
    r = post("/chefs", batch)
    if r.status_code in (200, 201):
        for row in r.json():
            chef_id_map[row["name"]] = row["id"]
        print(f"  Inserted {len(batch)}")
    else:
        print(f"  ERROR {r.status_code}: {r.text[:300]}")

print(f"\nTotal chefs: {len(chef_id_map)}")

existing_rc = C.req("GET", "/restaurant_chefs?select=restaurant_id,chef_id").json()
existing_pairs = set((row["restaurant_id"], row["chef_id"]) for row in existing_rc)
print(f"Existing associations: {len(existing_pairs)}")

to_insert = []
for name, rid, role, is_current, url in ASSOCIATIONS:
    cid = chef_id_map.get(name)
    if not cid:
        print(f"  SKIP: {name} not found")
        continue
    if (rid, cid) in existing_pairs:
        continue
    to_insert.append({"restaurant_id": rid, "chef_id": cid, "role": role,
                       "is_current": is_current, "source_url": url})

print(f"New associations to insert: {len(to_insert)}")
abatch = []
for a in to_insert:
    abatch.append(a)
    if len(abatch) >= 10:
        r = post("/restaurant_chefs", abatch)
        if r.status_code in (200, 201):
            print(f"  Inserted {len(abatch)}")
        else:
            print(f"  ERROR {r.status_code}: {r.text[:300]}")
        abatch = []
if abatch:
    r = post("/restaurant_chefs", abatch)
    if r.status_code in (200, 201):
        print(f"  Inserted {len(abatch)}")
    else:
        print(f"  ERROR {r.status_code}: {r.text[:300]}")

final = C.req("GET", "/chefs?select=id,name").json()
final_rc = C.req("GET", "/restaurant_chefs?select=*").json()
print(f"\n=== FINAL ===")
print(f"Chefs: {len(final)}")
print(f"Associations: {len(final_rc)}")
