#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final 2026 Black Pearl Shanghai full list with manual alignment resolutions."""
import json, pathlib

AUTH = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/authority")

# Final curated list with manual alignment
# matched_id resolved from DB lookup
three = [
    {"name": "遇外滩(新天地店)", "diamond": 3, "cuisine": "闽菜", "district": "黄浦区",
     "address": "黄浦区马当路245号新天地", "matched_id": 523,
     "source_url": "http://m.toutiao.com/group/7600207294030234112/"},
    {"name": "菁禧荟(外滩店)", "diamond": 3, "cuisine": "潮州菜", "district": "黄浦区",
     "address": "黄浦区中山东二路600号BFC外滩金融中心", "matched_id": 494,
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-3-diamond"},
    {"name": "甬府·北外滩", "diamond": 3, "cuisine": "宁波菜", "district": "虹口区",
     "address": "虹口区东大名路300号北外滩来福士东塔56层", "matched_id": 542,
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-3-diamond"},
]

two = [
    {"name": "福和慧", "diamond": 2, "cuisine": "素食", "district": "长宁区",
     "address": "长宁区愚园路1037号", "matched_id": 1383,
     "source_url": "https://www.enprimeurclub.com/restaurants/fu-he-hui-shanghai-restaurant"},
    {"name": "荣府宴(南阳路店)", "diamond": 2, "cuisine": "中餐/私房", "district": "静安区",
     "address": "静安区南阳路48号贝轩大公馆", "matched_id": 759,
     "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "中国菜·头灶", "diamond": 2, "cuisine": "中餐板前", "district": "静安区",
     "address": "静安区南京西路1376号上海商城", "matched_id": 719,
     "source_url": "http://m.toutiao.com/group/7600207294030234112/"},
    {"name": "8½ Otto e Mezzo BOMBANA(洛克外滩源店)", "diamond": 2, "cuisine": "意餐", "district": "黄浦区",
     "address": "黄浦区圆明园路169号洛克外滩源", "matched_id": 1175,
     "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "Ling Long(上海总会店)", "diamond": 2, "cuisine": "中餐创新", "district": "黄浦区",
     "address": "黄浦区中山东一路2号", "matched_id": 1391,
     "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "DA VITTORIO SHANGHAI(外滩店)", "diamond": 2, "cuisine": "意餐", "district": "黄浦区",
     "address": "黄浦区中山东一路6号", "matched_id": 1173,
     "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
]

one = [
    # 静安 11
    {"name": "Horita堀田", "diamond": 1, "cuisine": "日料", "district": "静安区", "matched_id": None,
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "IL RISTORANTE - NIKO ROMITO", "diamond": 1, "cuisine": "意餐", "district": "静安区",
     "address": "静安区宝格丽酒店", "matched_id": 1389,
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "MERCADO 505 Gourmet Restaurant", "diamond": 1, "cuisine": "西班牙/南美", "district": "静安区",
     "matched_id": 1196, "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "宝丽轩中餐厅", "diamond": 1, "cuisine": "粤菜", "district": "静安区",
     "address": "静安区宝格丽酒店", "matched_id": 1382,
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "斐霓丝 PHÉNIX(璞丽酒店)", "diamond": 1, "cuisine": "法餐", "district": "静安区",
     "matched_id": 1145, "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "福廬 FULL HOUSE", "diamond": 1, "cuisine": "淮扬/川扬", "district": "静安区",
     "matched_id": None, "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "家全七福酒家(丰盛商业中心店)", "diamond": 1, "cuisine": "粤菜", "district": "静安区",
     "matched_id": 1468, "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "楼上菜馆(静安嘉里中心店)", "diamond": 1, "cuisine": "中餐", "district": "静安区",
     "matched_id": None, "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "随堂里", "diamond": 1, "cuisine": "中餐", "district": "静安区",
     "address": "静安区石门一路366号镛舍2层", "matched_id": None,
     "source_url": "https://www.trip.com/moments/poi-sui-tang-li-56741907/"},
    {"name": "皖宴(苏河湾店)", "diamond": 1, "cuisine": "徽菜", "district": "静安区",
     "matched_id": 569, "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "醉东 Oriental House(静安嘉里店)", "diamond": 1, "cuisine": "台州菜", "district": "静安区",
     "matched_id": 1840, "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    # 徐汇 5
    {"name": "Le Comptoir de Pierre Gagnaire", "diamond": 1, "cuisine": "法餐", "district": "徐汇区",
     "address": "徐汇区建国西路480号建业里", "matched_id": 1143,
     "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "Stone Sal 言盐西餐厅(东湖路店)", "diamond": 1, "cuisine": "牛排/西餐", "district": "徐汇区",
     "address": "徐汇区东湖路9号", "matched_id": None,
     "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "The Pine 松涧", "diamond": 1, "cuisine": "西餐", "district": "徐汇区",
     "address": "徐汇区长乐路333号", "matched_id": None,
     "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "大董(环贸iapm店)", "diamond": 1, "cuisine": "中餐/鲁菜创新", "district": "徐汇区",
     "matched_id": 1562, "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "南兴园", "diamond": 1, "cuisine": "淮扬菜", "district": "徐汇区",
     "matched_id": 478, "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    # 浦东 5
    {"name": "Maison Lameloise 莱美露滋(上海中心店)", "diamond": 1, "cuisine": "法餐", "district": "浦东新区",
     "matched_id": 1141, "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "南麓荟馆(国金中心店)", "diamond": 1, "cuisine": "浙菜", "district": "浦东新区",
     "matched_id": 878, "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "悦轩(上海柏悦酒店)", "diamond": 1, "cuisine": "本帮菜", "district": "浦东新区",
     "matched_id": None, "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "徽季荣派徽菜", "diamond": 1, "cuisine": "徽菜", "district": "浦东新区",
     "matched_id": None, "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "凪 Nagi", "diamond": 1, "cuisine": "日料", "district": "浦东新区",
     "matched_id": None, "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    # 黄浦 (from enprimeurclub + Michelin overlap)
    {"name": "遇外滩(BFC外滩金融中心店)", "diamond": 1, "cuisine": "闽菜", "district": "黄浦区",
     "matched_id": 524, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Coquille 壳里", "diamond": 1, "cuisine": "法餐/海鲜", "district": "黄浦区",
     "address": "黄浦区", "matched_id": 1714, "source_url": "https://m.thepaper.cn/newsDetail_forward_32361879"},
    {"name": "Jean Georges", "diamond": 1, "cuisine": "法餐", "district": "黄浦区",
     "address": "黄浦区中山东一路3号外滩三号", "matched_id": 1137,
     "source_url": "https://threeonthebund.com/zh/restaurant/102008183386"},
    {"name": "老兴鲜(黄浦)", "diamond": 1, "cuisine": "本帮菜", "district": "黄浦区",
     "matched_id": None, "source_url": "https://joinpearl.co/restaurants/shanghai/lao-xing-xian-huangpu"},
    {"name": "鲁采LU STYLE(环宇荟店)", "diamond": 1, "cuisine": "鲁菜", "district": "黄浦区",
     "matched_id": 463, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Mr & Mrs Bund", "diamond": 1, "cuisine": "法餐", "district": "黄浦区",
     "address": "黄浦区中山东一路18号外滩18号6楼", "matched_id": None,
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "逸道(益丰·外滩源店)", "diamond": 1, "cuisine": "中餐", "district": "黄浦区",
     "matched_id": 508, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "皇朝会(外滩店)", "diamond": 1, "cuisine": "粤菜", "district": "黄浦区",
     "matched_id": 715, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "晟永兴(黄浦)", "diamond": 1, "cuisine": "烤鸭/京菜", "district": "黄浦区",
     "matched_id": None, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Vivant by Johnny Pham", "diamond": 1, "cuisine": "中法融合", "district": "黄浦区",
     "matched_id": 1841, "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "永·江臻", "diamond": 1, "cuisine": "江鲜/中餐", "district": "黄浦区",
     "address": "黄浦区思南路思南公馆", "matched_id": None,
     "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "御宝轩(益丰·外滩源店)", "diamond": 1, "cuisine": "粤菜", "district": "黄浦区",
     "matched_id": 495, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "逸龙阁", "diamond": 1, "cuisine": "粤菜", "district": "黄浦区",
     "matched_id": 716, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "壹零贰小馆", "diamond": 1, "cuisine": "湘菜", "district": "黄浦区",
     "matched_id": 718, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "新荣记(BFC外滩金融中心店)", "diamond": 1, "cuisine": "台州菜", "district": "黄浦区",
     "matched_id": 1370, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "美·大董(外滩BFC店)", "diamond": 1, "cuisine": "中餐/鲁菜创新", "district": "黄浦区",
     "matched_id": 1049, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "RIVIERA松鹤楼(外滩店)", "diamond": 1, "cuisine": "苏菜", "district": "黄浦区",
     "matched_id": 757, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "府·外滩华尔道夫", "diamond": 1, "cuisine": "中餐", "district": "黄浦区",
     "matched_id": 527, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    # 长宁
    {"name": "成隆行·怡丰园(虹桥店)", "diamond": 1, "cuisine": "蟹宴/江浙", "district": "长宁区",
     "matched_id": None, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond",
     "notes": "enprimeurclub标注HongQiao branch; DB有九江路店id=1385，虹桥分店可能为缺"},
    {"name": "福1015(愚园路店)", "diamond": 1, "cuisine": "本帮菜", "district": "长宁区",
     "matched_id": 1007, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "福1088", "diamond": 1, "cuisine": "本帮菜", "district": "长宁区",
     "matched_id": 1388, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Maggie 5 西郊5号", "diamond": 1, "cuisine": "中餐", "district": "长宁区",
     "matched_id": None, "source_url": "https://www.enprimeurclub.com/restaurants/maggie-5-shanghai"},
    {"name": "鹿园MOOSE(长宁店)", "diamond": 1, "cuisine": "本帮/江浙", "district": "长宁区",
     "matched_id": 540, "source_url": "https://joinpearl.co/restaurants/shanghai/moose"},
    {"name": "泰安门 Taian Table", "diamond": 1, "cuisine": "现代欧陆", "district": "长宁区",
     "matched_id": 1381, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    # 虹口
    {"name": "泓0871臻选云南菜", "diamond": 1, "cuisine": "云南菜", "district": "虹口区",
     "matched_id": 1615, "source_url": "https://nw.eastday.com/self/citynews/20260129/e8b75c01a9a948b68d20380680d2d1ec.html"},
    # 闵行
    {"name": "周舍海派菜", "diamond": 1, "cuisine": "本帮/海派", "district": "闵行区",
     "matched_id": None, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    # 其他/待确认
    {"name": "nabi", "diamond": 1, "cuisine": "韩食", "district": "长宁区",
     "matched_id": 1347, "source_url": "https://nw.eastday.com/self/citynews/20260129/e8b75c01a9a948b68d20380680d2d1ec.html",
     "notes": "DB标注长宁区; 2026新上榜韩食"},
    {"name": "1929 by Guillaume Galliot", "diamond": 1, "cuisine": "法餐", "district": "徐汇区",
     "matched_id": 1147, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "食庐NOBLE(港汇恒隆店)", "diamond": 1, "cuisine": "淮扬菜", "district": "徐汇区",
     "matched_id": 510, "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "VALE RESTAURANT", "diamond": 1, "cuisine": "西餐", "district": "浦东新区",
     "matched_id": None, "source_url": "https://www.enprimeurclub.com/restaurants/vale-restaurant-shanghai-restaurant"},
    {"name": "Sushi Aoki", "diamond": 1, "cuisine": "日料/寿司", "district": "待确认",
     "matched_id": None, "source_url": "https://joinpearl.co/restaurants/shanghai/sushi-aoki"},
]

ALL = three + two + one
matched = [r for r in ALL if r.get("matched_id")]
unmatched = [r for r in ALL if not r.get("matched_id")]
print(f"Total: {len(ALL)} (3d={len(three)}, 2d={len(two)}, 1d={len(one)})")
print(f"Matched in DB: {len(matched)}")
print(f"Truly missing: {len(unmatched)}")
print("\n--- Truly missing ---")
for r in unmatched:
    print(f"  [{r['diamond']}d] {r['name']} ({r.get('cuisine','')}) {r.get('district','')}")

output = {
    "edition": "2026黑珍珠餐厅指南",
    "city": "上海",
    "total": len(ALL),
    "three_diamond": three,
    "two_diamond": two,
    "one_diamond": one,
}
(AUTH / "blackpearl_shanghai_full.json").write_text(
    json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved blackpearl_shanghai_full.json")
