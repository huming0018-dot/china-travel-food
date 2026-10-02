#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud/kol_router.py — KOL 线索「验真 → 去重 → 分级路由」连接器（A2/A3/A4，默认 dry-run）。

为什么需要它：
  kol_monitor 把无法锚定的店名写为 food_kol_mentions(unmatched/ambiguous)，但实测 283 条
  unmatched 里大量是「希望店 / 锅底味道还行 / 正大广场店 / 号线世博会博物馆」这类**句子碎片或
  分店/地名**，并非真实新品牌；若直接喂给采集会造成污染和白烧。本连接器用确定性规则 + 地图
  POI 验真，把非实体剔除、把真实新店按「独立 KOL 声音数」分级，产出可进入口味核验的干净队列。

管线（只走 L0 免费地图通道，配额自守、断点续跑）：
  1. 拉 food_kol_mentions(unmatched/ambiguous) JOIN food_kol_posts(post_id→kol_id)；
  2. 碎片/地名/分店守卫 is_clean_brand → 得到品牌核心，否则记原因丢弃；
  3. 按品牌核心聚合，统计 distinct kol_id（独立声音）/ 极性 / raw 异写；
  4. 高德 POI 验真（amap_search，城市=上海，结果缓存、每候选只查一次）：
       无 POI → rejected(no_poi)；有同名 POI → verified，附带地址/坐标/电话；
  5. 与现有 restaurants 核心比对：已在库 → alias_link（交 name-link，不重复建）；
     全新 verified → 按独立声音分级写入 kol_lead_fill.json，等待「候选人口味核验→admission 建店」。

铁律：本连接器【绝不直接建 restaurants、绝不把 KOL 声音当口味】；KOL 仅作发现/特征线索。
      电话/坐标等事实只从选中 POI 取；宁空不假。配额耗尽(QUOTA_EXCEEDED)即停、保存进度。

用法：
  python3 kol_router.py                 # dry-run（守卫+聚合，不打地图、不写产物）
  python3 kol_router.py --verify        # 调地图验真（仍不写最终队列，只看结果）
  python3 kol_router.py --verify --apply
  python3 kol_router.py --verify --apply --max-check 40
"""
import argparse
import collections
import datetime
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
for p in (str(HERE), PIPE, str(HERE / "vendor" / "pipeline"), "/app/pipeline"):
    if p and p not in sys.path:
        sys.path.insert(0, p)

import requests  # noqa: E402
import common as C  # noqa: E402
import authority_sitemap as S  # noqa: E402
try:
    import map_helpers as M  # noqa: E402
except Exception:
    M = None

OUT_DIR = DATA / "research" / "kol"
STATE_F = OUT_DIR / "kol_router_state.json"
FILL_F = OUT_DIR / "kol_lead_fill.json"
REJECT_F = OUT_DIR / "kol_lead_rejected.jsonl"
ALIAS_F = OUT_DIR / "kol_alias_link.jsonl"

# 句子/功能/情绪词：出现即判定为「句子碎片」，不是品牌
_SENTENCE_CHARS = list("的了是我你他她它这那到去把被让在和跟与就也都还很最只能可会要想觉得看说提")
_SENTENCE_PHRASES = ["希望", "考虑", "包含", "只有", "免费", "续面", "味道", "水准", "突飞",
                     "步行", "博物馆", "科技馆", "提到", "这家", "那家", "一家", "楼下", "楼上",
                     "路口", "巷口", "朋友", "老板", "小哥", "姐姐", "今天", "昨天", "这次"]
# 纯地名/泛业态核心：不是品牌
_GENERIC_CORES = {"上海", "本帮", "本帮菜", "粤菜", "潮汕", "点心", "小吃", "美食", "餐厅",
                  "饭店", "餐馆", "广场", "正大", "南京路", "南京西路", "浦东", "徐汇", "黄浦",
                  "静安", "长宁", "闵行", "虹口", "杨浦", "普陀", "嘉定", "宝山", "松江", "青浦",
                  "奉贤", "金山", "崇明", "陆家嘴", "外滩", "新天地", "豫园", "城隍庙", "来福士",
                  "环贸", "太古汇", "国金", "恒隆", "合生汇", "世博", "世博会", "科技馆"}
# 分店/业态后缀（剥离后取品牌核心）
_BRANCH_TAIL = re.compile(
    r"(旗舰店|总店|分店|门店|新店|直营店|加盟店|[\u4e00-\u9fa5A-Za-z0-9]{0,8}?(?:广场|商场|购物中心|漫游城|国际|店))$")
_TAIL_HINT = re.compile(r"[\u4e00-\u9fa5A-Za-z·]{1,12}?(?:店|馆|餐厅|料理|小馆|面馆|坊|屋|舍|堂|楼|轩|居|铺|室|行|记|苑|阁)$")
# 地区/菜系前缀（剥离后若只剩纯品类词则非品牌）
_REGION_TOKENS = ["上海", "本帮", "东北", "西北", "潮汕", "台式", "台湾", "日本", "美式",
                  "泰国", "越南", "西班牙", "墨西哥", "浦东", "徐汇", "黄浦", "静安", "长宁",
                  "闵行", "虹口", "杨浦", "普陀", "嘉定", "宝山", "松江", "青浦", "奉贤",
                  "金山", "崇明", "京", "粤", "川", "鲁", "苏", "浙", "闽", "湘", "徽",
                  "日", "韩", "泰", "法", "意", "美", "德", "葡"]
_CATEGORY_WORDS = {"菜馆", "餐厅", "饭店", "餐馆", "料理", "面馆", "小吃", "点心", "美食",
                   "菜", "馆", "店", "小馆", "食堂", "牛排馆", "烧烤店", "烤肉店", "火锅店",
                   "串串店", "甜品店", "甜点店", "面包店", "蛋糕店", "烘焙店", "咖啡馆", "咖啡店",
                   "茶馆", "茶饮店", "酒吧", "酒馆", "寿司店", "拉面店", "饺子馆", "包子铺",
                   "烧腊店", "卤味店", "海鲜店", "龙虾店", "早餐店", "夜宵店", "快餐店", "咖喱店"}


def is_clean_brand(raw):
    """返回 (brand_core|None, reason)。确定性守卫，宁弃勿滥。"""
    s = (raw or "").strip()
    if not s:
        return None, "empty"
    # 取括号外主名（如 Madre(番禺路店) → Madre）
    main = re.split(r"[（(]", s, 1)[0].strip()
    # 反复剥离分店尾缀
    core0 = main
    for _ in range(3):
        nxt = _BRANCH_TAIL.sub("", core0).strip(" ·.-—")
        if not nxt:
            return None, "generic_place"          # 整串都是地名/分店（如「正大广场店」）
        if nxt == core0:
            break
        core0 = nxt
    cc = C.cjk_norm(core0)
    if not cc or len(cc) < 2:
        return None, "core_too_short"
    if any(ch in cc for ch in _SENTENCE_CHARS):
        return None, "sentence_fragment"
    if any(p in s for p in _SENTENCE_PHRASES):
        return None, "sentence_phrase"
    if cc in {C.cjk_norm(x) for x in _GENERIC_CORES}:
        return None, "generic_place"
    # 含商场/地标词且无独立品牌 → 地名
    if re.search(r"广场|商场|购物中心|漫游城|步行街|博物馆|科技馆", cc):
        return None, "generic_place"
    # 剥掉地区/菜系前缀后，若只剩纯品类词（如「上海本帮菜馆」→「菜馆」）→ 非品牌
    _t = cc
    for tok in _REGION_TOKENS:
        while _t.startswith(tok):
            _t = _t[len(tok):]
    if (not _t) or _t in _CATEGORY_WORDS:
        return None, "generic_place"
    if cc[0] in "号":
        return None, "generic_place"
    # 形态校验：原串应像「品牌 + 店型」
    if not _TAIL_HINT.search(main) and not re.search(r"[A-Za-z]{2,}", main):
        return None, "not_shop_form"
    try:
        ok, _why = C.looks_like_brand(core0)
    except Exception:
        ok = True
    if not ok:
        return None, "not_brand_like"
    return cc, "ok"


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"verified": {}, "runs": 0}


def save_state(st):
    STATE_F.parent.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def verify_poi(core, st):
    """高德验真：返回 (poi|None, status[verified/no_poi/non_food/quota/cached])。每核心只查一次。
    只接受餐饮服务 POI（typecode 以 05 开头），排除公证处/零售/住宿等非餐饮 POI。"""
    if core in st["verified"]:
        cached = st["verified"][core]
        return (cached or None), "cached"
    if M is None:
        return None, "no_map_module"
    try:
        pois = M.amap_search(core, offset=10)
    except Exception:
        return None, "map_error"
    if pois == "QUOTA_EXCEEDED":
        return None, "quota"
    best, best_s = None, 0.0
    for p in pois:
        tc = str(p.get("typecode") or "")
        if not tc.startswith("05"):
            continue                      # 非餐饮 POI（政府/零售/住宿…）
        pc = C.cjk_norm(p.get("title"))
        if not pc:
            continue
        sim = M.cjk_sim(pc, core) if hasattr(M, "cjk_sim") else (
            1.0 if core in pc or pc in core else 0.0)
        if core in pc or pc in core:
            sim = max(sim, 0.9)
        if sim > best_s:
            best_s, best = sim, p
    if best is None or best_s < 0.7:
        st["verified"][core] = None
        return None, "no_poi"
    poi = {"poi_id": best.get("id"), "title": best.get("title"),
           "address": best.get("address"), "tel": (best.get("tel") or ""),
           "typecode": best.get("typecode"),
           "lng": best.get("lng"), "lat": best.get("lat"), "sim": round(best_s, 2)}
    st["verified"][core] = poi
    return poi, "verified"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="调地图验真（默认只做守卫/聚合）")
    ap.add_argument("--apply", action="store_true", help="写出最终队列/账本")
    ap.add_argument("--max-check", dest="max_check", type=int, default=40)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    st = load_state()

    # ---- 现有餐厅核心索引（判断是否已在库）
    rests = C.fetch_all("restaurants", "id,name,name_en,status", order_col="id")
    db_cores = {}
    for r in rests:
        if r.get("status") == C.STATUS_CLOSED:
            continue
        for nm in (r.get("name"), r.get("name_en")):
            c = S.core(nm) if nm else ""
            if c and S.eligible(c):
                db_cores.setdefault(C.cjk_norm(c), r["id"])

    # ---- mentions JOIN posts(kol_id)
    posts = {p["id"]: p for p in C.fetch_all("food_kol_posts", "id,kol_id", order_col="id")}
    mens = C.fetch_all("food_kol_mentions",
                       "id,post_id,match_status,polarity,mentioned_raw,restaurant_id", order_col="id")
    open_ = [m for m in mens if m["match_status"] in ("unmatched", "ambiguous")]

    agg = {}
    rejected = []
    for m in open_:
        core, why = is_clean_brand(m["mentioned_raw"])
        if core is None:
            rejected.append({"mentioned_raw": m["mentioned_raw"], "reason": why,
                             "match_status": m["match_status"]})
            continue
        a = agg.setdefault(core, {"core": core, "kol_ids": set(), "pol": collections.Counter(),
                                  "raws": set()})
        kol_id = posts.get(m["post_id"], {}).get("kol_id")
        if kol_id is not None:
            a["kol_ids"].add(kol_id)
        a["pol"][m.get("polarity") or "neu"] += 1
        a["raws"].add(m["mentioned_raw"])

    # ---- 地图验真
    quota_stop = False
    checked = 0
    verified_new, alias_link = [], []
    for core, a in sorted(agg.items(), key=lambda kv: -len(kv[1]["kol_ids"])):
        if not args.verify:
            continue
        if core in st["verified"]:
            poi, status = verify_poi(core, st)
        else:
            if checked >= args.max_check:
                continue
            poi, status = verify_poi(core, st)
            checked += 1 if status in ("verified", "no_poi") else 0
            time.sleep(0.15)
        if status == "quota":
            quota_stop = True
            break
        if not poi:
            if status in ("no_poi", "cached") and st["verified"].get(core) is None:
                rejected.append({"mentioned_raw": sorted(a["raws"])[0], "reason": "no_poi",
                                 "core": core, "kol_voices": len(a["kol_ids"])})
            continue
        rid = db_cores.get(core)
        rec = {"core": core, "name": poi["title"], "poi_id": poi["poi_id"],
               "address": poi["address"], "lng": poi["lng"], "lat": poi["lat"],
               "tel": poi["tel"], "independent_kol_voices": len(a["kol_ids"]),
               "polarity": dict(a["pol"]), "raw_variants": sorted(a["raws"])}
        if rid is not None:
            rec["restaurant_id"] = rid
            alias_link.append(rec)
        else:
            # 分级：≥2 独立 KOL = A（2 名整理者声音，仍需食客口味）；1 个 = B（需再佐证）
            rec["grade"] = "A" if len(a["kol_ids"]) >= 2 else "B"
            verified_new.append(rec)

    # 按 poi_id 去重（异写核心可能指向同一 POI，如「苍蝇小馆」）
    def _dedup(rows):
        seen, out = set(), []
        for r in rows:
            k = r.get("poi_id")
            if k and k in seen:
                continue
            if k:
                seen.add(k)
            out.append(r)
        return out
    verified_new = _dedup(verified_new)
    alias_link = _dedup(alias_link)
    verified_new.sort(key=lambda r: (-r["independent_kol_voices"], r["name"]))

    # ---- 写出
    if args.apply:
        FILL_F.write_text(json.dumps(verified_new, ensure_ascii=False, indent=2), encoding="utf-8")
        with REJECT_F.open("w", encoding="utf-8") as f:
            for r in rejected:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with ALIAS_F.open("w", encoding="utf-8") as f:
            for r in alias_link:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        st["runs"] += 1
        st["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
        save_state(st)

    # ---- 报告
    rc = collections.Counter(r["reason"] for r in rejected)
    print("=" * 92)
    print(f"KOL 线索路由器 — verify={args.verify} apply={args.apply}")
    print("=" * 92)
    print(f"开放 mentions {len(open_)}；守卫通过候选 {len(agg)}；剔除 {len(rejected)} {dict(rc)}")
    if args.verify:
        print(f"本次地图新查 {checked}（缓存命中另计）；验真全新店 {len(verified_new)}"
              f"（A 级 {sum(1 for x in verified_new if x['grade']=='A')} / "
              f"B 级 {sum(1 for x in verified_new if x['grade']=='B')}）；已在库 alias {len(alias_link)}")
        for r in verified_new[:25]:
            print(f"  [{r['grade']}] {r['name']:<20} 独立KOL={r['independent_kol_voices']} "
                  f"{r['address'] or ''}")
        if quota_stop:
            print("  ⚠ 地图配额耗尽(QUOTA_EXCEEDED)，已保存进度，本轮停止（不硬刷）。")
    else:
        print("（未 --verify：仅守卫/聚合，不调地图；加 --verify 验真）")
        for core, a in list(sorted(agg.items(), key=lambda kv: -len(kv[1]['kol_ids'])))[:15]:
            print(f"  候选 {core:<16} 独立KOL={len(a['kol_ids'])} raws={len(a['raws'])}")
    if args.apply:
        print(f"\n写出：{FILL_F}\n      {REJECT_F}\n      {ALIAS_F}")


if __name__ == "__main__":
    main()
