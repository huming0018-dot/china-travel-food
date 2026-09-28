#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_blackpearl_collect.py — 黑珍珠餐厅指南·上海全量权威连接器（确定性、默认 dry-run、可复跑）。

对齐米其林那一套（authority-recall 三件套），补 Phase 0-D 的 F2b 权威框缺口：
  1) 全量索引兜底：黑珍珠官方榜单不是前台翻页，而是美团点评官方 rank API
     （https://apimeishi.meituan.com/blackpearl/pc/rank/...，黑珍珠海外版 SPA home.js 逆向所得）。
     本连接器走该官方接口，按 cityId 分页穷举上海全量，不依赖会被裁剪的前台列表。
  2) 与官方总数对账：getSelectorList 返回的上海 shopCount 与 filterList 的 totalCount 双口径对账；
     采集数 < 官方总数直接报警、绝不静默（漏一家也要能解释发现路径）。
  3) 缺店强制闭环：与库内多别名归一（复用 authority_sitemap.make_matcher 四态
     exact/strong/weak/none；cjk 繁简异体 + 中文数字 + 品牌前缀）比对；
     exact/strong=在库，weak/short=待人工，none=真缺失（交 admission_gate 补录，不在此建店）。

铁律（宪法 A1/A2/A5）：
  - 只采信官方榜单（本接口即黑珍珠官方）+ 真实食客证据；媒体通稿不冒充 UGC。
  - 默认 dry-run：只抓官方名单落盘 + 与库对账，不写 restaurants、不建店。
  - --apply-tag 仅做一件事：给"在库且官方在榜(exact/strong)"的店幂等挂/补黑珍珠认证标签
    （cuisine_id=160，dimension=认证，口径对齐米其林 159）；不 detag、不改其它字段、不绑错分店。
  - 登录态：接口为黑珍珠海外版公开 web API（L2），点评 LANCE cookie 仅作礼貌携带/兜底，不硬刷。

用法（容器内，先 . /app/cloud/env.sh）：
  python3 cloud_blackpearl_collect.py                 # dry-run：抓官方名单 + 对账 + 与库四态比对
  python3 cloud_blackpearl_collect.py --apply-tag     # 自检通过后，幂等给在库在榜店补挂 160 标签
  python3 cloud_blackpearl_collect.py --limit-pages 2 # 调试：只拉前 N 页
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C  # noqa: E402
import authority_sitemap as S  # noqa: E402  (复用 make_matcher / core / slug_brand_cores)

COOKIE_F = pathlib.Path(os.environ.get("DIANPING_COOKIE_FILE",
                                       str(DATA / ".dianping_cookies.json")))
LIST_OUT = pathlib.Path(os.environ.get("BLACKPEART_LIST_OUT",
                                       str(DATA / "blackpearl_shanghai.json")))
RECON_OUT = pathlib.Path(os.environ.get("BLACKPEARL_RECON_OUT",
                                        str(DATA / "blackpearl_reconcile.json")))

API_HOST = "https://apimeishi.meituan.com"
EP_SELECTOR = "/blackpearl/pc/rank/getSelectorList"
EP_FILTER = "/blackpearl/pc/rank/filterList"
CITY_NAME = "上海"
DIAMOND_TAG_ID = 160          # cuisines: 黑珍珠餐厅, dimension=认证（已存在，无需 migration）
MICHELIN_TAG_ID = 159         # 口径对齐：认证宽口径（曾上榜），不 detag
SITE = "https://blackpearl.meituan.com/"

# 人工已核对照表白名单（entity_align confirmed 集）：
# 官方名无分隔符、品牌为短前缀，自动四态无法精确命中；但地址/品牌已与库内行逐字核实为同店。
# 每条必须能指到地址证据，禁止凭感觉加。命中后按 strong 挂标，不建店、不改其它字段。
#   key = 官方 shopName（与 filterList 返回逐字一致）；value = (db_id, 核实依据)
MANUAL_CONFIRM = {
    "徽季荣派徽菜": (1884,
        "官方名无分隔符（徽季+荣派徽菜）；库内 id=1884「徽季」地址=浦东新区世纪大道1788号"
        "陆家嘴金控广场V2号别墅，与 gap_blackpearl 证据地址逐字一致；新荣记集团首间徽菜，"
        "diner_quotes≥2、携程4.5，确认为同店。"),
}

# 分店错配排除表（near-miss → 真缺失，绝不挂错店）：
# core() 剥掉括号分店后缀后，多分店品牌会坍缩成同一核心名而误判 exact/strong。
# 经地址人工核对，下列官方店与匹配到的库内行是【同名异址分店 / 完全不同店】，
# 必须排除挂标，转真缺失进补录闭环。每条含被错配的 db_id 与地址依据。
BRANCH_MISMATCH = {
    "1929 by Guillaume Galliot餐厅": (517,
        "官方为外滩法式餐厅；自动误配到 id=517 莆田餐厅PUTIEN(世博源)，完全不同店。→ 真缺失"),
    "成隆行·颐丰花园(虹桥店)": (1385,
        "官方虹桥店(闵行)≠ id=1385 成隆行蟹王府(九江路店,黄浦)，同名异址分店。→ 真缺失"),
    "大董(环贸iapm店)": (1561,
        "官方环贸iapm店(徐汇)≠ id=1561 大董(国金中心IFC店,浦东)，不同分店。→ 真缺失"),
    "广舟(千禧店)": (654,
        "官方千禧店≠ id=654 广舟(巨鹿店)，不同分店。→ 真缺失"),
    "海味观(老西门店)": (1913,
        "官方老西门店(黄浦)≠ id=1913 海味观(静安)，不同分店。→ 真缺失"),
    "家全七福酒家(丰盛商业中心店)": (1468,
        "官方丰盛商业中心店≠ id=1468 家全七福(静安嘉里中心店)，不同分店。→ 真缺失"),
    "食廬NOBLE(凯德晶萃店)": (510,
        "官方凯德晶萃店≠ id=510 食庐NOBLE(港汇恒隆店)，不同分店。→ 真缺失"),
    "鲁采LU STYLE(新天地店)": (463,
        "官方新天地店≠ id=463 鲁采LU STYLE(环宇荟店)，不同分店。→ 真缺失"),
    "皖宴(苏河湾店)": (568,
        "官方苏河湾店≠ id=568 皖宴(龙柏饭店店)，不同分店。→ 真缺失"),
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
SLEEP_BETWEEN_PAGES = float(os.environ.get("BP_PAGE_SLEEP", "1.0"))


# ---------------------------------------------------------------- session
def load_session():
    s = requests.Session()
    if COOKIE_F.exists():
        try:
            cookies = json.loads(COOKIE_F.read_text(encoding="utf-8"))
            for c in cookies:
                s.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."))
        except Exception as e:  # cookie 坏了不阻断：海外版 API 为公开 L2
            print(f"[warn] 点评 cookie 读取失败，按公开匿名通道继续: {e}")
    s.headers.update({
        "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": SITE, "Origin": "https://blackpearl.meituan.com",
    })
    return s


def _post(s, ep, body, retries=4):
    last = None
    for i in range(retries):
        try:
            r = s.post(API_HOST + ep, json=body, timeout=25)
            j = r.json()
            # 黑珍珠官方 API 成功码为 200/message=succeed（非 0）
            if j.get("data") is not None and j.get("code") in (0, 200):
                return j
            last = j
        except Exception as e:
            last = repr(e)
        time.sleep(min(2 ** i, 8))
    raise RuntimeError(f"{ep} 连续失败: {last}")


# ---------------------------------------------------------------- 官方全量
def official_city(sess):
    """getSelectorList → 上海 cityId + 官方 shopCount（对账口径之一）。"""
    j = _post(sess, EP_SELECTOR,
              {"pcSelectorRequest": {"cityId": 0, "diamondLevel": 0,
                                      "selfCatId": 0, "newRankShop": 0},
               "commonRequest": {"language": "zh"}})
    for cc in j["data"]["countryCityInfoList"]:
        for c in cc["cityList"]:
            if CITY_NAME in c["cityName"]:
                return c["cityId"], c["shopCount"], c["cityName"]
    raise RuntimeError("getSelectorList 未找到城市: " + CITY_NAME)


def fetch_shanghai(sess, city_id, max_pages=20):
    """分页穷举上海全量；返回 (shops, totalCount)。"""
    shops, page, total = [], None, None
    for _ in range(max_pages):
        j = _post(sess, EP_FILTER,
                  {"pcRankListRequest": {"cityId": city_id, "sortType": 0, "lng": 0, "lat": 0,
                   "selfCatId": -1, "newRankShop": 0, "diamondLevel": 0,
                   "pageNum": page or 1, "pageSize": 100},
                   "commonRequest": {"language": "zh"}})
        d = j["data"]
        total = d.get("totalCount")
        lst = d.get("shopList") or []
        shops.extend(lst)
        cur_page = (page or 1)
        print(f"  page {cur_page}: +{len(lst)} totalCount={total} cum={len(shops)}", flush=True)
        if total is None or len(shops) >= total or not lst:
            break
        page = cur_page + 1
        time.sleep(SLEEP_BETWEEN_PAGES)
    return shops, total


def normalize_shop(x):
    """统一成与米其林名单一致的扁平 schema。"""
    return {
        "name": (x.get("shopName") or "").strip(),
        "shop_id": str(x.get("shopId") or ""),
        "diamond": x.get("diamondLevel"),           # 1/2/3 钻
        "cate": x.get("cateName") or "",            # 官方菜系大类
        "price": x.get("avgPriceDisplay") or "",
        "city": x.get("shopCountryCityName") or "中国 上海",
        "image": x.get("imageUrl") or "",
        "source_url": SITE,
    }


# ---------------------------------------------------------------- 与库四态比对
def _brand_aliases(name):
    """官方名常带场馆/菜系描述段（"上海柏悦酒店·悦轩"、"皇朝会.经典传统粤菜(外滩店)"），
    品牌藏在分隔符某一段。按 make_matcher 对 slug 品牌前缀的同一哲学，切出各分隔段作别名：
    整名 core 优先（精确不被短段抢），再补各段（去括号后）core；纯拉丁段也一并补。"""
    segs = [S.core(name)]
    # 先去括号分店后缀，再按 · . • ・ - — | 切品牌段
    stripped = re.sub(r"[（(].*?[)）]", "", name or "")
    for seg in re.split(r"[·•・.\-—–|｜]", stripped):
        seg = seg.strip()
        if not seg:
            continue
        c = S.core(seg)
        if c and S.eligible(c):
            segs.append(c)
    # 纯拉丁官方名（NABI / VIVANT）再补 slug 品牌前缀
    segs += list(S.slug_brand_cores((name or "").lower().replace(" ", "-")))
    # 去重保序
    seen, out = set(), []
    for c in segs:
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out


def reconcile(rows):
    rests = C.fetch_all("restaurants", "id,name,name_en,status,district", order_col="id")
    by_id = {r["id"]: r for r in rests}
    matcher = S.make_matcher(rests)
    out, missing, uncertain = [], [], []
    for r in rows:
        aliases = _brand_aliases(r["name"])
        m, conf = matcher(aliases)
        # 分店错配排除：地址已核为同名异址分店/错店，强制转真缺失，不挂标
        near_miss = None
        if r["name"] in BRANCH_MISMATCH:
            near_id, near_miss = BRANCH_MISMATCH[r["name"]]
            m, conf = None, "none"
        # 人工已核白名单：地址/品牌逐字核实为同店，按 strong 接管（仅覆盖自动 none/weak）
        if r["name"] in MANUAL_CONFIRM:
            cid, note = MANUAL_CONFIRM[r["name"]]
            m = by_id.get(cid)
            conf = "strong"
        if not S.eligible(S.core(r["name"])) and conf == "none":
            conf = "short"
        row = dict(r)
        row.update({"match_conf": conf,
                    "manual_confirm": MANUAL_CONFIRM.get(r["name"], [None, ""])[1] or None,
                    "near_miss": near_miss,
                    "matched_id": m["id"] if m else None,
                    "matched_name": m["name"] if m else None,
                    "matched_status": m["status"] if m else None})
        out.append(row)
        if conf == "none":
            missing.append(row)
        elif conf in ("weak", "short"):
            uncertain.append(row)
    return out, missing, uncertain


def existing_tagged_ids():
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    return {x["restaurant_id"] for x in rc if x["cuisine_id"] == DIAMOND_TAG_ID}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-tag", action="store_true",
                    help="给在库且官方在榜(exact/strong)的店幂等补挂黑珍珠标签160")
    ap.add_argument("--limit-pages", type=int, default=0)
    args = ap.parse_args()

    sess = load_session()
    print("=== 黑珍珠·上海 官方全量召回 ===")
    city_id, shop_count, city_name = official_city(sess)
    print(f"官方城市: {city_name} cityId={city_id} 官方 shopCount={shop_count}")

    shops, total = fetch_shanghai(sess, city_id)
    rows = [normalize_shop(x) for x in shops]

    # 三件套之二：总数对账（不静默）
    print(f"\n=== 总数对账 ===")
    print(f"selector.shopCount={shop_count}  filterList.totalCount={total}  实际采集={len(rows)}")
    problems = []
    if total is not None and len(rows) < total:
        problems.append(f"采集 {len(rows)} < 官方 totalCount {total}（可能分页截断/口径差异，需补页核对）")
    if shop_count and total and shop_count != total:
        problems.append(f"shopCount({shop_count}) != totalCount({total})（官方两口径不一致，需人工核对）")
    if problems:
        for p in problems:
            print("⚠ " + p)
    else:
        print("✓ 双口径一致，采集数=官方总数，无静默漏采")

    LIST_OUT.write_text(json.dumps({
        "guide": "黑珍珠餐厅指南", "city": city_name, "city_id": city_id,
        "official_shopCount": shop_count, "official_totalCount": total,
        "collected": len(rows), "diamond_dist": _dist(rows),
        "reconcile_problems": problems, "shops": rows,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写官方名单 {LIST_OUT}")

    # 与库四态比对
    print("\n=== 与库四态比对 ===")
    matched, missing, uncertain = reconcile(rows)
    from collections import Counter
    dist = Counter(r["match_conf"] for r in matched)
    in_db = dist.get("exact", 0) + dist.get("strong", 0)
    print(f"官方 {len(rows)}：exact={dist.get('exact',0)} strong={dist.get('strong',0)} "
          f"weak={dist.get('weak',0)} short={dist.get('short',0)} none={dist.get('none',0)}")
    print(f"在库(exact+strong)={in_db}；待确认(weak/short)={len(uncertain)}；真缺失(none)={len(missing)}")

    if uncertain:
        print("\n-- 待确认(weak/short) --")
        for r in uncertain:
            print(f"  [{r['match_conf']}] {r['name']}  ~ 候选 {r.get('matched_name')}(id={r.get('matched_id')})")
    if missing:
        print("\n-- 真缺失(none，交 admission_gate 补录闭环) --")
        for r in missing:
            print(f"  [{r['diamond']}钻] {r['name']}（{r['cate']}）")

    RECON_OUT.write_text(json.dumps({
        "official_shopCount": shop_count, "official_totalCount": total,
        "collected": len(rows), "in_db_exact_strong": in_db,
        "conf_dist": dict(dist),
        "missing": missing, "uncertain": uncertain, "all": matched,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已写对账 {RECON_OUT}")

    # 挂标（仅在库在榜，幂等；不 detag、不建店）
    if args.apply_tag:
        have = existing_tagged_ids()
        print(f"\n=== --apply-tag：当前已挂黑珍珠标签 {len(have)} 家 ===")
        added = 0
        for r in matched:
            if r["match_conf"] not in ("exact", "strong"):
                continue
            rid = r["matched_id"]
            if rid in have:
                continue
            pr = C.req("POST", "/restaurant_cuisines",
                       json={"restaurant_id": rid, "cuisine_id": DIAMOND_TAG_ID})
            if pr.status_code in (200, 201):
                added += 1
                have.add(rid)
                print(f"  + 挂标 [{rid}] {r['matched_name']}  <- 官方 {r['name']}")
            else:
                print(f"  ! 挂标失败 [{rid}] HTTP {pr.status_code} {pr.text[:120]}")
        # 回读核对
        now = existing_tagged_ids()
        print(f"本轮新增挂标 {added}；挂标后总数 {len(now)}")
        RECON_OUT.write_text(json.dumps({
            "official_shopCount": shop_count, "official_totalCount": total,
            "collected": len(rows), "in_db_exact_strong": in_db,
            "conf_dist": dict(dist), "tag_added_this_run": added,
            "tagged_total_after": len(now),
            "missing": missing, "uncertain": uncertain, "all": matched,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        print("\n(dry-run；加 --apply-tag 才给在库在榜店补挂标签，不建店/不改其它字段)")
    return 0


def _dist(rows):
    from collections import Counter
    return dict(Counter(r["diamond"] for r in rows))


if __name__ == "__main__":
    sys.exit(main())
