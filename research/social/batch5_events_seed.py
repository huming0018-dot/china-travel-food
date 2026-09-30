#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次5 首页动态数据层：有界真实抓取结果落库（dry-run 默认，COMMIT=1 才写）。
每条带 source_url / event_date(start) / expires_on(end) / registration_* / tags / category。
海外字段 origin_market/is_overseas_brand live 库尚无此列，本脚本不写，由 022 SQL 回填。"""
import sys, os, json, hashlib, time
sys.path.insert(0, '/app/pipeline')
import common as C
import requests

COMMIT = os.environ.get('COMMIT') == '1'

EVENTS = [
  {
    "scope": "industry", "category": "announcement", "event_subtype": "通告",
    "title": "《一饭封神》第二季腾讯视频热播中",
    "summary": "腾讯视频美食竞技综艺《一饭封神》第二季，2026-07-29 起每周三、周四 12:00 更新，百位厨者同台竞技；试吃官以受邀为主，普通观众可关注官方话题。",
    "event_date": "2026-07-29", "expires_on": None,
    "city": None, "district": None, "restaurant_id": None,
    "sources": [
      {"url": "https://m.weibo.cn/detail/5323063008952574", "kind": "official", "label": "微博综艺官方（播出日历/预约）"},
      {"url": "https://www.iesdouyin.com/share/video/7665550763238316954", "kind": "official", "label": "一饭封神2官方抖音（阵容官宣）"},
    ],
    "confidence": "high", "status": "verified",
    "registration_info": "腾讯视频每周三/周四12:00更新；无公开报名入口，观众可看节目正片",
    "tags": ["综艺", "美食竞技", "腾讯视频"],
  },
  {
    "scope": "local", "category": "collaboration", "event_subtype": "跨界联名",
    "title": "Café Kitsuné x Toris「蓝色游牧」限定甜点菜单",
    "summary": "Café Kitsuné 携手 Toris（静安区铜仁路72号）推出「蓝色游牧」系列限定甜点菜单，法式工艺融汇双城风味。",
    "event_date": "2026-10-01", "expires_on": "2026-10-14",
    "city": "上海", "district": "静安区", "restaurant_id": None,
    "sources": [
      {"url": "https://m.weibo.cn/detail/5348545163952893", "kind": "official", "label": "Maison Kitsuné 官方微博（9-29发布）"},
    ],
    "confidence": "high", "status": "verified",
    "registration_info": "现场堂食，无单独预约链接",
    "tags": ["联名", "甜点", "咖啡", "铜仁路"],
  },
  {
    "scope": "local", "category": "popup", "event_subtype": "联合快闪",
    "title": "Breville铂富「Café & Store」上海限时慢闪",
    "summary": "澳大利亚厨电品牌 Breville 借 Oracle Jet 新机发布，于铜仁路88号打造限时慢闪空间：一楼限定特调+新机手作，二楼品牌展；世界拉花冠军梁凡任一日店长，冠军咖啡师谭茜莹带来大师课。",
    "event_date": "2026-09-21", "expires_on": "2026-10-15",
    "city": "上海", "district": "静安区", "restaurant_id": None,
    "sources": [
      {"url": "https://www.jiemian.com/article/15116005.html", "kind": "media", "label": "界面新闻·美食情报（9-24）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": "现场入场；大师课/一日店长征询见品牌官方渠道",
    "tags": ["咖啡", "慢闪", "厨电", "铜仁路"],
  },
  {
    "scope": "local", "category": "popup", "event_subtype": "联合快闪",
    "title": "POP BAKERY「复古理发店」× THE MONSTERS 登陆东方滨江大酒店",
    "summary": "东方明珠旗下上海国际会议中心东方滨江大酒店携手 POP BAKERY，将 THE MONSTERS 复古理发店主题限时搬入酒店一楼江畔空间。",
    "event_date": "2026-09-01", "expires_on": "2026-11-30",
    "city": "上海", "district": "浦东新区", "restaurant_id": None,
    "sources": [
      {"url": "http://wapp.zhoudaosh.com/mobile/#/detail/DAB888CDB6E222A113E6010AAE5C23244EED4735E4635BD268C52BBED461129F", "kind": "media", "label": "新闻晨报·周到（来源：东方明珠发布）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": "上海国际会议中心东方滨江大酒店官方微信渠道购票",
    "tags": ["烘焙", "IP联名", "陆家嘴", "主题快闪"],
  },
  {
    "scope": "local", "category": "new_open", "event_subtype": "新店开业",
    "title": "Atelier玖樓（粤菜）与 Opia 酒吧同层开业（A Mansion 9F）",
    "summary": "Atelier Group 在复兴路 A Mansion 9 层同层开出传统粤菜玖樓（炭烤蟹配 paccheri 等）与下沉式鸡尾酒吧 Opia（Matthew Hall 主理）；长乐路侧办公电梯上 9F。具体开业日未披露，以 9 月开业报道日近似。",
    "event_date": "2026-09-18", "expires_on": None,
    "city": "上海", "district": "静安区", "restaurant_id": None,
    "sources": [
      {"url": "https://etather.com/en/news/shanghai-september-2026-restaurant-openings", "kind": "ugc", "label": "ÉTAT HER 上海9月开业盘点（9-18）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": None,
    "tags": ["粤菜", "酒吧", "长乐路", "集团新店"],
  },
  {
    "scope": "local", "category": "new_open", "event_subtype": "新店开业",
    "title": "Leyas 蕾娅中东美食新天地开业",
    "summary": "黎巴嫩 Eli Falafel 创始人 Wael Accad 主理的精致现代中东餐厅，三层空间、全包间、全酒吧与两个水烟露台，入驻新天地广场。",
    "event_date": "2026-09-18", "expires_on": None,
    "city": "上海", "district": "黄浦区", "restaurant_id": 1251,
    "sources": [
      {"url": "https://etather.com/en/news/shanghai-september-2026-restaurant-openings", "kind": "ugc", "label": "ÉTAT HER 上海9月开业盘点（9-18）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": None,
    "tags": ["中东菜", "新天地"],
  },
  {
    "scope": "local", "category": "new_open", "event_subtype": "新店开业",
    "title": "KIRILLITSA 西里尔俄罗斯餐厅入驻 Bund City Hall",
    "summary": "汉口路201号5楼 Bund City Hall，主厨 Evgeny Vikentiev 以欧洲训练背景做现代俄罗斯菜，命名致敬西里尔字母。",
    "event_date": "2026-09-29", "expires_on": None,
    "city": "上海", "district": "黄浦区", "restaurant_id": 1210,
    "sources": [
      {"url": "https://www.smartshanghai.com/listings/dining/recently_opened/", "kind": "ugc", "label": "SmartShanghai Recently Opened（9-29更新）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": None,
    "tags": ["俄罗斯菜", "BundCityHall", "汉口路"],
  },
  {
    "scope": "local", "category": "new_open", "event_subtype": "主厨新店",
    "title": "Accents 开业：前东京 Narisawa 主厨 Joey 掌舵永福路新店",
    "summary": "主厨 Joey 曾任职东京 Narisawa，在永福路开设 Accents，融合法餐、本帮与日料的“上海+”风格。",
    "event_date": "2026-09-18", "expires_on": None,
    "city": "上海", "district": "徐汇区", "restaurant_id": None,
    "sources": [
      {"url": "https://etather.com/en/news/shanghai-september-2026-restaurant-openings", "kind": "ugc", "label": "ÉTAT HER 上海9月开业盘点（9-18）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": None,
    "tags": ["主厨新店", "融合菜", "永福路"],
  },
  {
    "scope": "local", "category": "coming_soon", "event_subtype": "海外热门入沪",
    "title": "曼谷 Tribe Sky Beach Club 中国首店落位恒隆广场屋顶（预计2026 Q4末）",
    "summary": "曼谷都市海滩品牌 Tribe 首次进入中国、首次出海，落位上海恒隆广场主楼6F屋顶花园：无边际天际泳池、艺术装置、完整灯光音响。具体开业日待官方公布。",
    "event_date": None, "expires_on": None,
    "city": "上海", "district": "静安区", "restaurant_id": None,
    "sources": [
      {"url": "https://etather.com/en/news/shanghai-september-2026-restaurant-openings", "kind": "ugc", "label": "ÉTAT HER 上海9月开业盘点（9-18）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": "未开放，待官方公布",
    "tags": ["泰国", "屋顶酒吧", "首店", "恒隆广场", "海滩俱乐部"],
  },
  {
    "scope": "local", "category": "new_open", "event_subtype": "重新开业",
    "title": "红房子西菜馆焕新回归试营业",
    "summary": "1935 年创立的海派西餐老字号红房子西菜馆悄然开启试营业，全场八折；后厨与服务团队引入米其林、黑珍珠履历班底。具体分店地址待补。",
    "event_date": "2026-09-30", "expires_on": None,
    "city": "上海", "district": None, "restaurant_id": None,
    "sources": [
      {"url": "http://m.toutiao.com/group/7691227554723807790/", "kind": "media", "label": "上观新闻（头条号，9-30）"},
    ],
    "confidence": "mid", "status": "rumor",
    "registration_info": "试营业全场8折；分店地址待补",
    "tags": ["海派西餐", "老字号", "重新开业"],
  },
]

def fp(row):
    raw = f"{row['category']}|{C.cjk_norm(row['title'])}|{row.get('event_date') or ''}"
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:32]

# 已有事件按 fingerprint / title 去重
existing = C.fetch_all('food_events', 'id,title,dedup_fingerprint', page=1000)
have_fp = {e.get('dedup_fingerprint') for e in existing if e.get('dedup_fingerprint')}
have_title = {C.cjk_norm(e['title']) for e in existing}

todo, skipped = [], []
for ev in EVENTS:
    f = fp(ev)
    ev['dedup_fingerprint'] = f
    if f in have_fp or C.cjk_norm(ev['title']) in have_title:
        skipped.append(ev['title'])
        continue
    todo.append(ev)

print(f"=== {'COMMIT 写库' if COMMIT else 'DRY-RUN 预演'} ===")
print(f"已有事件 {len(existing)} 条；本批候选 {len(EVENTS)} 条；跳过重复 {len(skipped)}；待写 {len(todo)}")
for s in skipped:
    print("  SKIP:", s)
for i, ev in enumerate(todo, 1):
    print(f"[{i}/{len(todo)}] {ev['category']}/{ev['event_subtype']} | {ev['event_date']} → {ev['expires_on']} | {ev['title']}")
    print(f"     tags={ev['tags']} conf={ev['confidence']} status={ev['status']} rid={ev['restaurant_id']}")
    print(f"     src={ev['sources'][0]['url']}")

if not COMMIT:
    print("\nDRY-RUN 结束，未写库。COMMIT=1 重跑写入。")
    sys.exit(0)

# COMMIT：逐行 POST 并回读（直接用 requests，自带 Prefer: return=representation）
written = []
for ev in todo:
    body = dict(ev)
    hdr = {**C.headers(), 'Prefer': 'return=representation'}
    r = requests.post(C.BASE + '/food_events', headers=hdr, json=body, timeout=45)
    if r.status_code not in (200, 201):
        print("!! 写失败:", r.status_code, r.text[:500], "| title:", ev['title'])
        sys.exit(1)
    back = r.json()[0]
    written.append(back)
    print(f"  已写 id={back['id']} {back['category']}/{back['event_subtype']} {back['title']}")

# 写后回读：按 id 再拉一次确认
print("\n=== 写后回读 ===")
for back in written:
    r = C.req('GET', f"/food_events?select=id,category,event_subtype,title,event_date,expires_on,tags,status,confidence&id=eq.{back['id']}", use_service=True)
    row = r.json()[0]
    print(f"  id={row['id']} | {row['category']}/{row['event_subtype']} | {row['event_date']}~{row['expires_on']} | {row['status']}/{row['confidence']} | {row['title']}")
print(f"\nDONE 写入 {len(written)} 条。")
