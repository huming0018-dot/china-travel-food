#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用腾讯 WebService 批量补坐标（强化版）：
多关键词(全名/品牌核心/英文/中文)聚合 suggestion 候选 → 地址·商场强匹配选分店 →
连锁无地址吻合标 ambiguous(不瞎选) → 实在无候选才 geocoder 兜底。只产出结果，不写库。"""
import json, math, re, sys, time, pathlib
import requests

KEY = "7PQBZ-7IDKZ-YUHXF-7V2GG-M2B3O-4OBT6"
BASE = "https://apis.map.qq.com"
HERE = pathlib.Path(__file__).parent
_PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, _PIPE)
import tencent_sig as TS  # noqa: E402
TASKS = HERE / "scene_coord_tasks.json"
OUT = HERE / "scene_coords_result.json"

MALL = (r"[一-龥A-Za-z0-9]+?(?:广场|购物中心|万象城|大悦城|日月光|来福士|恒隆|太古汇|太古里|"
        r"龙之梦|印象城|环宇城|环宇荟|久光|美罗城|太阳宫|大丸|百货|荟聚|瑞虹|鸿寿坊|慎余里|"
        r"环球港|合生汇|正大|国金|金融中心|仲盛|近铁|百联|万达|银泰|嘉里|南丰城|新世界|大融城|"
        r"宝龙|世茂|虹桥天地|欢乐颂|紫荆广场|领展广场|光环Live|公园巷|缤纷城|绿地缤纷)")


def norm(s):
    s = (s or "").lower()
    return re.sub(r"[\s·・•\-—_–'‘’\"“”`（）()【】\[\]]+", "", s)


def strip_admin(addr):
    s = re.sub(r"^上海市", "", str(addr))
    s = re.sub(r"^[一-龥]{2,4}?区", "", s)          # 开头行政区
    s = re.sub(r"[一-龥]+?(?:路街道|街道|镇|乡|社区)", "", s)  # 行政街道/镇
    return s


def addr_core(addr):
    if not addr:
        return ""
    s0 = strip_admin(addr)
    m = re.search(r"([一-龥A-Za-z0-9]+(?:路|街|道|村|公路)\d*[一-龥A-Za-z0-9]*?(?:\d+弄)?\d*号?)", s0)
    core = m.group(1) if m else re.sub(r"[（(].*?[)）]", "", s0)
    return re.sub(r"\s", "", core)


def road_of(core):
    m = re.match(r"([一-龥A-Za-z0-9]+(?:路|街|道))", core or "")
    return m.group(1) if m else None


def mall_of(addr):
    m = re.search(MALL, str(addr or ""))
    return m.group() if m else None


def suggest(keyword):
    try:
        r = TS.signed_get("/ws/place/v1/suggestion",
                          {"keyword": keyword, "region": "上海",
                           "region_fix": 1, "page_size": 10})
        j = r.json()
        return j.get("data", []) if j.get("status") == 0 else []
    except requests.RequestException:
        return []


def geocode(address):
    try:
        r = TS.signed_get("/ws/geocoder/v1/", {"address": address})
        j = r.json()
        return j.get("result") if j.get("status") == 0 else None
    except requests.RequestException:
        return None


def keywords(rec):
    n = rec["name"]
    ks = [n]
    core = re.split(r"[（(]", n)[0].strip()
    if core and core not in ks:
        ks.append(core)
    for e in re.findall(r"[A-Za-z][A-Za-z0-9'&.\- ]+", n):
        e = e.strip(" .&-")
        if len(e) >= 3 and e not in ks:
            ks.append(e)
    zh = "".join(re.findall(r"[一-龥]+", n))
    if zh and zh not in ks:
        ks.append(zh)
    # 去重保序，限5个
    out, seen = [], set()
    for k in ks:
        if k not in seen:
            seen.add(k); out.append(k)
    return out[:5]


def score_cand(c, rec, core_name):
    ct, nt, cn = norm(c.get("title")), norm(rec["name"]), norm(core_name)
    ns = 0
    if ct == nt or (cn and ct == cn):
        ns = 4
    elif cn and (cn in ct or ct in cn):
        ns = 2
    elif ct and (ct in nt or nt in ct):
        ns = 1
    cc, ac = addr_core(c.get("address")), addr_core(rec["address"])
    as_ = 0
    if cc and ac and cc == ac:
        as_ = 4
    elif road_of(cc) and road_of(ac) and road_of(cc) == road_of(ac):
        as_ = 2
    mc, ma = mall_of(c.get("address")), mall_of(rec["address"])
    if mc and ma and mc == ma:
        as_ = max(as_, 3)
    ds = 1 if (c.get("ad_info") or {}).get("district") == rec["district"] else 0
    return ns + as_ + ds, ns, as_


CHAIN_RE = re.compile(r"多区连锁|多家门店|多家直营|多店连锁|连锁（|连锁\(|等\s?\d+\s?家|全城配送")

# 确定性人工锚定（规则搞不定的别字/商圈/同建筑；坐标均可溯源到腾讯POI）
MANUAL_OVERRIDE = {
    1669: (31.153353, 121.472577, "江泳路86号POI（raw误写江永路）"),
    1692: (31.218889, 121.475038, "新天地南里POI"),
    1705: (31.210002, 121.457679, "襄阳南路298号POI"),
    1714: (31.20834, 121.476941, "蒙自路29号POI"),
    1668: (31.29600, 121.40758, "真大路520号米谷产业园（raw明确）"),
    1734: (31.23570, 121.48083, "南京东路505号海仑宾馆（候选同建筑）"),
}


def _meters(a, b):
    la, lb = a["location"], b["location"]
    dx = (la["lng"] - lb["lng"]) * 95000 * math.cos(math.radians(31.2))
    dy = (la["lat"] - lb["lat"]) * 111000
    return math.hypot(dx, dy)


def _multi_addr(addr):
    """多址聚合：连锁词；或去括号备注后，并列段里出现≥2个不同主路（连号同路/近路不算）。"""
    if CHAIN_RE.search(str(addr)):
        return True
    s = re.sub(r"[（(].*?[)）]", "", str(addr))   # 括号内是"近XX路/备注"，去掉
    parts = re.split(r"[/／、,，]", s)
    roads = set()
    for p in parts:
        m = re.search(r"[一-龥]{2,6}?(?:路|街)", p)
        if m:
            roads.add(m.group())
    return len(parts) >= 2 and len(roads) >= 2


def process(rec):
    if rec["rid"] in MANUAL_OVERRIDE:
        lat, lng, why = MANUAL_OVERRIDE[rec["rid"]]
        return {"rid": rec["rid"], "name": rec["name"], "status": "ok",
                "method": "manual_override", "matched_title": why, "lat": lat, "lng": lng}
    if _multi_addr(rec["address"]):
        return {"rid": rec["rid"], "name": rec["name"], "status": "multi_no_point",
                "note": "一条记录含多分店/多址，无单点坐标，需拆分"}
    core_name = re.split(r"[（(]", rec["name"])[0].strip()
    pool, by_id = [], {}
    for kw in keywords(rec):
        for c in suggest(kw):
            cid = c.get("id")
            if cid and cid not in by_id:
                by_id[cid] = 1; pool.append(c)
        time.sleep(0.18)
    scored = sorted(((score_cand(c, rec, core_name), c) for c in pool),
                    key=lambda x: -(x[0][0]))
    if scored:
        # 门牌完全吻合(as_==4)：地址即门牌，可直接认定，不强求名字分
        exact = [x for x in scored if x[0][2] == 4]
        if exact:
            top = exact[0][0][0]
            if sum(1 for x in exact if x[0][0] == top) == 1:
                return emit("ok", exact[0][1], "addr_exact")
            return ambiguous(exact[:4])
        # 地址相关(as>=2 路同) 且名字相关(ns>=2)：同路+品牌，唯一即认定
        addr_hit = [x for x in scored if x[0][2] >= 2 and x[0][1] >= 2]
        if addr_hit:
            top = addr_hit[0][0][0]
            tops = [x for x in addr_hit if x[0][0] == top]
            if len(tops) == 1:
                return emit("ok", tops[0][1], "addr_match")
            cs = [x[1] for x in tops]
            if all(_meters(cs[0], c) < 50 for c in cs[1:]):
                return emit("ok", cs[0], "same_building")  # 同建筑多楼层/写法
            return ambiguous(tops[:4])
        # 名字精确(ns>=4)、唯一、区一致或仅一个候选（独立非连锁店）
        name_hit = [x for x in scored if x[0][1] >= 4]
        if name_hit:
            if len(name_hit) == 1:
                return emit("ok", name_hit[0][1], "name_unique")
            # 连锁同名多店且无地址吻合 → 歧义，不瞎选
            return ambiguous(name_hit[:4])
    raw_addr = str(rec["address"])
    addr = raw_addr
    if not addr.startswith("上海市"):
        addr = "上海市" + rec["district"] + addr
    g = geocode(addr)
    if g and g.get("location"):
        loc, rel = g["location"], g.get("reliability") or 0
        if rel >= 6:  # 路弄级，可用
            return {"rid": rec["rid"], "name": rec["name"], "status": "ok_fallback",
                    "method": "geocoder", "matched_title": g.get("title"),
                    "lat": loc["lat"], "lng": loc["lng"], "reliability": rel}
        return {"rid": rec["rid"], "name": rec["name"], "status": "low_confidence",
                "note": f"geocoder可靠度仅{rel}，坐标留空待精确拾取", "cand": loc}
    return {"rid": rec["rid"], "name": rec["name"], "status": "miss"}


def emit(status, c, note):
    loc = c["location"]
    return {"rid": None, "name": None, "status": status, "method": "suggestion:" + note,
            "matched_title": c["title"], "address": c.get("address"), "tel": c.get("tel"),
            "lat": loc["lat"], "lng": loc["lng"]}


def ambiguous(items):
    return {"rid": None, "name": None, "status": "ambiguous",
            "candidates": [{"title": c["title"], "address": c.get("address"),
                            "lat": c["location"]["lat"], "lng": c["location"]["lng"]}
                           for (s, c) in items]}


def main():
    tasks = json.load(open(TASKS))
    results = []
    for i, rec in enumerate(tasks, 1):
        r = process(rec)
        r["rid"], r["name"] = rec["rid"], rec["name"]
        results.append(r)
        print(f"[{i}/{len(tasks)}] {r['status']} {rec['name']}")
        time.sleep(0.12)
    json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)
    from collections import Counter
    print("\n", dict(Counter(r["status"] for r in results)))
    for r in results:
        if r["status"] in ("ambiguous", "miss"):
            print(" ⚠", r["name"], [c["address"] for c in r.get("candidates", [])][:4])


if __name__ == "__main__":
    main()
