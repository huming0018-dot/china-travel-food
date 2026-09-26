#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
migrate_legacy_scene.py — 旧场景标签 id48「咖啡/甜品专门店」、id49「酒吧/小酒馆」
迁移到新非正餐树（咖啡300/面包301/甜品302/Bar303 及三级），并删除旧标签关联。

铁律：主业态以【店名】为准，不用招牌菜（咖啡馆招牌菜普遍含蛋糕/面包会误判）；
店名无业态词的店一律在 OVERRIDE 显式指定（确定性、可审计），未覆盖则报 AMBIGUOUS。
默认 dry-run；--commit 才写。
"""
import argparse
import time

import common as C

OVERRIDE = {
    # —— 咖啡（300；304创意/305手冲自烘/306社区/307连锁）——
    "铁手咖啡制造局Metal Hands(永嘉路店)": [300, 305],
    "Metal Hands 铁手咖啡制造局": [300, 305],
    "1/10 Coffee Roaster(长乐路店)": [300, 305],
    "有容乃大 Bigger Than Bigger(北京西路店)": [300, 305],
    "有容乃大 LuckyDraw": [300, 305],
    "Radar雷达咖啡(思南路店)": [300, 305],
    "Radar Coffee": [300, 305],
    "煮屿 Brew Island(溧阳路店)": [300, 305],
    "Brew Island 煮屿": [300, 305],
    "Café del Volcán火山咖啡(永康路店)": [300, 305],
    "Café del Volcán": [300, 305],
    "鲁马滋 Rumors Coffee Roastery": [300, 305],
    "白鲸咖啡 White Whale": [300, 305],
    "Blacksheep Espresso(茂名南路店)": [300, 305],
    "VOYAGE COFFEE": [300, 305],
    "赤瑕咖啡Akadama Coffee(武定西路店)": [300, 305],
    "赤瑕咖啡 Akadama": [300, 305],
    "DEARYOU 咖啡豆研究所": [300, 305],
    "New Lane Coffee 纽巷": [300, 305],
    "0566咖啡製作所": [300, 305],
    "堀口咖啡HORIGUCHI COFFEE(洛克·外滩源店)": [300, 305],
    "O.P.S. CAFE(太原路店)": [300, 304],
    "O.P.S CAFE": [300, 304],
    "Captain George风味博物馆(太原路店)": [300, 304],
    "DayDreaming by Monos 白日梦": [300, 304],
    "Gregorius航迹(愚园路店)": [300, 304],
    "Gregorius SHADE(安福路店)": [300, 304],
    "月球咖啡 Retro": [300, 306],
    "aftertaste 回味": [300, 306],
    "小半咖啡": [300, 306],
    "pocket pocket 口袋咖啡": [300, 306],
    "HUGO HUSKY HOUSE 雨果咖啡": [300, 306],
    "IKIGAI": [300, 306],
    "城是 CITYBORING": [300, 306],
    "LANERS老虎灶喫咖啡": [300, 306],
    "MONO": [300, 306],
    "Rain Mountain 雨山咖啡": [300, 306],
    "且乐 cheer": [300, 306],
    "3又二分之一": [300, 306],
    "马里昂巴Marienbad(武康路店)": [300, 306],
    "老麦咖啡馆TheCottageBar(武康大楼店)": [300, 306],
    "一木家 Café Chez W": [300, 306],
    "SMAKA咖啡烘焙": [300, 306],
    "HUFFY coffee&gelato(威海路店)": [300, 306],
    "BIG SUR COFFEE": [300, 306],
    "Manner Coffee": [300, 307],
    "Seesaw Coffee": [300, 307],
    "星巴克臻选上海烘焙工坊": [300, 307],
    # —— 面包（301；308起酥/309日式/310社区/311贝果/312酸种）——
    "PAIN CHAUD百丘(建国西路店)": [301, 308],
    "PAIN CHAUD百丘(番禺路店)": [301, 308],
    "gluglu面包店(思南路店)": [301, 308],
    "Gluglu(愚园路店)": [301, 308],
    "LUNEURS月乐诗冰淇淋咖啡(北外滩来福士店)": [301, 308],
    "Luneurs月乐诗(南京西路店)": [301, 308],
    "VERIE BAKEHOUSE(马当路店)": [301, 308],
    "FASCINO BAKERY(新天地店)": [301, 308],
    "FASCINO BAKERY(丰盛里店)": [301, 308],
    "BAsdBAN巴适得板(愚园路店)": [301, 308],
    "BAsdBAN（愚园路店）": [301, 308],
    "TonTon(永康路店)": [301, 308],
    "Bebaked(愚园路店)": [301, 308],
    "drunk baker醉师傅(陕康里店)": [301, 308],
    "Bake No Title(番禺路店)": [301, 308],
    "乔尔卢布松美食坊Boulangerie(外滩18号)": [301, 308],
    "翠贝果(乌鲁木齐南路店)": [301, 311],
    "Big Bagel(永康路店)": [301, 311],
    "纽约贝果博物馆(新天地店)": [301, 311],
    "Sumerian(陕西北路店)": [301, 312],
    "O'Mills Sourdough Bakery & Bistro(永嘉路店)": [301, 312],
    "When Pigs Fly当猪飞(愚园路店)": [301, 312],
    "SMAKA（愚园路店）": [301, 310],
    "SunFlour阳光粮品(安福路店)": [301, 310],
    "Baker & Spice（安福路店）": [301, 310],
    "国际饭店帆声饼屋(黄河路店)": [301, 310],
    "Le Pain Sense(建国东路店)": [301, 310],
    # —— 甜品（302；313 Gelato/314刨冰/315松饼/316糖水/317蛋糕/318铜锣烧抹茶）——
    "Kaki Mania日式刨冰": [302, 314],
    "LENOTRE雷诺特法式西点(前滩太古里店)": [302, 317],
    "Le Gateau戛朵法式蛋糕(世博源店)": [302, 317],
    "PAUL LAFAYET法式甜品(港汇广场店)": [302, 317],
    "制冰铺MakingGelato·时桉(陕西南路店)": [302, 313],
    "BONUS Gelato(乌鲁木齐中路店)": [302, 313],
    "Spiceman辣男Gelato(思南路店)": [302, 313],
    "麻布屋AZABUYA(永康路店)": [302, 313],
    "MIMILATO(长乐路店)": [302, 313],
    "Sit Gelato(南昌路店)": [302, 313],
    "达可芮Gelato Dal Cuore(陕西北路店)": [302, 313],
    "贵州冰浆(陕西北路店)": [302, 314],
    "香港华心糖水铺(南西总店)": [302, 316],
    "双喜老铺(静安寺店)": [302, 316],
    "小团圆糖水铺(思南路店)": [302, 316],
    "堂屋糖水铺(愚园路店)": [302, 316],
    "辛一铜锣烧(静安大悦城店)": [302, 318],
    "Matcha Love 抹艾茶": [302, 318],
    "西园抹茶专卖店（大悦城店）": [302, 318],
    "Sloppy Gin(延平路店)": [302, 317],
    "柴田西点Chez Shibata(紫云西路店)": [302, 317],
    "yesOcake巴斯克专门店": [302, 317],
    "L'eclair de Genie闪电巴黎(芮欧百货店)": [302, 317],
    "法田鹿蛋糕": [302, 317],
    "Lady M(上海恒隆广场店)": [302, 317],
    "聚福shanghailander(乌鲁木齐南路店)": [302, 317],
    "EVERNAKED裸蛋糕(巨鹿路店)": [302, 317],
    "yeetlemon柠檬蛋糕(同乐坊店)": [302, 317],
    "FINE pancake&canteen(陕西南路店)": [302, 315],
    # —— 下午茶77 / 茶馆82 ——
    "新天地朗廷酒店大堂吧": [77], "海仑宾馆505Bar": [77],
    "外滩华尔道夫酒店羿庭": [77], "和平饭店华懋阁": [77],
    "上海半岛酒店 The Lobby 大堂茶座": [77],
    "上海浦东丽思卡尔顿酒店 AURA酒廊": [77],
    "上海柏悦酒店 大堂客厅": [77],
    "上海璞丽酒店 LONG BAR长吧": [77],
    "裕莲茶楼（金虹桥国际中心店）": [82], "湖心亭茶楼": [82],
    # —— Bar（303；319威士忌/320精酿/321葡萄酒/322鸡尾酒）——
    "Kartel Wine Bar": [303, 321], "Justgrapes萄醉(安福路店)": [303, 321],
    "Vinism Wine Bar": [303, 321], "Vinism": [303, 321],
    "SOiF": [303, 321], "Mavis966": [303, 321],
    "Nora's Wine Shop & Bar": [303, 321],
    "DTE down to earth": [303, 321],
    "Le Saleya Bar à Vin": [303, 321],
    "La Tavernetta Bar à Vin": [303, 321],
    "Pecher Wine Bar": [303, 321],
    "Wine Universe": [303, 321], "Le Verre à vin": [303, 321],
    "PuR'aisin Wine Bar皮酉海让葡萄酒酒吧(定西路店)": [303, 321],
    "葡道Wine Shop & Bar(武康店)": [303, 321],
    "HEALER Bar": [303, 322], "SHIMMER(巨鹿路店)": [303, 322],
    "JZ CLUB": [303, 322], "Speak Low彼楼": [303, 322],
    "Speak Low 低语": [303, 322], "Sober Company": [303, 322],
    "Pony Up": [303, 322], "COA Shanghai": [303, 322],
    "武宫酒吧": [303, 322], "Bar Leone": [303, 322],
    "SOSA": [303, 322], "PLAN B(襄阳北路店)": [303, 322],
    "明日酿造/明日酒馆": [303, 320],
    "Goose Island Taproom 鹅岛精酿啤酒屋(巨鹿路店)": [303, 320],
    "飲适精酿 Ease Taproom(南京东路店)": [303, 320],
    "ONE WAY STREET精酿啤酒(大沽路店)": [303, 320],
    "ABA WHISKEY BAR 糟糕艺术家": [303, 319],
    "Tourbillon 特彼龙 Whisky Lounge": [303, 319],
    "Project W威士忌·鸡尾酒": [303, 319],
    "Lab whisky&cocktail(武定路店)": [303, 319],
    # —— 餐酒馆归形式 Bistro 73 ——
    "法国舅舅家小酒馆CHEZ JOJO(永嘉路店)": [73],
    "Sip bistro&bar": [73], "龍满·云贵川bistro小酒馆": [73],
    "Forage Eatery & Wine Bar": [73], "gula bistro": [73],
    "壮壮酒馆 Terroir Strong": [73],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    rests = {r["id"]: r for r in C.fetch_all("restaurants", "id,name")}
    jobs, ambiguous = [], []
    for legacy in (48, 49):
        rows = C.req("GET", f"/restaurant_cuisines?cuisine_id=eq.{legacy}"
                            "&select=restaurant_id").json()
        for x in rows:
            rid = x["restaurant_id"]
            name = rests[rid]["name"]
            if name in OVERRIDE:
                jobs.append((legacy, rid, name, OVERRIDE[name]))
            else:
                ambiguous.append((legacy, rid, name))

    for legacy, rid, name, tags in jobs:
        print(f"[{legacy}] {rid} {name} -> {tags}")
    for legacy, rid, name in ambiguous:
        print(f"[AMBIGUOUS {legacy}] {rid} {name}")

    if ambiguous:
        print(f"\n{len(ambiguous)} 家未覆盖，请补 OVERRIDE 后重跑。")
        return
    if not args.commit:
        print(f"\n【DRY-RUN】共 {len(jobs)} 家。确认后加 --commit。")
        return

    for legacy, rid, name, tags in jobs:
        have = {x["cuisine_id"] for x in
                C.req("GET", f"/restaurant_cuisines?restaurant_id=eq.{rid}"
                             "&select=cuisine_id").json()}
        for t in tags:
            if t not in have:
                C.req("POST", "/restaurant_cuisines",
                      json={"restaurant_id": rid, "cuisine_id": t})
                time.sleep(0.04)
        C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{rid}"
                        f"&cuisine_id=eq.{legacy}")
    print(f"迁移完成 {len(jobs)} 家；旧标签 48/49 关联已删除。")


if __name__ == "__main__":
    main()
