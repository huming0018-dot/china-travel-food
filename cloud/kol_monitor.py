#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud/kol_monitor.py — Phase 0-E：KOL 名单监控连接器（长期连接器，A4/A5/A2）。

职责（连接器化 / 增量 / 幂等 / 可复跑，默认 dry-run）：
  1. 遍历 food_kol_watchlist 里的 active KOL，按平台用对应 keyless 通道拉近期内容；
  2. 每条新内容归档 food_kol_posts（post_url 唯一，merge-duplicates 幂等）；
  3. 从标题+简介里锚定「提到的店」：
       - 高置信（核心名唯一，或连锁分店被正文区/路名消歧到唯一一家）→ 写 restaurant_id, match_status=matched；
       - 连锁多分店但正文未消歧 / 弱匹配 → restaurant_id 留空, match_status=ambiguous（绝不猜绑、绝不绑错分店）；
       - 不像库内店、但像真实店名的线索 → match_status=unmatched, restaurant_id 留空，路由进 discovery 池交 admission_gate，
         本连接器【绝不直接插 restaurants】。
  4. 每 KOL 游标 last_pub_ts + seen_bvids 落 /app/data/kol_monitor_state.json，只处理新内容，重跑不重复写。
  5. 默认 dry-run 只打印逐 KOL 报告；--apply 才写 food_kol_posts / food_kol_mentions + 路由线索文件。

通道现状（实测 2026-09-28）：
  - bilibili：keyless 搜索接口 x/web-interface/search/all/v2（Referer=search.bilibili.com）code=0 可用；
    按 KOL 名 + order=pubdate 拉近期视频，再用 author==name(归一) 且 mid 一致严格归属，防错绑 UP 主。
    space/wbi arc/search 在本数据中心 IP 返回 -403/-352 风控，不可用 → 不硬刷。
  - cross（沈宏非/殳俏/陈晓卿…跨媒介美食作家）：无 keyless 单渠道，登记但不自动轮询（manual）。
  - xiaohongshu：两账号 web_session 均 -100，F4 停摆；当前 watchlist 无 xhs KOL，XHS 部分标「待账号恢复」。

铁律对齐：提及只是【特征线索/发现入口】，绝不计入 taste（北极星唯一使命=真实堂食口味）。
只写 food_kol_posts / food_kol_mentions；restaurants 表零变化；新候选一律经 admission_gate。
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
import datetime
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import requests  # noqa: E402
import common as C  # noqa: E402
import authority_sitemap as S  # noqa: E402

STATE_F = DATA / "kol_monitor_state.json"
DISC_DIR = DATA / "discovery"
LEAD_F = DISC_DIR / "raw_kol.jsonl"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all/v2"
API_HEADERS = {"User-Agent": UA, "Referer": "https://search.bilibili.com"}

# 口味词（归属窗口情感判定；服务/情绪/环境词刻意不收）——与 kol_post_ingest 同源口径
POS_WORDS = ["好吃", "惊艳", "香", "嫩滑", "鲜嫩", "鲜美", "正宗", "地道", "回购", "入味",
             "酥脆", "浓郁", "满足", "天花板", "锅气", "层次", "软糯", "回甘", "值得", "现炒"]
NEG_WORDS = ["难吃", "踩雷", "失望", "齁咸", "腥", "发柴", "预制", "不新鲜", "寡淡",
             "嚼不烂", "糊了", "变质", "雷区", "不推荐", "徒有虚名"]

# 上海相关性：本图鉴只服务上海。正文有上海信号→保留；无上海信号但点了外地城市→丢弃。
SH_SIGNALS = ("上海", "静安", "徐汇", "黄浦", "浦东", "前滩", "长宁", "闵行", "虹口",
              "杨浦", "普陀", "嘉定", "宝山", "松江", "青浦", "奉贤", "巨鹿", "武康",
              "安福", "乌鲁木齐", "进贤", "复兴中路", "新天地", "太古汇", "国金", "恒隆",
              "环贸", "iapm", "IAPM", "南京西路", "淮海", "陆家嘴", "徐家汇", "人民广场",
              "外滩", "豫园", "思南", "永康路", "巨鹿路", "愚园", "张园", "西岸", "北外滩")
OUT_TOWNS = set(C.OUT_CITIES) | {"济南", "兰州", "青岛", "大连", "厦门", "福州", "无锡",
                                "宁波", "佛山", "东莞", "泉州", "温州", "台州", "常州",
                                "合肥", "昆明", "贵阳", "洛阳", "三亚", "丽江", "大理",
                                "哈尔滨", "长春", "沈阳", "太原", "石家庄", "南昌", "南宁",
                                "海口", "贵阳", "无锡", "苏州", "无锡"}

MIN_INTERVAL = 1.2          # B站搜索限速
MAX_VIDEOS_PER_KOL = 20     # 搜索接口单页上限


# --------------------------------------------------------------------------- 工具
def strip_em(s):
    return re.sub(r"</?em[^>]*>", "", str(s or "")).strip()


def shanghai_relevant(title, desc):
    """只保留有【明确上海信号】的视频（路名/区/地标）。
    KOL 全国探店居多；本图鉴只服务上海，无上海信号的月饼/外地/泛话题一律不产 mentions/线索（A2 宁空不假）。"""
    t = f"{title or ''} {desc or ''}"
    return any(w in t for w in SH_SIGNALS)


def polarity_for(seg):
    p = sum(w in seg for w in POS_WORDS)
    n = sum(w in seg for w in NEG_WORDS)
    if p and not n:
        return "pos"
    if n and not p:
        return "neg"
    if p and n:
        return "mixed"
    return "neu"


# --------------------------------------------------------------------------- 库索引
def build_rest_index():
    """core(剥括号归一) -> [rest 行]（保留连锁分店多行，不折叠）。只收 active。"""
    rests = C.fetch_all("restaurants", "id,name,name_en,address,district,status", order_col="id")
    active = [r for r in rests if r.get("status") in (None, "active")]
    core2rests = defaultdict(list)
    for r in active:
        for nm in (r.get("name"), r.get("name_en")):
            if not nm:
                continue
            c = S.core(nm)
            if c and S.eligible(c):
                core2rests[c].append(r)
    return active, core2rests


def anchor_mentions(text_raw, core2rests):
    """从正文里抽「库内店」提及并锚定。返回 (matched_rows, ambiguous_rows)。

    matched_rows: [{restaurant_id, mentioned_raw, polarity}]
    ambiguous_rows: [{restaurant_id:None, mentioned_raw, polarity}]
    分店消歧：连锁多分店时，仅当正文出现某分店的区/路/门牌线索才绑；否则留空。
    """
    cn = C.cjk_norm(text_raw)
    if not cn:
        return [], []
    # 最长核心优先，去重叠
    hits = []
    for core, rests in core2rests.items():
        pos = cn.find(core)
        if pos < 0:
            continue
        hits.append((pos, core, rests))
    hits.sort(key=lambda x: -len(x[1]))
    kept = []
    used_spans = []
    for pos, core, rests in hits:
        s, e = pos, pos + len(core)
        if any(not (e <= a or s >= b) for a, b in used_spans):
            continue  # 与更长命中重叠
        used_spans.append((s, e))
        kept.append((s, e, core, rests))
    kept.sort()

    matched, ambiguous = [], []
    for i, (s, e, core, rests) in enumerate(kept):
        win_end = kept[i + 1][0] if i + 1 < len(kept) else len(cn)
        seg = cn[s:win_end]
        pol = polarity_for(seg)
        if len(rests) == 1:
            matched.append({"restaurant_id": rests[0]["id"],
                            "mentioned_raw": rests[0]["name"], "polarity": pol})
            continue
        # 连锁多分店：用正文里的区/路线索消歧
        disamb = []
        for r in rests:
            addr = f"{r.get('address') or ''}{r.get('district') or ''}"
            hints = re.findall(r"[一-龥]{2,7}?(?:路|街|道|区|村|号)", addr)
            if any(h and h in text_raw for h in hints):
                disamb.append(r)
        if len(disamb) == 1:
            matched.append({"restaurant_id": disamb[0]["id"],
                            "mentioned_raw": disamb[0]["name"], "polarity": pol})
        else:
            # 不猜绑：留空，标 ambiguous（保留代表名与 raw 窗口）
            ambiguous.append({"restaurant_id": None,
                              "mentioned_raw": rests[0]["name"], "polarity": pol})
    return matched, ambiguous


# 未知店名线索（候选路由）：只取干净的「专名+店型后缀」，剔除动词/语气/元话术碎片。
_LEAD_STOP = set("这那我你他她它其每某本各另去吃午晚早称之的在是有和跟把被让从向往到")
_LEAD_FILLER = ("大家", "谢谢", "祝", "推荐", "评论", "店铺", "淘宝", "微信", "搜索", "师傅",
                "姐姐", "小哥", "朋友", "老板", "一家", "这家", "那家", "起来", "一口",
                "今天", "昨天", "这次", "上次", "到底", "为什么", "怎么", "什么",
                "居民区", "楼下", "楼上", "巷口", "路口")
_RE_SHOP = re.compile(
    r"([一-龥A-Za-z][一-龥A-Za-z&·]{1,10}?"
    r"(?:饭店|餐馆|餐厅|小馆|料理|面馆|面馆|店|馆|坊|屋|舍|堂|楼|轩|居|铺|室|行|记|苑|阁))")


def extract_leads(title, desc, known_cores):
    out, seen = [], set()
    for txt in (title or "", desc or ""):
        for m in _RE_SHOP.findall(txt):
            name = m.strip(" ：:，。、！？!?,./～~·-（）()")
            if len(name) < 3 or len(name) > 12:
                continue
            if name[0] in _LEAD_STOP:
                continue
            if any(f in name for f in _LEAD_FILLER):
                continue
            ok, why = C.looks_like_brand(name)
            if not ok:
                continue
            k = C.cjk_norm(name)
            if not k or k in seen:
                continue
            if k in known_cores:        # 库内已有 → 不算新候选
                continue
            # 与库内核心互为子串也视为已知，避免重复路由
            if any(len(k) >= 4 and (k in c or c in k) for c in known_cores):
                continue
            seen.add(k)
            out.append(name)
    return out


# --------------------------------------------------------------------------- 通道
def fetch_bili_videos(kol):
    """按 KOL 名搜索近期视频，严格 author 归属。返回 (vids, err)。"""
    try:
        r = requests.get(SEARCH_API, params={"keyword": kol["name"], "page": 1, "order": "pubdate"},
                         headers=API_HEADERS, timeout=20)
        j = r.json()
    except Exception as e:
        return [], f"请求异常 {e}"
    if j.get("code") != 0:
        return [], f"code={j.get('code')} msg={j.get('message')}（风控/限流）"
    vids = []
    mid = kol.get("mid")
    for blk in (j.get("data") or {}).get("result", []):
        if blk.get("result_type") != "video":
            continue
        for v in blk.get("data", []):
            author = v.get("author") or ""
            if C.cjk_norm(author) != C.cjk_norm(kol["name"]):
                continue  # 严格归属，防同名 UP 主错绑
            if mid and v.get("mid") and int(v["mid"]) != int(mid):
                continue
            vids.append({
                "bvid": v.get("bvid") or "",
                "title": strip_em(v.get("title")),
                "desc": (v.get("description") or v.get("desc") or "").strip(),
                "created": int(v.get("pubdate") or v.get("senddate") or 0),
                "url": f"https://www.bilibili.com/video/{v.get('bvid')}",
                "author": author,
            })
    return vids[:MAX_VIDEOS_PER_KOL], None


# --------------------------------------------------------------------------- 状态
def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"kols": {}, "runs": 0}


def save_state(st):
    STATE_F.parent.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------- 写库（仅 apply）
def upsert_post(rec):
    h = dict(C.headers())
    h["Prefer"] = "resolution=merge-duplicates,return=representation"
    r = requests.post(C.BASE + "/food_kol_posts?on_conflict=post_url", headers=h, json=rec, timeout=45)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"post upsert {r.status_code}: {r.text[:200]}")
    rep = r.json()
    if isinstance(rep, list) and rep:
        return rep[0]["id"]
    g = requests.get(C.BASE + f"/food_kol_posts?post_url=eq.{rec['post_url']}&select=id",
                     headers=C.headers(), timeout=30).json()
    return g[0]["id"]


def upsert_mentions(rows):
    if not rows:
        return 0
    h = dict(C.headers())
    h["Prefer"] = "resolution=merge-duplicates"
    r = requests.post(C.BASE + "/food_kol_mentions?on_conflict=post_id,mentioned_raw",
                      headers=h, json=rows, timeout=45)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"mention upsert {r.status_code}: {r.text[:200]}")
    return len(rows)


# --------------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写库（默认 dry-run）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个可轮询 KOL（调试）")
    args = ap.parse_args()
    apply = args.apply

    DISC_DIR.mkdir(parents=True, exist_ok=True)
    _, core2rests = build_rest_index()
    known_cores = set(core2rests.keys())
    kols = C.fetch_all("food_kol_watchlist",
                       "id,name,platform,status,mid,kol_type", order_col="id",
                       extra="status=eq.active")
    st = load_state()

    report = {"mode": "apply" if apply else "dry-run", "kols": [],
              "totals": {"searched": 0, "new_videos": 0, "sh_relevant": 0,
                         "matched": 0, "ambiguous": 0, "leads": 0,
                         "posts_written": 0, "mentions_written": 0,
                         "blocked": 0, "no_channel": 0}}
    lead_buf = []

    pollable = [k for k in kols if k.get("platform") == "bilibili"]
    skipped = [k for k in kols if k.get("platform") != "bilibili"]
    if args.limit:
        pollable = pollable[:args.limit]

    for kol in skipped:
        report["kols"].append({"id": kol["id"], "name": kol["name"], "platform": kol["platform"],
                               "status": "no_channel",
                               "note": "cross-media 权威/作家，无 keyless 单渠道，登记不自动轮询"})
        report["totals"]["no_channel"] += 1

    for kol in pollable:
        kid = str(kol["id"])
        kst = st["kols"].setdefault(kid, {"last_pub_ts": 0, "seen_bvids": []})
        seen = set(kst.get("seen_bvids", []))
        rec = {"id": kol["id"], "name": kol["name"], "platform": "bilibili"}
        vids, err = fetch_bili_videos(kol)
        report["totals"]["searched"] += 1
        if err:
            rec.update({"status": "blocked", "note": err})
            report["totals"]["blocked"] += 1
            report["kols"].append(rec)
            time.sleep(MIN_INTERVAL)
            continue

        new = [v for v in vids if v["bvid"] not in seen]
        sh_new = [v for v in new if shanghai_relevant(v["title"], v["desc"])]
        rec.update({"status": "ok", "fetched": len(vids), "new": len(new), "sh_relevant": len(sh_new),
                    "matched": 0, "ambiguous": 0, "leads": 0, "posts": 0, "mentions": 0})

        for v in sh_new:
            text = f"{v['title']}。{v['desc']}"
            matched, ambiguous = anchor_mentions(text, core2rests)
            leads = extract_leads(v["title"], v["desc"], known_cores)
            rec["matched"] += len(matched)
            rec["ambiguous"] += len(ambiguous)
            rec["leads"] += len(leads)
            report["totals"]["new_videos"] += 1
            report["totals"]["sh_relevant"] += 1
            report["totals"]["matched"] += len(matched)
            report["totals"]["ambiguous"] += len(ambiguous)
            report["totals"]["leads"] += len(leads)

            if apply:
                pub = (datetime.datetime.fromtimestamp(v["created"])
                       .replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))).isoformat()
                       if v["created"] else None)
                post_id = upsert_post({
                    "kol_id": kol["id"], "platform": "bilibili", "post_url": v["url"],
                    "title": v["title"], "summary": v["desc"][:500], "published_at": pub,
                    "raw_mentions": [m["mentioned_raw"] for m in matched + ambiguous]})
                rec["posts"] += 1
                rows = []
                for m in matched:
                    rows.append({"post_id": post_id, "restaurant_id": m["restaurant_id"],
                                 "mentioned_raw": m["mentioned_raw"], "match_status": "matched",
                                 "polarity": m["polarity"]})
                for a in ambiguous:
                    rows.append({"post_id": post_id, "restaurant_id": None,
                                 "mentioned_raw": a["mentioned_raw"], "match_status": "ambiguous",
                                 "polarity": a["polarity"]})
                for ld in leads:
                    rows.append({"post_id": post_id, "restaurant_id": None,
                                 "mentioned_raw": ld, "match_status": "unmatched",
                                 "polarity": "neu"})
                n = upsert_mentions(rows)
                rec["mentions"] += n
                report["totals"]["posts_written"] += 1
                report["totals"]["mentions_written"] += n
                # 候选路由：线索进 discovery 池（不直接插 restaurants）
                if leads:
                    lead_buf.append({"kind": "discover", "category": "kol",
                                     "query": kol["name"], "city": "上海", "source": "bilibili",
                                     "notes": [{"title": v["title"], "desc": v["desc"],
                                                "author": v["author"], "url": v["url"],
                                                "leads": leads}]})

            seen.add(v["bvid"])
            if v["created"] > kst.get("last_pub_ts", 0):
                kst["last_pub_ts"] = v["created"]

        kst["seen_bvids"] = sorted(seen)
        report["kols"].append(rec)
        time.sleep(MIN_INTERVAL)

    # 候选路由文件（仅 apply）
    if apply and lead_buf:
        with LEAD_F.open("a", encoding="utf-8") as f:
            for r in lead_buf:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 游标/状态只在 apply 持久化；dry-run 绝不推进游标（否则下次 apply 会漏这批视频）
    if apply:
        st["runs"] = st.get("runs", 0) + 1
        st["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
        st["last_mode"] = report["mode"]
        save_state(st)

    # ---------------------------------------------------------------- 打印报告
    print("=" * 96)
    print(f"KOL 监控连接器 — {report['mode']}")
    print("=" * 96)
    for r in report["kols"]:
        if r["status"] == "ok":
            print(f"  [ok] {r['name']:<16} 拉{r['fetched']:<3} 新{r['new']:<3} "
                  f"沪{r['sh_relevant']:<3} matched={r['matched']:<2} ambig={r['ambiguous']:<2} "
                  f"leads={r['leads']:<2} 写入post={r['posts']} mention={r['mentions']}")
        elif r["status"] == "blocked":
            print(f"  [阻塞] {r['name']:<16} {r['note']}")
        else:
            print(f"  [无通道] {r['name']:<14} {r['note']}")
    t = report["totals"]
    print("-" * 96)
    print(f"合计：可轮询KOL={t['searched']} 无通道={t['no_channel']} 阻塞={t['blocked']}")
    print(f"      新视频={t['new_videos']}(沪相关{t['sh_relevant']}) "
          f"matched={t['matched']} ambiguous={t['ambiguous']} 候选线索={t['leads']}")
    if apply:
        print(f"      写库：food_kol_posts +{t['posts_written']}，food_kol_mentions +{t['mentions_written']}"
              f"（restaurants 零变化；候选线索→{LEAD_F} 待 admission_gate≥2独立声音）")
    else:
        print("      (dry-run 未写库；--apply 才写 food_kol_posts/food_kol_mentions 并路由候选线索)")

    out = DATA / "kol_monitor_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写 {out}")


if __name__ == "__main__":
    main()
