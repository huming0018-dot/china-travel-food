#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按店名原位补强被打回店的 diner_quotes / sources，再回写 raw。不新建、不删除其他记录。"""
import json, pathlib

DIR = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/continents")

def load(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
def save(p, rows):
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

# ---------- Tacolicious (NA)：2 条 trip.com 食客 UGC ----------
def patch_tacolicious(r):
    r["evidence"]["diner_quotes"] = [
        {"quote": "這家墨西哥餐廳的Taco做得非常正宗，特別是烤牛排口味的，肉質鮮嫩又多汁，配上酥脆的玉米餅和酸爽的泡菜，吃起來口感特別豐富。",
         "dish": "烤牛排Taco", "source": "Trip.com", "url": "https://hk.trip.com/travel-guide/foods/shanghai-2-restaurant/city-121696346", "date": "2026-07-30"},
        {"quote": "套餐性價比超高，分量也特別足。尤其是玉米片配的牛油果醬和辣番茄莎莎，味道很獨特，值得一試；餐廳環境充滿墨西哥特色。",
         "dish": "玉米片+牛油果醬/辣番茄莎莎", "source": "Trip.com", "url": "https://hk.trip.com/travel-guide/foods/shanghai-2-restaurant/city-121696346", "date": "2026-07-30"},
    ]
    r["sources"] = [
        {"title": "Trip.com - Tacolicious(余姚路店)食评", "url": "https://hk.trip.com/travel-guide/foods/shanghai-2-restaurant/city-121696346", "type": "ugc"},
        {"title": "SmartShanghai - Tacolicious 商户页", "url": "https://www.smartshanghai.com/venue/19163/tacolicious_yuyao_lu", "type": "media"},
        {"title": "澎湃/今日头条 - 同乐坊Taco脆壳现场", "url": "http://m.toutiao.com/group/7643988795297219113/", "type": "media"},
    ]
    r["evidence_summary"] = (
        "Tacolicious 位于静安余姚路34号同乐坊，联合创始人是资深调酒师 Logan Brouse。招牌是独创『双层taco』——"
        "酥脆玉米硬壳外包一层软面粉饼、中间夹融芝士；馅料从 asados、al pastor 到韩式牛肉、川味回锅肉都有，"
        "Taco 两个65元。Trip.com 食客反复点名烤牛排taco肉质鲜嫩多汁、配脆玉米饼与酸爽泡菜；玉米片配牛油果醬与"
        "辣番茄莎莎性价比高。负面：创意墨西哥、酒吧与Taco Tuesday属性强，非纯地道。由『上海 taco』在 Trip/SmartShanghai 发现。")
    return r

# ---------- El Bodegon (SA)：补第2条抖音UGC（脆皮牛排）----------
def patch_el_bodegon(r):
    r["evidence"]["diner_quotes"] = [
        {"quote": "这家店开了12年，很多人一说阿根廷菜就想到烤肉，但真正让我觉得在别家吃不到的是这家的脆皮牛排：牛里脊敲扁，裹面包糠炸成酥脆底子，再像做披萨一样铺番茄酱、火腿、芝士，烤到芝士融化拉丝，一口下去既是牛排又是披萨。",
         "dish": "脆皮牛排(neapolitan steak)", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7661250961343701583", "date": "2026-07-11"},
        {"quote": "在上海常熟路上就能品尝到正宗阿根廷牛肉啦，店开了很久、价格亲民、生意好到不行；Bodegon是食物之意，乘电梯上4楼迎面就是小门面，阿根廷畜牧业发达、自然放养所以肉质鲜嫩。",
         "dish": "阿根廷草饲牛排", "source": "穷游", "url": "https://biu.qyer.com/p/XGWrP2GaXECH1wIcW1Ir-w.html", "date": "2026-09-18"},
    ]
    r["sources"] = [
        {"title": "抖音 - 上海4家小众外国菜(El Bodegon脆皮牛排)", "url": "https://www.iesdouyin.com/share/video/7661250961343701583", "type": "ugc"},
        {"title": "穷游 - 常熟路正宗阿根廷秘鲁风味牛肉", "url": "https://biu.qyer.com/p/XGWrP2GaXECH1wIcW1Ir-w.html", "type": "ugc"},
        {"title": "DiningCity - El Bodegon 鼎食聚(empanada)", "url": "https://www.diningcity.cn/zh/shanghai/el_bodegon", "type": "media"},
        {"title": "SmartShanghai - El Bodegon(Panyu Lu)", "url": "https://www.smartshanghai.com/venue/16121/el_bodegon_panyu_lu", "type": "media"},
    ]
    return r

# ---------- Delight Food (EU)：哔哩哔哩 + trip 双UGC，bendibao map ----------
def patch_delight(r):
    r["evidence"]["diner_quotes"] = [
        {"quote": "Delight Food-Belgian Brasserie 老外街27号，点了比利时风味青口贝168元、荷兰特色香肠小吃48元、比利时薯条；比利时的薯条是全世界最好吃的薯条吧（个人封的）。",
         "dish": "青口贝/比利时薯条", "source": "哔哩哔哩", "url": "https://m.bilibili.com/opus/539400218242852001", "date": "2026-05-27"},
        {"quote": "這家餐廳當地口碑還是不錯的，是上海為數不多的比利時餐廳中的佼佼者，青口、牛排和炸薯條不錯的，推薦餐廳的啤酒；各色比利時啤酒，薯條正宗。",
         "dish": "青口/牛排/炸薯条", "source": "Trip.com", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/delight-food-belgian-brasserie-bilishi-restaurant-11153091/", "date": "2021-02-26"},
    ]
    r["sources"] = [
        {"title": "哔哩哔哩 - 老外街400米吃遍全球(Delight Food)", "url": "https://m.bilibili.com/opus/539400218242852001", "type": "ugc"},
        {"title": "Trip.com - Delight Food 比利时啤酒餐厅食评", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/delight-food-belgian-brasserie-bilishi-restaurant-11153091/", "type": "ugc"},
        {"title": "上海本地宝 - Delight Food比利时餐厅(老外街27号)", "url": "http://m.sh.bendibao.com/wangdian/dian/4831298.shtm", "type": "map"},
    ]
    return r

# ---------- 阿萨 (Asia)：补强第2条携程UGC（来源仍待补非UGC类）----------
def patch_asa(r):
    r["evidence"]["diner_quotes"] = [
        {"quote": "荟聚这家宝藏中东料理我能刷100次！一进门直接穿越到波斯市集；摩洛哥牛肋排塔吉锅慢炖到脱骨，裹着醇厚的香料酱汁，连胡萝卜都吸满了肉香，配阿拉伯馕蘸酱吃。",
         "dish": "牛肋排塔吉锅", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=224340418", "date": "2025-11-07"},
        {"quote": "真的是一家无论是环境还是味道都让人恍惚在迪拜的店：中东传统三酱先上桌，鹰嘴豆泥口感绵密，烟熏甜椒酱带着微微焦香，酸奶茄子酱酸得开胃；现烤的皮塔饼热乎乎。",
         "dish": "鹰嘴豆泥/三酱/皮塔饼", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=328436256", "date": "2026-06-28"},
    ]
    # 增加 trip 商户页(ugc) + 抖音(ugc)；来源类型仍需补1个 media/map，留待真人高德拾取
    r["sources"] = [
        {"title": "携程 - 阿萨中东料理荟聚店(波斯市集)", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=224340418", "type": "ugc"},
        {"title": "携程 - 阿萨中东料理(三酱/鹰嘴豆泥)", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=328436256", "type": "ugc"},
        {"title": "抖音 - 阿萨骆驼排罐罐开罐仪式", "url": "https://www.iesdouyin.com/share/video/7601056794224041125", "type": "ugc"},
    ]
    return r

# ---------- 新增：纹兵卫手打荞麦面(天山店) ----------
def monbei():
    return {
        "name": "纹兵卫手打荞麦面日料(天山店)",
        "name_en": "Soba Monbei",
        "district": "长宁区",
        "address": "天山路765号(近古北路,荣华东道57号里昂花园为古北本店)",
        "business_area": "古北/天山",
        "price_avg": 90, "price_range": "¥80-120",
        "cuisine_paths": [["亚洲", "日本", "荞麦·冷荞麦/山药泥"], ["亚洲", "日本", "荞麦·天妇罗盛荞麦"]],
        "form": "Casual Dining", "scene": "正餐",
        "ingredients": ["面"],
        "signature_dishes": ["天妇罗冷荞麦面", "招牌冷荞麦面配山药泥", "秋葵纳豆山药泥冷荞麦", "小银鱼干梅肉荞麦面"],
        "phone_raw": None, "booking_method": "大众点评/到店",
        "brand_group": "纹兵卫(2007年入沪,多分店)", "brand_confirmed": True,
        "scores": {"objective": 76, "diner": 78, "taste": 78, "endorsement": 60,
                   "soft_ad_penalty": 0, "platform_credibility": 0.85},
        "evidence_summary": (
            "纹兵卫 Soba Monbei 是2007年入沪的老牌手打荞麦专门店，天山店位于长宁天山路765号，古北本店在荣华东道57号"
            "里昂花园，另在辛耕路125号(徐家汇)、金虹桥、新天地有分店。坚持手工制面，冷荞麦配浓蘸汁(蘸而非泡)。"
            "携程食客反复点天妇罗冷荞麦面：原味或蘸汁加芥末、剩下的蘸汁倒荞麦汤『原汤化原食』；招牌冷荞麦配山药泥"
            "是首次见到的吃法、面筋道爽滑蘸微甜山药泥；另有秋葵纳豆山药泥冷荞麦、烤青花鱼、荞麦布丁。澎湃称其开了17年、"
            "上海凉面界老牌、招牌小银鱼干梅肉荞麦面。负面：客单逐年上涨、夏天排队、连锁多分店品质参差。"
            "由『上海 荞麦面 仙霞路/古北』在携程/澎湃/抖音发现。（按附录A：荞麦独立成二级，不并入拉面。）"),
        "evidence": {
            "diner_quotes": [
                {"quote": "天妇罗冷荞麦面很不错，不管是原味吃还是蘸汁，加芥末一口下去太爽了；剩下的蘸汁倒上荞麦汤喝，原汤化原食；天妇罗配萝卜泥超好吃，还有秋葵纳豆山药泥冷荞麦面、烤鱿鱼、荞麦布丁，一人食很适合。",
                 "dish": "天妇罗冷荞麦面", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=288551362", "date": "2026-04-05"},
                {"quote": "选了招牌冷荞麦面搭配山药泥，这个吃法有点意思，第一次吃到这样的荞麦面；手工荞麦面筋道爽滑，蘸上微甜的山药泥一口很满足；烤青花鱼外焦里嫩带着炭火香气。",
                 "dish": "冷荞麦面配山药泥", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=151543148", "date": "2025-05-20"},
            ],
            "platform_scores": [
                {"platform": "携程", "score": 4.5, "review_count": 300, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=288551362"},
            ],
            "negative_signals": ["客单逐年上涨", "夏天排队", "多分店品质参差"],
            "soft_ad_flags": ["澎湃日料地图推荐"],
            "traffic_signals": ["开17年老牌", "一人食吧台", "夏季冷荞麦旺季"],
        },
        "sources": [
            {"title": "携程 - 纹兵卫天山店(天妇罗冷荞麦)", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=288551362", "type": "ugc"},
            {"title": "携程 - 纹兵卫(冷荞麦配山药泥)", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=151543148", "type": "ugc"},
            {"title": "澎湃新闻 - 一份上海日料地图(纹兵卫手打荞麦)", "url": "https://m.thepaper.cn/newsDetail_forward_26380111", "type": "media"},
        ],
        "notes": "回归用例命中（纹兵卫多分店）。cuisine_paths 按附录A荞麦独立二级。荞麦道/ichi 见 candidates_list。坐标留空。",
    }

# ====== 执行补丁 ======
def patch_file(fname, patches, extra_new=None):
    p = DIR / fname
    rows = load(p)
    by_name = {r["name"]: r for r in rows}
    for key, fn in patches.items():
        for n in list(by_name):
            if key in n:
                by_name[n] = fn(by_name[n])
    out = list(by_name.values())
    if extra_new:
        out.append(extra_new())
    save(p, out)
    print(f"{fname}: {len(out)} records")

patch_file("raw_north_america.jsonl", {"Tacolicious": patch_tacolicious})
patch_file("raw_south_america.jsonl", {"El Bodegon": patch_el_bodegon})
patch_file("raw_europe.jsonl", {"Delight": patch_delight})
patch_file("raw_asia.jsonl", {"阿萨": patch_asa}, extra_new=monbei)
print("done")
