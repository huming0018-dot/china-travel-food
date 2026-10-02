#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
candidate_chain_branchcount.py — 候选连锁「分店计数」自动判定器（免费，仅用高德，容器内运行）。

计数规则（防通名假阳性、防短词召回不稳）：
  对每个候选品牌做高德文本搜索，一个 POI 计为同品牌分店，当且仅当：
    - typecode 以 05 开头（餐饮）；
    - 标题含品牌【专属名 mark】（去通用品类后缀后的专名）；
    - mark 为 2 字时，还须与候选【同品类组】（如 拉面/面、火锅、牛杂、餐厅），
      排除「御香海/御香斋」这类同名异业。
  mark 无区分度（通用名，如 农场/农家）→ 不判连锁（independent + generic_mark）。
  搜索首次 0 结果时，用 mark 短词重试一次（高德短词/前缀召回更稳）。
  结论：n≥3 chain | n==2 small | n≤1 independent。
  以候选【name】为准（name 经高德验真、可靠；core 可能被上游截断）。

输入：/app/cloud/dianping_lead_fill.json、/app/data/research/kol/kol_lead_fill.json、
      /app/cloud/chain_brand_blocklist.json
输出：/app/data/research/candidate_chain_verdict.json
用法（容器，先 . /app/cloud/env.sh）：python3 candidate_chain_branchcount.py --apply
"""
import argparse
import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), str(HERE / "vendor" / "pipeline"), "/app/pipeline"):
    if p not in sys.path:
        sys.path.insert(0, p)

import map_helpers as MH  # noqa: E402
import common as C       # noqa: E402

OUT_DIR = pathlib.Path("/app/data/research")
DIAN_F = OUT_DIR / "dianping_lead_fill.json"
BLOCKLIST_F = OUT_DIR / "chain_brand_blocklist.json"
KOL_F = OUT_DIR / "kol" / "kol_lead_fill.json"
OUT_F = OUT_DIR / "candidate_chain_verdict.json"
STATE_F = OUT_DIR / "candidate_chain_branchcount_state.json"

CHAIN_MIN = 3

DISTRICT_RE = re.compile(
    r"^\s*(上海|黄浦|徐汇|静安|长宁|浦东|闵行|杨浦|虹口|普陀|嘉定|宝山|松江|青浦|奉贤|金山|崇明)[市区]?")
SEG_SPLIT_RE = re.compile(r"[·•・｜\-—]")

# 品类组：组 → (该组后缀列表, 标题中应出现的品类词列表)
GROUPS = {
    "restaurant": (["餐厅", "餐饮", "酒家", "酒楼", "饭店"], ["餐厅", "餐馆", "酒家", "酒楼", "饭店"]),
    "noodle": (["拉面馆", "拉面", "面馆", "面"], ["拉面", "面馆", "面", "面条"]),
    "bbq": (["烧烤", "烤串"], ["烧烤", "烤串", "烤肉"]),
    "hotpot": (["潮汕牛肉火锅", "潮汕鲜牛肉火锅", "牛肉火锅", "海鲜火锅", "寿喜烧", "火锅"],
               ["火锅", "寿喜烧"]),
    "sushi": (["寿司"], ["寿司"]),
    "cuisine": (["日式料理", "日本料理", "料理"], ["料理"]),
    "seafood": (["街头小海鲜", "小海鲜", "海鲜"], ["海鲜"]),
    "foodstore": (["食品"], ["食品"]),
    "canteen": (["食堂"], ["食堂"]),
    "porridge": (["粥庄", "粥"], ["粥"]),
    "bakery": (["烘焙"], ["烘焙", "面包"]),
    "cake": (["蛋糕"], ["蛋糕"]),
    "dessert": (["甜品", "点心"], ["甜品", "点心"]),
    "coffee": (["咖啡"], ["咖啡"]),
    "tea": (["茶饮", "奶茶"], ["茶", "奶茶"]),
    "winebar": (["中式小酒馆", "小酒馆", "酒馆"], ["酒馆"]),
    "xiaochi": (["小食"], ["小食"]),
    "offal": (["牛杂"], ["牛杂"]),
    "ricenoodle": (["花溪牛肉粉", "牛肉粉"], ["牛肉粉", "米粉"]),
    "soupdumpling": (["蟹粉小笼", "小笼", "小笼包"], ["小笼"]),
    "claypot": (["煲仔饭"], ["煲仔饭"]),
    "skewer": (["羊肉串"], ["羊肉串", "串"]),
    "private": (["私房菜"], ["私房菜"]),
    "teppanyaki": (["铁板烧"], ["铁板烧", "铁板"]),
    "pancake": (["饼"], ["饼"]),
    "weak": (["小厨", "小馆"], []),
}
SUFFIX_TO_GROUP, ALL_SUFFIXES = {}, []
for g, (su, _w) in GROUPS.items():
    for s in su:
        SUFFIX_TO_GROUP[s] = g
        ALL_SUFFIXES.append(s)
ALL_SUFFIXES.sort(key=len, reverse=True)
SUFFIX_RE = re.compile("(" + "|".join(map(re.escape, ALL_SUFFIXES)) + ")")

# 各组用于「品牌+品类」搜索的代表品类词
GROUP_QUERYWORD = {
    "restaurant": "餐厅", "noodle": "拉面", "bbq": "烧烤", "hotpot": "火锅",
    "sushi": "寿司", "cuisine": "料理", "seafood": "海鲜", "foodstore": "食品",
    "canteen": "食堂", "porridge": "粥", "bakery": "烘焙", "cake": "蛋糕",
    "dessert": "甜品", "coffee": "咖啡", "tea": "茶饮", "winebar": "酒馆",
    "xiaochi": "小食", "offal": "牛杂", "ricenoodle": "牛肉粉",
    "soupdumpling": "小笼", "claypot": "煲仔饭", "skewer": "羊肉串",
    "private": "私房菜", "teppanyaki": "铁板烧", "pancake": "饼", "weak": "",
}

GENERIC_MARKS = {
    "农场", "农家", "老街", "老地", "人民", "大食", "美食", "家常", "乡村", "本地",
    "老街坊", "老街口", "乡下", "私房", "食堂", "餐厅", "饭店", "小吃",
}
INDUSTRIAL_RE = re.compile(
    r"自助餐|宜家|大酒店|机场|服务区|高铁站?|景区内|风景区|环球影城|迪士尼|乐园|影城|员工食堂|连锁")


# ------------------------------------------------ 名称解析
def deparen(name):
    return re.sub(r"[（(][^）)]*[）)]", "", name or "")


def segments_of(name):
    return [s.strip(" ·•・-—") for s in SEG_SPLIT_RE.split(deparen(name)) if s.strip(" ·•・-—")]


def strip_district(s):
    m = DISTRICT_RE.match(s.strip())
    return s[m.end():].strip() if m else s.strip()


def han_of(s):
    return "".join(ch for ch in C.cjk_unify(s).lower() if "\u4e00" <= ch <= "\u9fff")


def latin_lead(s):
    m = re.match(r"([A-Za-z][A-Za-z0-9'&\-\. ]*)", s.strip())
    return re.sub(r"[^a-z0-9]", "", m.group(1).lower()) if m else ""


def analyze(name):
    segs = [strip_district(x) for x in segments_of(name)]
    full = "".join(segs) if segs else strip_district(deparen(name))
    han = han_of(full)
    cm = SUFFIX_RE.search(han)
    group = SUFFIX_TO_GROUP.get(cm.group(1)) if cm else None
    real_group = group if group not in (None, "weak") else None
    cat_words = GROUPS[group][1] if real_group else []
    # 汉字 mark（首段剥离品类后缀）
    seg0 = segs[0] if segs else full
    h0 = han_of(seg0)
    m0 = SUFFIX_RE.search(h0)
    hmark = h0[:m0.start()] if m0 else h0
    if len(hmark) >= 2:
        kind, mark = "han", hmark
    else:
        lmark = latin_lead(seg0)
        kind, mark = ("lat", lmark) if len(lmark) >= 3 else ("han" if hmark else "", hmark or lmark)
    distinctive = bool(mark) and (kind == "lat" or mark not in GENERIC_MARKS)
    # 主查询：首段已含品类→首段；否则 品牌+代表品类词
    if SUFFIX_RE.search(h0) or (kind == "lat" and seg0):
        primary = seg0
    elif real_group:
        primary = mark + GROUP_QUERYWORD[real_group]
    else:
        primary = mark
    return {"kind": kind, "mark": mark, "group": real_group, "cat_words": cat_words,
            "distinctive": distinctive, "primary": primary}


# ------------------------------------------------ 已知连锁
def load_blocklist():
    if not BLOCKLIST_F.exists():
        return set()
    try:
        return {C.cjk_norm(b) for b in
                json.loads(BLOCKLIST_F.read_text(encoding="utf-8")).get("cores", []) if b}
    except (json.JSONDecodeError, OSError):
        return set()


def known_chain(cand, blocklist):
    if INDUSTRIAL_RE.search(cand.get("name", "") + cand.get("address", "")):
        return "industrial_re"
    han = han_of(cand.get("name", ""))
    lat = re.sub(r"[^a-z]", "", C.cjk_unify(cand.get("name", "")).lower())
    for b in blocklist:
        if re.search(r"[\u4e00-\u9fff]", b):
            if len(b) == 2 and han.startswith(b):
                return b
            if len(b) >= 3 and b in han:
                return b
        elif len(b) >= 5 and b in lat:
            return b
    return None


# ------------------------------------------------ 候选 / 状态
def load_candidates():
    merged, seen_poi, seen_name = [], set(), set()

    def _add(rows, src):
        for c in rows or []:
            c = dict(c)
            c["_src"] = src
            poi, nm = c.get("poi_id"), C.cjk_norm(c.get("name", ""))
            if (poi and poi in seen_poi) or (nm and nm in seen_name):
                continue
            if poi:
                seen_poi.add(poi)
            if nm:
                seen_name.add(nm)
            merged.append(c)

    if DIAN_F.exists():
        _add(json.loads(DIAN_F.read_text(encoding="utf-8")), "dianping")
    if KOL_F.exists():
        _add(json.loads(KOL_F.read_text(encoding="utf-8")), "kol")
    return merged


def load_json(p, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def poi_matches(info, poi):
    if not str(poi.get("typecode", "")).startswith("05"):
        return False
    title = poi.get("title", "")
    if info["kind"] == "han":
        if info["mark"] not in han_of(title):
            return False
    elif info["kind"] == "lat":
        if info["mark"] not in re.sub(r"[^a-z0-9]", "", C.cjk_unify(title).lower()):
            return False
    else:
        return False
    # 已知品类组：要求同品类词共现（防通名/异业假阳性）
    if info["cat_words"] and not any(w in han_of(title) for w in info["cat_words"]):
        return False
    return True


def search_and_count(info):
    queries = [info["primary"]]
    if info["mark"] and info["mark"] != info["primary"]:
        queries.append(info["mark"])        # 空结果时短词重试
    seen, samples, quota = set(), [], False
    for qi, q in enumerate(queries):
        if not q:
            continue
        pois = MH.amap_search(q)
        if pois == "QUOTA_EXCEEDED":
            quota = True
            continue
        if not pois and qi < len(queries) - 1:
            time.sleep(1.2)
            continue
        for p in pois:
            if poi_matches(info, p) and p.get("id") not in seen:
                seen.add(p.get("id"))
                samples.append(p.get("title", ""))
        break
    return (None if quota and not seen else len(seen)), samples[:6], quota


def verdict_of(info, n):
    if not info["distinctive"]:
        return "independent"
    # 2 字汉字短名且品类组不明 → 无法消歧，保守不判连锁
    if info["kind"] == "han" and len(info["mark"]) == 2 and not info["group"]:
        return "independent"
    return "chain" if n >= CHAIN_MIN else "small" if n == 2 else "independent"


def export_auto_chains(items):
    """把计数确认的连锁 mark 回写清单 auto_cores，供 candidate_verify 花费前拦截。"""
    auto = set()
    for it in items.values():
        if it.get("verdict") == "chain" and it.get("mark") and it.get("n_branches"):
            auto.add(C.cjk_norm(it["mark"]))
    if not auto:
        return
    data = {"cores": [], "auto_cores": []}
    if BLOCKLIST_F.exists():
        try:
            data = json.loads(BLOCKLIST_F.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    data.setdefault("cores", [])
    merged = sorted({C.cjk_norm(x) for x in data.get("auto_cores", [])} | auto)
    data["auto_cores"] = merged
    BLOCKLIST_F.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已回写 auto_cores {len(merged)} 条 → {BLOCKLIST_F}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    blocklist = load_blocklist()
    cands = load_candidates()
    verdict = load_json(OUT_F, {"updated_at": "", "items": {}})
    state = load_json(STATE_F, {"done": []})
    done, items = set(state["done"]), verdict["items"]

    c_known = c_chain = c_small = c_indep = c_pending = 0
    quota_hit = False
    for c in cands:
        name = c.get("name", "")
        key = c.get("poi_id") or C.cjk_norm(name)
        kh = known_chain(c, blocklist)
        if kh:
            items[key] = {"name": name, "verdict": "chain", "reason": f"known:{kh}",
                          "n_branches": None}
            c_known += 1
            continue
        if key in done and key in items and items[key].get("verdict") in ("chain", "small", "independent"):
            v = items[key]["verdict"]
            c_chain += v == "chain"; c_small += v == "small"; c_indep += v == "independent"
            continue
        info = analyze(name)
        if not args.apply:
            c_pending += 1
            continue
        n, samples, quota = search_and_count(info)
        if quota and n is None:
            quota_hit = True
            break
        v = verdict_of(info, n)
        items[key] = {"name": name, "mark": info["mark"], "cat_words": info["cat_words"],
                      "distinctive": info["distinctive"], "verdict": v,
                      "n_branches": n, "sample_branches": samples}
        done.add(key)
        c_chain += v == "chain"; c_small += v == "small"; c_indep += v == "independent"
        print(f"[{v:11s}] n={n} mark={info['mark']!r:10s} {name}")
        time.sleep(0.6)

    if args.apply:
        verdict["updated_at"] = C.today()
        OUT_F.write_text(json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
        state["done"] = sorted(done)
        STATE_F.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        export_auto_chains(items)

    print("\n=== 候选连锁判定汇总 ===")
    print(f"已知连锁(清单/正则): {c_known}")
    print(f"连锁(≥{CHAIN_MIN}): {c_chain} | 小型(2): {c_small} | 独立(≤1): {c_indep}")
    if c_pending:
        print(f"待判定(需 --apply): {c_pending}")
    if quota_hit:
        print("⚠ 高德配额耗尽，已存进度，配额重置后续跑。")
    print(f"verdict 总条目: {len(items)}")


if __name__ == "__main__":
    main()
