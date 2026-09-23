#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_phones.py —— 腾讯位置服务 SK 签名批量补电话（确定性，不编造）。

对库内 phone 为空的店，用品牌核心名调 place/v1/search（返回各分店 POI 含 tel），
再按"店名核心相似 + 地址路名/门牌相容"锚定具体分店，取其电话。
查不到 / 匹配弱 -> 留空，绝不硬凑、不用同名他店号码。

用法：
  python3 fill_phones.py --limit 30                 # 小样本验证
  python3 fill_phones.py                            # 全量（断点续跑，结果 merge 落盘）
  python3 fill_phones.py --apply                    # 把 high 置信电话 PATCH 写库（写前 clean_phone）
"""
import argparse
import difflib
import json
import pathlib
import re
import sys
import time

SKILL_PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SKILL_PIPE)
from tencent_sig import signed_get  # noqa: E402
import common as C  # noqa: E402

OUT = pathlib.Path("phone_result.json")
ROAD_RE = re.compile(r"([一-龥]{2,9}(?:路|街|大道|道|弄))(\d+)?")
MALL_TOK = ["广场", "万象城", "万象天地", "大悦城", "来福士", "恒隆", "太古里", "印象城", "合生汇",
            "日月光", "大丸", "环球港", "天地", "中心", "商场", "百货", "翡悦里", "WYSH", "太阳宫"]


def brand_core(s):
    s = str(s)
    s = re.split(r"[（(]", s)[0]
    m = re.search(r"[路街道里弄号镇]|广场|中心|商场|万象城|大悦城|来福士|恒隆|印象城|百货", s)
    if m:
        s = s[:m.start()]
    s = re.sub(r"(上海)?(全国首店|首店|分店|总店|直营店|旗舰店|店)$", "", s)
    return C.norm_name(s)


BAD_VENUE = ["K歌", "沐足", "足浴", "KTV", "ktv", "便利店", "超市", "服装", "美甲", "美发",
             "宾馆", "银行", "网吧", "棋牌", "健身", "药房", "药店", "地产", "中介", "营业厅",
             "会所", "酒店", "百货商场"]


def bad_venue(title):
    return any(b in str(title) for b in BAD_VENUE)


def core_match(a, b):
    """exact=品牌核心完全相等；fuzzy=近名(≥3字子串或相似度≥0.75)；None=不匹配。"""
    ca, cb = brand_core(a), brand_core(b)
    if not ca or not cb:
        return None
    if ca == cb:
        return "exact"
    if (ca in cb or cb in ca) and min(len(ca), len(cb)) >= 3:
        return "fuzzy"
    if difflib.SequenceMatcher(None, ca, cb).ratio() >= 0.75:
        return "fuzzy"
    return None


def addr_compatible(la, pa):
    """库址与POI址是否不矛盾（路名相同/同商场；至少一方无路名则无法证伪=True）。"""
    lr, _ = road_of(la)
    pr, _ = road_of(pa)
    if lr and pr and lr != pr:
        lm, pm = mall_of(la), mall_of(pa)
        return bool(set(lm) & set(pm))
    return True


SPEC_MALL = ["K11", "万象城", "万象天地", "来福士", "恒隆", "太古里", "太古汇", "大悦城",
             "合生汇", "环球港", "日月光", "百联", "万达", "翡悦里", "嘉里", "CP静安", "龙之梦",
             "印象城", "太阳宫", "仲盛", "近铁", "南丰城", "金虹桥", "金光绿庭", "大丸", "悦荟"]


def _anchors(s):
    a = set()
    r, _ = road_of(s)
    if r:
        a.add(r)
    for m in SPEC_MALL:
        if m in str(s):
            a.add(m)
    return a


def branch_conflict(name, addr, poi):
    """库(名+址)与POI(名+址)的分店锚点都存在且无交集 -> 错分店(降mid)；否则不冲突。"""
    A = _anchors(name) | _anchors(addr)
    B = _anchors(poi.get("title")) | _anchors(poi.get("address"))
    return bool(A and B and not (A & B))


def road_of(s):
    s = str(s).split("街道")[-1]
    m = ROAD_RE.search(s)
    if not m:
        return None, None
    return m.group(1), (int(m.group(2)) if m.group(2) else None)


def mall_of(s):
    return [t for t in MALL_TOK if t in str(s)]


def addr_confidence(lib_addr, poi_addr):
    """返回 high/mid/low：地址相容性。"""
    lr, ln = road_of(lib_addr)
    pr, pn = road_of(poi_addr)
    if lr and pr and lr == pr:
        if ln and pn:
            if abs(ln - pn) <= 15:
                return "high"
            return "low"
        return "mid"
    lm, pm = mall_of(lib_addr), mall_of(poi_addr)
    if lm and pm and set(lm) & set(pm):
        # 同商场，路名缺失/不一致 -> mid（不同铺位也可能同电话总机，谨慎）
        return "mid"
    if lr and pr and lr == pr:
        return "mid"
    return "low"


def search_pois(keyword):
    try:
        j = signed_get("/ws/place/v1/search",
                       {"keyword": keyword, "boundary": "region(上海,0)", "page_size": 10}).json()
    except Exception:
        return []
    return j.get("data", []) if j.get("status") == 0 else []


def nearby_pois(keyword, lat, lng, radius):
    """返回 (data, tencent_status)；status=121=当日 place search 配额耗尽。"""
    try:
        j = signed_get("/ws/place/v1/search",
                       {"keyword": keyword, "boundary": f"nearby({lat},{lng},{radius})",
                        "page_size": 20}).json()
    except Exception:
        return [], -1
    if not j:
        return [], -1
    return j.get("data", []), j.get("status")


def _out(rec, conf, c):
    return {"rid": rec["id"], "name": rec["name"], "conf": conf, "tel": c.get("tel"),
            "poi_title": c.get("title"), "poi_addr": c.get("address")}


def find_phone(rec):
    name, addr = rec["name"], rec.get("address") or ""
    core = brand_core(name)
    ll = C.parse_location(rec.get("location"))
    if ll:
        lng, lat = ll
        # 单次 nearby 300m（省配额：每家最多 1 次 search）
        data, st = nearby_pois(core or name, lat, lng, 300)
        if st == 121:
            return {"rid": rec["id"], "name": name, "conf": "quota", "tel": None,
                    "poi_title": None, "poi_addr": None}
        exact = fuzzy = None
        for c in data:
            if bad_venue(c.get("title", "")):
                continue
            m = core_match(name, c.get("title", ""))
            if m == "exact" and exact is None:
                exact = c
            elif m == "fuzzy" and fuzzy is None:
                fuzzy = c
        if exact is not None:
            return _out(rec, "mid" if branch_conflict(name, addr, exact) else "high", exact)
        if fuzzy is not None and addr_compatible(addr, fuzzy.get("address", "")):
            return _out(rec, "mid", fuzzy)
    return {"rid": rec["id"], "name": name, "conf": "none", "tel": None,
            "poi_title": None, "poi_addr": None}


def load_done():
    if OUT.exists():
        return {x["rid"]: x for x in json.loads(OUT.read_text())}
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.apply:
        rows = json.loads(OUT.read_text())
        n = 0
        for x in rows:
            if x["conf"] != "high" or not x.get("tel"):
                continue
            clean, issues, _ = C.clean_phone(x["tel"])
            if issues or not clean:
                continue
            r = C.req("PATCH", f"/restaurants?id=eq.{x['rid']}", json={"phone": clean})
            if r.status_code in (200, 201, 204):
                n += 1
            time.sleep(0.08)
        print(f"已写 high 电话 {n} 家")
        return

    rests = C.fetch_all("restaurants", "id,name,address,district,phone,location", order_col="id")
    todo = [r for r in rests if not r.get("phone")]
    done = load_done()
    if args.limit:
        todo = todo[:args.limit]
    results = dict(done)
    for i, rec in enumerate(todo, 1):
        if rec["id"] in done and not args.limit:
            continue
        x = find_phone(rec)
        if x["conf"] == "quota":
            print("⚠️ place search 日配额已耗尽，停止；进度已保存，配额重置后重跑本命令即续跑")
            break
        results[rec["id"]] = x
        if i % 20 == 0:
            OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=1))
        print(f"[{i}/{len(todo)}] {x['conf']:4} {rec['name']}  {x['tel'] or ''}")
        time.sleep(0.22)
    OUT.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=1))
    from collections import Counter
    c = Counter(x["conf"] for x in results.values())
    print("\n汇总（含历史断点）:", dict(c), "| high有tel:",
          sum(1 for x in results.values() if x["conf"] == "high" and x["tel"]))


if __name__ == "__main__":
    main()
