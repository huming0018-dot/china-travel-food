#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""events_build.py — 「最新动向」采集 raw → 可入库 food_events 行（纯 python / REST，Bash 运行）。

输入：research/social/raw_events_collected.jsonl（events_collect 产出，sweep/watch）
配置：research/social/listen_keywords.json
输出：research/social/raw_events.jsonl         （对齐 atlas_write EVENT_COLS + expires_on）
      research/social/new_shops_unmatched.jsonl（锚不到库的中文新店，待补收录）

确定性机制（不靠模型拍脑袋）：
1. 事件分类：正文/标题命中词根（去 negative）；sweep 须正文验证 category_hint，watch 全词根扫描。
2. 合集不锚单一店：≥2 库内非参照店 / ≥2"地址：" / ≥2 📍 / 标题"N场·合集·盘点·攻略" → 丢弃（联名 A×B 除外）。
3. 餐饮域闸：须命中食物/餐饮词；命中服装·潮玩·钟表·桌游·地产观察等且无食物 → 丢弃。
4. 每篇独立锚主体（教训 #56）：全名/品牌形式/core_unique + 商场分店冲突；联名/快闪 A×B、A携手B、
   A快闪@B → restaurant=A、related=B。
5. 海外/限时品牌不在库（本就是新的）：popup/collaboration/guest_kitchen/new_open/coming_soon 若正文有
   拉丁字母品牌 + 餐饮信号 → 允许 restaurant_id 空也成事件（品牌写入标题/摘要），先 rumor、多源再 verified。
6. 源分层（common.source_kind + 官方作者标记）：T1 官方 / T2 媒体 / T3 KOL / T4 地图。
7. 多源合并 + 置信度函数化：≥1 T1 或 ≥2 独立 T2/T3 = high(verified)，否则 mid(rumor)。
8. 时效：限时类取正文结束日（含"限时N个月/N天"），否则 event_date+默认窗口 → expires_on；feed_view 自动下沉。
9. 去重：同 (category, 主体, event_date) 合并 sources；与库内 food_events 对齐跳过。
"""
import sys
import json
import re
import pathlib
import datetime
from collections import Counter

SP = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SP)
import common as C

BASE = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"
RAW_P = BASE + "/research/social/raw_events_collected.jsonl"
CFG_P = BASE + "/research/social/listen_keywords.json"
OUT_P = BASE + "/research/social/raw_events.jsonl"
NEW_P = BASE + "/research/social/new_shops_unmatched.jsonl"

# ------------------------------------------------ 加载库 / 配置
cfg = json.loads(pathlib.Path(CFG_P).read_text(encoding="utf-8"))
CATS = cfg["categories"]
PRIORITY = cfg["category_priority"]
DISCOUNT_RE = re.compile("|".join(re.escape(x) for x in cfg["discard_signals"]))
OFFICIAL_MARK = cfg["official_author_markers"]
FOOD_RE = re.compile("|".join(re.escape(x) for x in cfg["food_domain"]["food_signals"]))
NONFOOD = cfg["food_domain"]["nonfood_signals"]

rests = C.fetch_all("restaurants", "id,name,status,district,address")
chefs = C.fetch_all("chefs", "id,name")
lib_events = C.fetch_all("food_events", "id,category,restaurant_id,event_date,title")
TODAY = datetime.date.today()

# ------------------------------------------------ 文本工具
def norm(s):
    return C.norm_name(s)

def strip_branch(s):
    return re.sub(r"（.*?）|\(.*?）", "", s or "").strip()

_GEO = ("上海|北京|武汉|四川|重庆|成都|广州|湖南|湖北|河南|江苏|浙江|云南|贵州|安徽|山东|"
        "福建|广东|陕西|新疆|江西|广西|海南|绵阳|泸州|自贡|潮汕|潮州|顺德|客家|港式|温州|"
        "杭州|宁波|无锡|南京|苏州|绍兴|嘉兴|台州|镇江|扬州|桂林")
_CATW = ["米粉","热干面","牛肉面","牛肉汤","胡辣汤","铜锣烧","卤菜","寿司","拉面","烧肉","咖喱",
         "咖啡","面馆","烤肉","烧烤","火锅","饺子","包子","甜品","料理","餐厅","饭店","酒楼",
         "酒家","餐室","小馆","酒馆","老铺"]

def forms_of(r):
    full = strip_branch(r["name"])
    out = {full}
    if "·" in full:
        out.add(full.split("·")[0])
    m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{1,4}记)", full)
    if m:
        out.add(m.group(1))
    s = re.sub(_GEO, "", full)
    for w in _CATW:
        s = s.replace(w, "")
    s = re.sub(r"[·・•\s]+", "", s).strip()
    if s and len(s) >= 2:
        out.add(s)
    return [f for f in out if f and len(f) >= 2]

by_norm, form_owners = {}, {}
for r in rests:
    by_norm.setdefault(norm(r["name"]), []).append(r)
    for f in set(forms_of(r)):
        form_owners.setdefault(f, set()).add(r["id"])
unique_form = {f: next(iter(ids)) for f, ids in form_owners.items() if len(ids) == 1}
rid_by_id = {r["id"]: r for r in rests}
chef_by_name = {norm(c["name"]): c["id"] for c in chefs}

MALLS = ["美罗城","新天地","国金中心","IFC","恒隆广场","恒隆","太古汇","兴业太古汇","静安嘉里",
         "嘉里中心","来福士","大悦城","万象城","合生汇","日月光","正大广场","港汇","龙之梦","ITC",
         "前滩太古里","太古里","万达","环球港","久光","晶品","芮欧","K11","环贸","iapm","金鹰",
         "梅龙镇","中信泰富","大丸","正大乐城","今潮8弄","北外滩来福士"]
def malls_in(t):
    return {m for m in MALLS if m in (t or "")}

REF_PAT = re.compile(r"(?:还是|不如|没[^。，]{0,4}好吃|比[^。，]{0,4}好吃|相比|对比|相较于|论[^。，]{0,3}我只服)")

def scan_shops(text):
    hits = {}
    for r in rests:
        full = strip_branch(r["name"])
        sc = 0
        if full and len(full) >= 3 and full in text:
            sc = 3
        nf = norm(full)
        if len(nf) >= 3 and nf in norm(text):
            sc = max(sc, 2)
        for f in forms_of(r):
            ok = len(f) >= 3 or (len(f) >= 2 and unique_form.get(f) == r["id"])
            if ok and f in text:
                sc = max(sc, 1)
        if sc and (r["id"] not in hits or hits[r["id"]][1] < sc):
            hits[r["id"]] = (r["name"], sc)
    return hits

def match_id(name):
    if not name:
        return None
    ex = by_norm.get(norm(name))
    if ex:
        act = [x for x in ex if x["status"] == "active"] or ex
        return act[0]["id"]
    core = norm(strip_branch(name))[:6]
    if len(core) < 2:
        return None
    h = [r for r in rests if core in norm(r["name"])]
    return h[0]["id"] if len(h) == 1 else None

# ------------------------------------------------ 分类
def classify(text, hint):
    found = []
    for cat in PRIORITY:
        c = CATS[cat]
        neg = any(n in text for n in c.get("negative", []))
        hit = any(root.lower() in text.lower() for root in c["roots"])
        if hit and not neg:
            found.append(cat)
    if not found:
        return None
    return hint if hint in found else found[0]

# ------------------------------------------------ 联名双店
def collab_pair(text, cat):
    if cat not in ("collaboration", "popup"):
        return None
    pats = [
        r"([\u4e00-\u9fa5A-Za-z0-9·&]{2,20})\s*[×xX]\s*([\u4e00-\u9fa5A-Za-z0-9·&]{2,20})",
        r"([\u4e00-\u9fa5A-Za-z0-9·&]{2,20})\s*(?:携手|与|联合|联名|合作)[^。，]{0,8}([\u4e00-\u9fa5A-Za-z0-9·&]{2,20})",
        r"([\u4e00-\u9fa5A-Za-z0-9·&]{2,20})[^。，]{0,6}(?:快闪|popup|pop-up)[^。，]{0,8}(?:@|在|登陆|现身|入驻)([\u4e00-\u9fa5A-Za-z0-9·&]{2,20})",
    ]
    for p in pats:
        m = re.search(p, text)
        if m:
            a, b = match_id(m.group(1)), match_id(m.group(2))
            if a or b:
                return (a, b)
    return None

# ------------------------------------------------ 文本分析（合集/锚定）
def analyze(text, target_name):
    shops = scan_shops(text)
    refs = set()
    for rid, (nm, sc) in list(shops.items()):
        for mm in REF_PAT.finditer(text):
            if nm and nm in text[mm.start():mm.start() + 24]:
                refs.add(rid)
    nonref = {rid: v for rid, v in shops.items() if rid not in refs}
    addr_blocks = len(re.findall(r"地址[：:]", text))
    pin_count = len(re.findall(r"📍", text))
    roundup_words = re.search(r"\d+\s*场|合集|盘点|攻略|速递|承包|大盘点|看这篇就够|活动日历|本月|清单", text)
    roundup = (len(nonref) >= 2 or addr_blocks >= 2 or pin_count >= 2
               or bool(roundup_words) and (pin_count >= 1 or len(nonref) >= 1))
    anchor, mall_conflict = None, False
    tgt_rid = match_id(target_name) if target_name else None
    if tgt_rid is not None:
        tr = rid_by_id[tgt_rid]
        in_text = strip_branch(target_name) in text or any(f in text for f in forms_of(tr))
        m_shop, m_text = malls_in(tr["name"] + (tr["address"] or "")), malls_in(text)
        if m_shop and m_text and not (m_text & m_shop):
            mall_conflict = True
        if in_text and not mall_conflict:
            anchor = tgt_rid
    return {"shops": shops, "refs": refs, "nonref": nonref, "roundup": roundup,
            "anchor": anchor, "mall_conflict": mall_conflict, "tgt_rid": tgt_rid}

# ------------------------------------------------ 餐饮域 / 拉丁品牌
def food_domain(text):
    has_food = bool(FOOD_RE.search(text))
    strong_nonfood = sum(1 for w in NONFOOD if w in text)
    if strong_nonfood and not has_food:
        return False
    return has_food

STOP_EN = {"the","and","for","you","your","with","menu","chef","open","new","this","season",
           "limited","shanghai","space","hotel","coming","soon","guest","table","official",
           "brand","pop","popup","culture","yard","city","food","restaurant","dining","bar"}
def latin_brands(text):
    out, seen = [], set()
    for m in re.finditer(r"[A-Za-z][A-Za-z&'’.]{2,30}", text):
        w = m.group(0).strip("&'’. ")
        if len(w) >= 3 and w.lower() not in STOP_EN and (any(c.isupper() for c in w) or "&" in w) \
           and w not in seen:
            seen.add(w); out.append(w)
    return out

DISTRICT_HINTS = {
    "黄浦区": ["外滩", "南京东路", "人民广场", "新天地", "豫园"],
    "静安区": ["静安寺", "南京西路", "恒隆", "张园", "兴业太古汇", "巨鹿路"],
    "徐汇区": ["徐家汇", "安福路", "武康路", "湖南路", "衡复", "徐汇滨江"],
    "长宁区": ["古北", "黄金城道", "中山公园"],
    "浦东新区": ["陆家嘴", "前滩", "国金", "世纪大道", "浦东滨江"],
    "虹口区": ["北外滩", "四川北路", "今潮"],
}
def guess_district(text):
    for d, kws in DISTRICT_HINTS.items():
        if any(k in text for k in kws):
            return d
    return None

# ------------------------------------------------ 日期
def parse_date(s):
    s = (s or "").strip()
    m = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", s)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    m = re.search(r"(?<!\d)(\d{1,2})[-./](\d{1,2})(?!\d)", s)
    if m:
        return datetime.date(TODAY.year, int(m.group(1)), int(m.group(2))).isoformat()
    if "前天" in s:
        return (TODAY - datetime.timedelta(days=2)).isoformat()
    if "昨天" in s:
        return (TODAY - datetime.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*天前", s)
    if m:
        return (TODAY - datetime.timedelta(days=int(m.group(1)))).isoformat()
    if "今天" in s or "刚刚" in s or "小时前" in s or "分钟前" in s:
        return TODAY.isoformat()
    return TODAY.isoformat()

def parse_end(text, ev_date, default_days):
    ed = datetime.date.fromisoformat(ev_date)
    # 1) 明确时长（"限时/持续/为期 N 个月/天"，最可靠）
    m = re.search(r"(?:限时|持续|为期)\s*(\d+)\s*个月", text)
    if m:
        return (ed + datetime.timedelta(days=30 * int(m.group(1)))).isoformat()
    m = re.search(r"(?:限时|持续|为期)\s*(\d+)\s*天", text)
    if m:
        return (ed + datetime.timedelta(days=int(m.group(1)))).isoformat()

    def valid(mm, dd):
        try:
            cand = datetime.date(ed.year, mm, dd)
        except ValueError:
            return None
        if cand < ed:  # 结束日早于开始日 → 顺延一年
            try:
                cand = datetime.date(ed.year + 1, mm, dd)
            except ValueError:
                return None
        return cand.isoformat()

    # 2) 结束日月日（候选须晚于开始日）
    m = re.search(r"(?:至|到|截止[到至]?|until|till|through)[^0-9]{0,4}(\d{1,2})[月./-](\d{1,2})\s*日?", text)
    if m:
        v = valid(int(m.group(1)), int(m.group(2)))
        if v:
            return v
    m = re.search(r"(\d{1,2})[月./-](\d{1,2})\s*(?:截止|结束|收官|落幕|止)", text)
    if m:
        v = valid(int(m.group(1)), int(m.group(2)))
        if v:
            return v
    # 3) 默认窗口
    if default_days:
        return (ed + datetime.timedelta(days=default_days)).isoformat()
    return None

# ------------------------------------------------ 源层 / 平台
def platform_name(url):
    for k, v in [("xiaohongshu","小红书"),("mp.weixin","微信公众号"),("douyin","抖音"),
                 ("dianping","大众点评"),("bilibili","B站"),("weibo","微博"),
                 ("guide.michelin","米其林指南"),("blackpearl","黑珍珠")]:
        if k in (url or "").lower():
            return v
    return "网络"

def note_tier(kind, author):
    if kind in ("brand", "official_guide") or any(mk in (author or "") for mk in OFFICIAL_MARK):
        return "T1"
    if kind == "media":
        return "T2"
    if kind == "map":
        return "T4"
    return "T3"

def clean_title(t):
    return re.sub(r"\s+", " ", re.sub(r"#\S+", "", t or "")).strip()[:60]

# ------------------------------------------------ 主循环
agg, new_shops, dropped = {}, [], []
seen_note = set()
ALLOW_NULL = {"new_open", "coming_soon", "popup", "collaboration", "guest_kitchen"}

for line in pathlib.Path(RAW_P).read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    rec = json.loads(line)
    target, hint = rec.get("watch_name"), rec.get("category_hint")
    for note in rec.get("notes", []):
        url = note.get("url") or ""
        if url in seen_note:
            continue
        seen_note.add(url)
        title = note.get("title", "")
        text = title + "\n" + note.get("desc", "")
        author = note.get("author", "")
        body = re.sub(r"#\S+", "", note.get("desc", "")).replace("\u200b", " ").strip()

        if DISCOUNT_RE.search(text):
            dropped.append((url, "招聘/加盟/招商噪声")); continue
        cat = classify(text, hint)
        if cat is None:
            dropped.append((url, "无事件词根")); continue
        az = analyze(text, target)
        pair = collab_pair(text, cat)
        if az["roundup"] and pair is None:
            dropped.append((url, "合集/盘点不锚单一店")); continue
        if not food_domain(text):
            dropped.append((url, "非餐饮域（服装/潮玩/钟表/桌游/地产）")); continue

        anchor, related = az["anchor"], None
        if pair:
            anchor, related = pair
        if anchor is None and len(az["nonref"]) == 1:
            only_rid = next(iter(az["nonref"]))
            only_name = strip_branch(az["nonref"][only_rid][0])
            brands_here = latin_brands(text)
            pshop = text.find(only_name)
            pbrand = min((text.find(b) for b in brands_here if text.find(b) >= 0), default=-1)
            if pbrand >= 0 and (pshop < 0 or pbrand < pshop):
                # 海外品牌在正文更靠前=真正主体（走 rid=null），库内店只是场地/关联
                related = only_rid
            else:
                anchor = only_rid
        if any(s in text for s in cfg["not_status_evidence"]) and cat in ("new_open", "menu_update"):
            dropped.append((url, "预订/外卖残留非事件")); continue

        scope = "local"
        if cat in ("new_open", "coming_soon") and re.search(
                r"(海外|国外|外国|日本|法国|意大利|美国|纽约|东京|巴黎|首尔|伦敦|新加坡|泰国|韩国).{0,10}(首店|来华|登陆|落沪|入驻|开业)", text):
            scope = "overseas"
        kind = C.source_kind(author + " " + body, url)
        tier = note_tier(kind, author)
        ev_date = parse_date(note.get("date"))
        src = {"platform": platform_name(url), "author": author[:20], "title": clean_title(title),
               "url": url, "date": ev_date, "tier": tier}

        if anchor is None:
            brands = latin_brands(text)
            if cat in ALLOW_NULL and brands:
                bk = brands[0]
                key = f"{cat}|B:{bk}|{ev_date}"
                district = guess_district(text)
                rid = None
            else:
                if cat in ALLOW_NULL:
                    new_shops.append({"search": target or rec.get("query"), "title": title,
                                      "url": url, "date": ev_date, "note": "中文新店未在库，待补收录"})
                dropped.append((url, "锚不到库内主体")); continue
        else:
            rid = anchor
            key = f"{cat}|{rid}|{ev_date}"
            district = rid_by_id[rid].get("district")

        if key not in agg:
            agg[key] = {"category": cat, "scope": scope, "rid": rid, "related": related,
                        "district": district, "sources": [src], "text": text,
                        "title_raw": title, "ev_date": ev_date}
        else:
            agg[key]["sources"].append(src)
            if related:
                agg[key]["related"] = related

# ------------------------------------------------ 置信度 / 组装
def independent(sources):
    cand, seen = [], set()
    for s in sources:
        k = (s["platform"], s["author"])
        if k not in seen:
            seen.add(k); cand.append(s)
    clusters = []
    for s in cand:
        head = norm(s["title"])[:10]
        for cl in clusters:
            if head and head == cl["head"]:
                cl["items"].append(s); break
        else:
            clusters.append({"head": head, "items": [s]})
    rank = {"T1": 3, "T2": 2, "T3": 1, "T4": 0}
    return [max(cl["items"], key=lambda x: rank.get(x["tier"], 0)) for cl in clusters]

def confidence(ind):
    tiers = {s["tier"] for s in ind}
    if "T1" in tiers:
        return "high"
    if sum(1 for s in ind if s["tier"] in ("T2", "T3")) >= 2:
        return "high"
    if "T2" in tiers or "T3" in tiers:
        return "mid"
    return "low"

lib_keys = {(e["category"], e["restaurant_id"], e.get("event_date")) for e in lib_events}
out_events = []
for key, e in agg.items():
    cat, rid, ev_date = e["category"], e["rid"], e["ev_date"]
    if rid is not None and (cat, rid, ev_date) in lib_keys:
        continue
    ind = independent(e["sources"])
    conf = confidence(ind)
    status = "verified" if conf == "high" else "rumor"
    default_days = CATS[cat].get("default_window_days")
    expires = parse_end(e["text"], ev_date, default_days) \
        if cat in ("popup", "collaboration", "guest_kitchen", "menu_update") else None
    # 限时活动若已过期 → 无 Feed 价值，丢弃（开业/关店/搬迁/荣誉等"已发生事实"保留）
    if cat in ("popup", "guest_kitchen", "collaboration", "menu_update") \
            and expires and expires < TODAY.isoformat():
        dropped.append(("(expired)", f"限时事件已过期 {expires}")); continue
    chef_id = None
    for cnm, cid in chef_by_name.items():
        if cnm and cnm in norm(e["text"]):
            chef_id = cid; break
    nm = strip_branch(rid_by_id[rid]["name"]) if rid else None
    out_events.append({
        "scope": e["scope"], "category": cat,
        "title": clean_title(e["title_raw"]) if rid is None else
                 (clean_title(e["title_raw"]) if nm and nm in e["title_raw"] else
                  {**{"new_open": f"{nm} 上海新开/首店", "relocated": f"{nm} 搬迁新址",
                      "closed": f"{nm} 闭店告别", "chef_changed": f"{nm} 主厨变动",
                      "guest_kitchen": f"{nm} 飞行客座晚宴", "collaboration": f"{nm} 跨界联名",
                      "popup": f"{nm} 限时快闪", "award": f"{nm} 荣誉发布",
                      "menu_update": f"{nm} 换季新菜单", "coming_soon": f"{nm} 即将开业"}}.get(cat, nm)),
        "summary": re.sub(r"#\S+", "", e["text"]).replace("\n", " ").strip()[:240],
        "event_date": ev_date, "restaurant_id": rid,
        "related_restaurant_id": e["related"], "chef_id": chef_id,
        "city": "上海", "district": e["district"],
        "sources": [{"platform": s["platform"], "author": s["author"],
                     "title": s["title"], "url": s["url"], "date": s["date"]} for s in e["sources"]],
        "confidence": conf, "status": status, "expires_on": expires})

C.write_jsonl(OUT_P, out_events)
C.write_jsonl(NEW_P, new_shops)
print("生成事件:", len(out_events), "| 未收录中文新店:", len(new_shops), "| 丢弃:", len(dropped))
print("category:", dict(Counter(x["category"] for x in out_events)))
print("confidence:", dict(Counter(x["confidence"] for x in out_events)),
      "| verified:", sum(1 for x in out_events if x["status"] == "verified"),
      "rumor:", sum(1 for x in out_events if x["status"] == "rumor"))
for u, why in dropped:
    print("  drop:", why, "|", u[:62])
for x in out_events:
    print("  EVENT[%s/%s] %s | rid=%s exp=%s" %
          (x["category"], x["confidence"], x["title"][:34], x["restaurant_id"], x["expires_on"]))
for ns in new_shops:
    print("  new-shop:", ns["title"][:30], "|", ns["url"][:55])
