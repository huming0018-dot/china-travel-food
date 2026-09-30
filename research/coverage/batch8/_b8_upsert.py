#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch8 coverage expansion — bounded round (2026-09-30).
Thinnest leaves targeted: 乌冬(236/275) / 荞麦(261/272) / 日式面包(309).
Admission: >=2 independent voices + taste evidence + >=1 signature dish.
Conservative: only name/name_en/status/address/price_avg; NO location/phone/hours/score.
Idempotent: name-core + address dedup; read-back assert. dry-run default; --apply writes.
"""
import sys, json, time, pathlib
sys.path.insert(0, "/app/pipeline")
import common as C

NEW_SHOPS = [
    {
        "name": "田口家·手打乌冬(禧瑞广场店)",
        "name_en": "Taguchi Teuchi Udon",
        "fields": {"status": C.STATUS_OPEN,
                   "address": "上海市长宁区延安西路2088号禧瑞广场F1层",
                   "price_avg": 122},
        "cids_add": [85, 236, 275],
        "evidence": "喜都乃旗下手打乌冬专门店；招牌五彩手打乌冬(墨鱼/原味/番茄/紫苏/抹茶)，面比一般乌冬粗更有嚼劲，琥珀色鲣鱼清汤底；溏心鸡肝。高德4.6/人均122。",
        "source_urls": [
            "https://m.ctrip.com/webapp/you/community/detail?articleId=325352329",
            "https://www.iesdouyin.com/share/video/7579884120768495729",
            "https://www.iesdouyin.com/share/video/7532416694963981628",
        ],
        "discovery_path": "F5地图POI(高德:延安西路2088号禧瑞广场F1,4.6,人均122) + F4社交框(携程笔记x3/抖音古北清单)",
    },
    {
        "name": "立食荞麦东京一味",
        "name_en": "Tokyo Ichimi Tachigui Soba",
        "fields": {"status": C.STATUS_OPEN,
                   "address": "上海市黄浦区瑞金一路161号",
                   "price_avg": 65},
        "cids_add": [85, 261, 272],
        "evidence": "上海首家/唯一立食荞麦店，东京老板+上海老板娘；去壳荞麦粉二八面，3分钟出餐，荞麦香扎实、咸鲜海鲜汤底、回味微苦；光面28元。高德4.6/人均65。(抖音口述名'荞本家/养本家'经模糊召回§7对齐到本名)",
        "source_urls": [
            "https://www.bilibili.com/video/BV1wQQJYhEKX/",
            "https://m.thepaper.cn/newsDetail_forward_29772713",
            "https://www.iesdouyin.com/share/video/7548339044158164259",
        ],
        "discovery_path": "F4社交框(B站立食荞麦vlog点名瑞金一路161号) + D媒体层(澎湃/魔都吃货小分队) + F5地图POI(高德4.6,人均65)",
    },
    {
        "name": "都恩客(高岛屋店)",
        "name_en": "DONQ",
        "fields": {"status": C.STATUS_OPEN,
                    "address": "上海市长宁区虹桥路1438号高岛屋百货B1"},
        "cids_add": [301, 309],
        "evidence": "1905年神户创立的百年日式面包连锁，上海13年；招牌巨无霸法棍(每天18段限量)、明太子法棍、盐面包；用料扎实无网红元素。(连锁，多店，仅标高岛屋老店)",
        "source_urls": [
            "https://www.iesdouyin.com/share/video/7654232151625572218",
            "https://www.bilibili.com/video/BV1FbW4zQEbZ/",
            "https://m.mafengwo.cn/mweng/wengdetail/?id=1657260453375163",
        ],
        "discovery_path": "F4社交框(抖音13年老店+B站巨无霸法棍攻略+马蜂窝)；日式面包叶309",
    },
]

def existing_cids(rid):
    r = C.req("GET", f"/restaurant_cuisines?select=cuisine_id&restaurant_id=eq.{rid}")
    return {x["cuisine_id"] for x in r.json()}

def add_link(rid, cid):
    have = existing_cids(rid)
    if cid in have:
        return "already"
    rr = C.req("POST", "/restaurant_cuisines", json={"restaurant_id": rid, "cuisine_id": cid})
    if rr.status_code in (200, 201): return "added"
    if "23505" in rr.text: return "already"
    return f"ERR:{rr.status_code}:{rr.text[:120]}"

def main():
    apply = "--apply" in sys.argv
    print(f"=== {'APPLY' if apply else 'DRY-RUN'} ===")
    rests = C.fetch_all("restaurants", "id,name,address,status", order_col="id")
    created = []
    for ns in NEW_SHOPS:
        core = ns["name"].split("(")[0]
        dup = [r for r in rests if C.norm_name(core) in C.norm_name(r["name"]) or
               C.norm_name(r["name"]) in C.norm_name(core)]
        already = None
        for r in dup:
            if ns["fields"]["address"][:10] in (r.get("address") or ""):
                already = r
        if already:
            rid = already["id"]
            print(f"[EXISTS] {ns['name']} -> rid={rid}, ensuring links {ns['cids_add']}")
            if apply:
                for cid in ns["cids_add"]:
                    res = add_link(rid, cid); assert cid in existing_cids(rid)
                    print("   link", cid, res)
            created.append({"name": ns["name"], "rid": rid, "action": "link_existing"})
            continue
        print(f"[{'COMMIT' if apply else 'PLAN'} NEW] {ns['name']} ({ns.get('name_en')}) addr={ns['fields']['address']} cids={ns['cids_add']}")
        if not apply:
            created.append({"name": ns["name"], "action": "new_plan"})
            continue
        fields = dict(ns["fields"]); fields["name"] = ns["name"]
        if ns.get("name_en"): fields["name_en"] = ns["name_en"]
        h = dict(C.headers(True)); h["Prefer"] = "return=representation"
        rr = requests.post(C.BASE + "/restaurants", headers=h, json=fields, timeout=45)
        rid = None
        if rr.status_code in (200, 201) and rr.json():
            d = rr.json(); rid = d[0]["id"] if isinstance(d, list) else d["id"]
        if rid is None:
            g = C.req("GET", "/restaurants?select=id,name&name=eq."+requests.utils.quote(ns["name"])+"&order=id.desc")
            if g.json(): rid = g.json()[0]["id"]
        assert rid, f"POST failed {rr.status_code} {rr.text[:200]}"
        for cid in ns["cids_add"]:
            res = add_link(rid, cid); assert cid in existing_cids(rid), f"readback fail cid {cid}"
            print("   link", cid, res); time.sleep(0.1)
        rb = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,name").json()
        assert rb and rb[0]["id"] == rid
        created.append({"name": ns["name"], "rid": rid, "action": "new_created"})
        time.sleep(0.3)
    print("\n=== RESULT ===")
    print(json.dumps(created, ensure_ascii=False, indent=2))

import requests
if __name__ == "__main__":
    main()
