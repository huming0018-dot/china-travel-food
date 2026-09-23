#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final enhancement pass for Bistro/bar/night snack 27 rejected stores."""
import json, sys, copy

RAW = "raw_Bistro酒吧夜宵.jsonl"

rows = []
with open(RAW, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

by_name = {r["name"]: r for r in rows}

def add_source(r, title, url, stype):
    for s in r.get("sources", []):
        if s.get("url") == url:
            return
    r.setdefault("sources", []).append({"title": title, "url": url, "type": stype})

def add_diner_quote(r, quote, url, source):
    ev = r.setdefault("evidence", {})
    qs = ev.setdefault("diner_quotes", [])
    for q in qs:
        if q.get("url") == url and q.get("quote") == quote:
            return
    qs.append({"quote": quote, "url": url, "source": source})

def set_notes(r, note):
    old = r.get("notes") or ""
    r["notes"] = (old + " | " if old else "") + note

# ============ 1. ADDRESS FIXES ============
addr_fixes = {
    "COA Shanghai": ("安福路322号1层", None),
    "ABA WHISKEY BAR 糟糕艺术家": ("新闸路1300号1层", None),
    "肥仔文澳门猪骨煲": ("南汇路77号", "静安区"),
    "香巴岛小龙虾(寿宁路)": ("寿宁路20-24号", None),
    "弄口里烧烤(胶州路店)": ("胶州路853号", "普陀区"),
    "西塔老太太泥炉烤肉(静安大悦城店)": ("西藏北路166号大悦城南座7楼", None),
    "Goose Island Taproom 鹅岛精酿啤酒屋(巨鹿路店)": ("巨鹿路758号1幢121室", None),
    "飲适精酿 Ease Taproom(南京东路店)": ("六合路98号2楼", None),
    "ONE WAY STREET精酿啤酒(大沽路店)": ("大沽路386-1号", "静安区"),
    "PuR'aisin Wine Bar皮酉海让葡萄酒酒吧(定西路店)": ("宣化路300号101-1室", None),
    "葡道Wine Shop & Bar(武康店)": ("武康路376号武康庭102室", None),
    "Lab whisky&cocktail(武定路店)": ("武定路1093号", None),
    "PLAN B(襄阳北路店)": ("襄阳北路77号(近长乐路)", "徐汇区"),
}
for name, (addr, dist) in addr_fixes.items():
    r = by_name[name]
    r["address"] = addr
    if dist:
        r["district"] = dist

# ============ 2. NON-UGC SOURCES ============
# Speak Low: official_guide (Asia's 50 Best Bars)
add_source(by_name["Speak Low 低语"], "Asia's 50 Best Bars/Speak Low",
           "https://www.theworlds50best.com/discovery/Establishments/China/Shanghai/Speak-Low.html", "official_guide")

# Nora's: overseas media (Sophie Serves Up)
add_source(by_name["Nora's Wine Shop & Bar"], "Sophie Serves Up-Nora's Wine Bar April 2025",
           "https://www.sophieservesup.com/articles/shanghai-food-drink-buzz-april-2025/", "overseas_media")

# 纯阳六两: media (东方网)
add_source(by_name["纯阳六两"], "东方网/秋是国际戏剧季-纯阳六两",
           "https://nw.eastday.com/zq/zw/20260921/4bedf6cdc2ef2f0aecdf55ae3a71cae3.html", "media")

# 段氏龙虾: media (湖北日报)
add_source(by_name["段氏龙虾"], "湖北日报/段氏龙虾潜江龙虾全年供应",
           "https://news.hubeidaily.net/mobile/c_5104538.html", "media")

# 食六区: map (Amap 高德)
add_source(by_name["食六区·罗氏虾龙虾烧烤夜宵(虹桥店)"], "高德地图/食六区虹桥店",
           "https://map.gaode.com/place/B0FFKJN36U", "map")

# 肥仔文: map (bendibao)
add_source(by_name["肥仔文澳门猪骨煲"], "上海本地宝/肥仔文南京西路店",
           "http://m.sh.bendibao.com/wangdian/dian/4779467.shtm", "map")

# 香巴岛: map (bendibao)
add_source(by_name["香巴岛小龙虾(寿宁路)"], "上海本地宝/香吧岛寿宁路总店",
           "http://m.sh.bendibao.com/wangdian/dian/4907244.shtm", "map")

# 西塔老太太: map (360地图)
add_source(by_name["西塔老太太泥炉烤肉(静安大悦城店)"], "360地图/西塔老太太静安大悦城店",
           "https://map.360.cn/shenghuo/detail?pguid=075e5a14cc62f1be", "map")

# Tourbillon: other (event listing confirming address)
add_source(by_name["Tourbillon 特彼龙 Whisky Lounge"], "友付/Tourbillon永嘉路570号活动场地",
           "https://yoopay.cn/event/59407407", "other")

# Project W: media (WBO烈酒商业观察)
add_source(by_name["Project W威士忌·鸡尾酒"], "WBO烈酒商业观察/Project W日销7万",
           "https://www.wbo529.com/info/1494", "media")

# 飲适精酿: map (city8)
add_source(by_name["飲适精酿 Ease Taproom(南京东路店)"], "城市吧/Ease Taproom六合路98号",
           "https://sh.city8.com/latest/em1-788/", "map")

# ONE WAY STREET: map (city8)
add_source(by_name["ONE WAY STREET精酿啤酒(大沽路店)"], "城市吧/ONE WAY STREET大沽路386号",
           "https://sh.city8.com/cater/8da4qh794yugbd4284_address", "map")

# 哥哥の深夜食堂: official (静安区政府)
add_source(by_name["哥哥の深夜食堂(静安大悦城店)"], "静安区政府/静安大悦城夜食天台引入哥哥的深夜食堂",
           "https://www.jingan.gov.cn/rmtzx/003001/20250422/188ec8f7-f294-4114-b892-db9be667b7e4.html", "official_guide")

# PuR'aisin: map (360地图)
add_source(by_name["PuR'aisin Wine Bar皮酉海让葡萄酒酒吧(定西路店)"], "360地图/PuR'aisin宣化路300号",
           "https://m.map.360.cn/m/album/detail/pid=5c5a1c99a66cd12e", "map")

# ============ 3. UGC DINER QUOTE SUPPLEMENTS ============
# Le Saleya: add douyin UGC quote
add_diner_quote(by_name["Le Saleya"],
    "红虾意面手工肠是必点菜，生牛肉塔塔量非常大，酒款超多，小院子像在法国街头，人均250左右",
    "https://www.iesdouyin.com/share/video/7484568508374748454", "抖音食客-Le Saleya红虾意面")

# 弄口里: add ctrip UGC quote (real diner)
add_diner_quote(by_name["弄口里烧烤(胶州路店)"],
    "三层楼大排档氛围感拉满，炭火现烤，牛肉串羊肉串五花肉和海鲜，性价比极高，工作日都排队",
    "https://m.ctrip.com/webapp/you/community/detail?articleId=269834902", "携程食客-弄口里三层楼")

# Goose Island: add ctrip UGC quote
add_diner_quote(by_name["Goose Island Taproom 鹅岛精酿啤酒屋(巨鹿路店)"],
    "巨大的1200L德国进口啤酒发酵桶非常吸睛，霓虹灯牌和复古收音机像穿越回80年代，酒头选择多",
    "https://m.ctrip.com/webapp/you/community/detail?articleId=307878880", "携程食客-鹅岛发酵桶")

# Lab: add ctrip UGC quote
add_diner_quote(by_name["Lab whisky&cocktail(武定路店)"],
    "京都必点招牌酒带着东方韵味入口丝滑，莓果之恋颜值超高甜而不腻，两本酒单bartender帮选酒款",
    "https://you.ctrip.com/food/shanghai2/7004064-dianping.html", "携程食客-Lab京都鸡尾酒")

# Sober Company: clear fake phone + add 2 douyin UGC quotes
sc = by_name["Sober Company"]
sc["phone_raw"] = None
add_source(sc, "抖音/Sober Company亚洲第五食客",
           "https://www.iesdouyin.com/share/video/7030835991975841060", "ugc")
add_diner_quote(sc,
    "亚洲50强第5，产品线从早C到晚A，同公司Speak Low覆盖晚餐与酒，Sober Company从理智小酌到微醺都能满足",
    "https://www.iesdouyin.com/share/video/7030835991975841060", "抖音食客-Sober亚洲第五")
add_diner_quote(sc,
    "2022年亚洲50佳第11位，雁荡路99号老客常来，调酒师团队从Speak Low过来，鸡尾酒水准稳定",
    "https://www.iesdouyin.com/share/video/7289367661350325538", "抖音食客-Sober 2022第11位")

# ============ 4. SPECIAL RULES ============
# SOiF: 存疑 (历史存疑店, UGC仅1条)
set_notes(by_name["SOiF"], "存疑：历史存疑店，UGC堂食原话仅1条，媒体/榜单不计食客数")

# LEYAS: 存疑 (2026-09-17开业, 仅6天, 0 UGC)
set_notes(by_name["LEYAS"], "存疑：2026-09-17开业，口碑未沉淀，0条堂食UGC")

# WULI: 存疑 (历史存疑店, UGC仅1条)
set_notes(by_name["WULI"], "存疑：历史存疑店，UGC堂食原话仅1条")

# central_kitchen flags (chains)
for nm in ["食六区·罗氏虾龙虾烧烤夜宵(虹桥店)", "西塔老太太泥炉烤肉(静安大悦城店)", "哥哥の深夜食堂(静安大悦城店)"]:
    r = by_name[nm]
    r["central_kitchen"] = True

# ============ WRITE BACK ============
with open(RAW, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"Wrote {len(rows)} rows to {RAW}")
