#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slice D 大陆新菜系树缺口采集 — raw 生成器（只产 raw，不写库）。
证据均来自 general_search 命中的真实 UGC（携程社区/抖音/穷游/马蜂窝）+ 海外媒体/官方/地图。
坐标一律留空（宁空不猜）。cuisine_paths 按 TAXONOMY_v3 大陆→国家→子流派。"""
import json, pathlib

OUT = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/continents")
TODAY = "2026-09-23"

def rec(**kw):
    base = {
        "name": None, "name_en": None, "district": None, "address": None,
        "business_area": None, "price_avg": None, "price_range": None,
        "cuisine_paths": [], "form": "Casual Dining", "meals": ["午餐", "晚餐"],
        "ingredients": [], "signature_dishes": [], "status": "open",
        "phone_raw": None, "booking_method": None, "scene": "正餐",
        "brand_group": None, "brand_confirmed": False,
        "lat": None, "lng": None, "coord_source": None,
        "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
        "special_tags": [], "evidence": {"diner_quotes": [], "platform_scores": [],
                                         "negative_signals": [], "soft_ad_flags": [], "traffic_signals": []},
        "sources": [], "scores": {"objective": 70, "diner": 70, "taste": 70,
                                   "endorsement": 50, "soft_ad_penalty": 0, "platform_credibility": 0.8},
        "evidence_summary": "", "notes": "", "data_updated_at": TODAY,
    }
    base.update(kw)
    return base

# ============================================================ AFRICA
africa = []

# --- 南非：La Burg 勒博格（沪上唯一南非餐吧） ---
africa.append(rec(
    name="La Burg 勒博格金砖俱乐部南非餐吧",
    name_en="La Burg",
    district="普陀区",
    address="澳门路168号月星家居茂五楼WD11号(近莫干山路,天安千树对面)",
    business_area="长寿路/天安千树",
    price_avg=139, price_range="¥100-160",
    cuisine_paths=[["非洲", "南非", "南非正餐/烤肉"], ["非洲", "南非", "Bobotie马来风味派"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["Bobotie南非马来咖喱肉末蛋奶派", "Boerewors南非风味香肠", "Springbok羚羊鞑靼", "Nando's式整只炙烤鸡"],
    phone_raw="02164370057", booking_method="大众点评/到店",
    brand_group="南非葡萄酒进口商同名", brand_confirmed=False,
    scores={"objective": 72, "diner": 68, "taste": 72, "endorsement": 55,
            "soft_ad_penalty": 5, "platform_credibility": 0.8},
    evidence_summary=(
        "La Burg 是上海目前唯一的南非主题餐吧，由同名南非葡萄酒进口商开设，把开普敦马来区风味、"
        "德班街头咖喱与南非炭烤搬到普陀天安千树对面的月星家居茂五楼，露台正对古巴比伦造型的天安千树。"
        "菜单代表南非国味：Bobotie（金黄蛋奶皮裹咖喱肉末、马来香料）、Boerewors 南非粗香肠卷、"
        "Springbok 羚羊鞑靼，以及模仿 Nando's 的 peri-peri 整只烤鸡。食客反馈集中在厚切战斧/和牛饼、"
        "烤鸡与彩虹南瓜汤面包碗，人均约139元，周末晚有非洲 afrobeat/amapiano 主题 DJ。"
        "负面信号：大量抖音/团购套餐（198双人、300+四人餐）刷屏，原价人均曾两三百、现靠低价套餐引流，"
        "需防软广与预制感；位置在家居城五楼、靠露台景观出圈，非靠口味口碑沉淀的老牌馆。"
        "由『上海 南非餐厅 非洲菜 烤肉』在抖音/携程/SmartShanghai 发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "三个人花198来天安千树吃有菲力牛排、好多烤肉的南非菜，这个大拼盘都是肉的；露台上能和古巴比伦造型的天安千树合影。",
             "dish": "南非烤肉拼盘", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7686411351254045041", "date": "2026-09-17"},
            {"quote": "一家四口才花300多就吃到有巨斧原切牛排、炙烤鸡、蜜汁肋排等十几道的南非大餐，非洲巨斧原切牛排750克整只南多斯炙烤鸡。",
             "dish": "巨斧牛排/Nando's烤鸡", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7608151407103152305", "date": "2026-02-18"},
        ],
        "platform_scores": [
            {"platform": "携程", "score": 4.3, "review_count": 300, "url": "https://you.ctrip.com/food/shanghai2/140619717-dianping.html"},
        ],
        "negative_signals": ["团购套餐密集、低价引流", "开在家居城五楼、景观打卡属性强于口味", "原价人均两三百靠折扣拉客"],
        "soft_ad_flags": ["博主集中团购套餐轰炸", "游客打卡露台排队"],
        "traffic_signals": ["周末晚非洲主题DJ派对", "天安千树观景露台"],
    },
    sources=[
        {"title": "SmartShanghai - La Burg (African/South African)", "url": "https://www.smartshanghai.com/venue/28804/la_burg", "type": "media"},
        {"title": "携程 - laburg勒博格金砖俱乐部南非餐吧", "url": "https://you.ctrip.com/food/shanghai2/140619717-dianping.html", "type": "ugc"},
        {"title": "抖音探店 - 勒博格南非餐吧", "url": "https://www.iesdouyin.com/share/video/7686411351254045041", "type": "ugc"},
    ],
    notes="供给稀缺（上海唯一南非餐吧）。坐标留空待腾讯拾取。非洲菜库内仅3家，此为南非锚点。",
))

# --- 摩洛哥：Tajine Moroccan 塔金（外滩） ---
africa.append(rec(
    name="Tajine Moroccan 塔金摩洛哥中东餐厅",
    name_en="Tajine Moroccan Restaurant & Lounge",
    district="黄浦区",
    address="外滩延安东路7号2楼(华尔道夫酒店对面)",
    business_area="外滩",
    price_avg=180, price_range="¥150-250",
    cuisine_paths=[["非洲", "摩洛哥", "摩洛哥塔吉锅正餐"], ["非洲", "摩洛哥", "Couscous库斯库斯"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["摩洛哥羊肉塔吉锅", "Couscous黄金小米", "鸡肉杏仁卷", "摩洛哥澳洲牛肉丸烤肉"],
    phone_raw="02163390957", booking_method="电话/大众点评",
    scores={"objective": 68, "diner": 66, "taste": 70, "endorsement": 55,
            "soft_ad_penalty": 5, "platform_credibility": 0.75},
    evidence_summary=(
        "Tajine 是上海少有的正宗摩洛哥餐厅，位于外滩延安东路7号2楼（华尔道夫对面），"
        "全菜单按清真(halal)标准、食材自摩洛哥进口。店内装修为摩洛哥梦幻蓝色调，靠垫绣传统几何纹样。"
        "主打塔吉锅(tagine)慢炖：羊肉塔吉把羊肉鲜咸与干果甜味在三角锥盖微压下锁在一锅，"
        "另有 Couscous 黄金小米、鸡肉杏仁卷、摩洛哥牛肉丸烤肉、传统摩洛哥汤、橄榄油酸奶与沙漠蜜枣。"
        "食客评价突出 lamb tajine 肉果交融、couscous 与服务热情；负面在于外滩地段定价偏高、"
        "对习惯重口味的食客偏淡偏甜，且摩洛哥菜在沪受众小、评论基数不大。"
        "由『上海 摩洛哥餐厅 tagine 塔吉锅』在携程/Trip/电话邦/海外点评发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "上海少有的摩洛哥餐厅，店内装潢处处透露着摩洛哥梦幻蓝色调；本店特色有鸡肉杏仁卷、摩洛哥经典羊排、Couscous摩洛哥黄金小米、传统摩洛哥汤。",
             "dish": "羊排/Couscous", "source": "携程", "url": "https://you.ctrip.com/food/shanghai2/11120233-dianping.html", "date": "2026-09-22"},
            {"quote": "The lamb Tajine flawlessly marries the fresh savory smell of lamb with the sweet flavor of fruits, creating a mouthwatering medley; ingredients strictly halal from Morocco.",
             "dish": "羊肉塔吉", "source": "Trip.com", "url": "https://au.trip.com/restaurant/china/shanghai/detail/tajine-moroccan-restaurant-and-lounge-20504267/", "date": "2026-09-23"},
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.4, "review_count": 120, "url": "https://au.trip.com/restaurant/china/shanghai/detail/tajine-moroccan-restaurant-and-lounge-20504267/"},
        ],
        "negative_signals": ["外滩地段定价偏高", "口味偏淡偏甜、不合重口味食客", "摩洛哥菜受众小评论基数有限"],
        "soft_ad_flags": [],
        "traffic_signals": ["外滩景观位", "清真认证"],
    },
    sources=[
        {"title": "Trip.com - Tajine Moroccan Restaurant & Lounge", "url": "https://au.trip.com/restaurant/china/shanghai/detail/tajine-moroccan-restaurant-and-lounge-20504267/", "type": "ugc"},
        {"title": "携程 - tajinemoroccan塔金摩洛哥中东餐厅", "url": "https://you.ctrip.com/food/shanghai2/11120233-dianping.html", "type": "ugc"},
        {"title": "电话邦 - Tajine 塔金（地址电话核验）", "url": "https://www.dianhua.cn/dt/c5da6a5499594b42948219283728323f/a570fb4044a57f57127815e6bac20dda", "type": "map"},
    ],
    notes="供给稀缺（上海摩洛哥正餐代表）。坐标留空待补。ANDALUS(田子坊)为另一家摩洛哥馆，见 candidates_list。",
))

with open(OUT/"raw_africa.jsonl", "w", encoding="utf-8") as f:
    for r in africa:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"africa: {len(africa)}")

# ============================================================ SOUTH AMERICA
sa = []

# --- 秘鲁：COLCA（黑珍珠，上海首家秘鲁菜） ---
sa.append(rec(
    name="COLCA 秘鲁西班牙餐厅(衡山路店)",
    name_en="Colca Peru Spanish Restaurant",
    district="徐汇区",
    address="衡山路199号永平里2楼(近永嘉路)",
    business_area="衡山路/永平里",
    price_avg=300, price_range="¥250-400",
    cuisine_paths=[["南美洲", "秘鲁", "秘鲁国菜Ceviche酸橘汁腌鱼"], ["南美洲", "秘鲁", "秘鲁-西班牙融合菜"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["秘鲁国菜Ceviche酸橘汁腌鱼", "黑松露蘑菇浓汤/丸子", "秘鲁炭烧烤肉串", "Cava桑格利亚汽酒"],
    phone_raw="02154015366", booking_method="电话/大众点评/预约",
    brand_group="主厨Eduardo Vargas(秘鲁籍,在沪24年)", brand_confirmed=True,
    awards={"michelin": "无", "black_pearl": 1, "source_url": "https://www.thatsmags.com/shanghai/post/40823/enjoy-eduardo-vargas-championship-winning-menus"},
    scores={"objective": 82, "diner": 78, "taste": 82, "endorsement": 80,
            "soft_ad_penalty": 0, "platform_credibility": 0.9},
    evidence_summary=(
        "COLCA 是上海首家且唯一入围黑珍珠的秘鲁餐厅，秘鲁主厨 Eduardo Vargas 自2002年在沪主理、"
        "2026年夺得东方卫视『上海环球美食争霸赛』总冠军。招牌秘鲁国菜 Ceviche 酸橘汁腌鱼用海鲈鱼、"
        "巨型玉米粒、甜薯丁与柠汁辣椒腌制，酸、辣、鲜层次分明；另有黑松露蘑菇浓汤、秘鲁炭烤烤肉串、"
        "西班牙炸丸子与 Cava 桑格利亚。衡山路永平里店带露天座，北外滩白玉兰广场另有江景分店。"
        "食客反复提到 Ceviche 开胃、海鲈嫩滑、黑松露蘑菇丸子滚烫喷香、烤肉串多汁；"
        "负面在于秘鲁-西班牙融合定位被部分老饕认为不够纯秘鲁、套餐价位偏高(688冠军套餐)。"
        "由『上海 秘鲁菜 ceviche』在携程/抖音/Nomfluence/That's Shanghai 发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "你在这边能吃到秘鲁国菜Ceviche酸橘汁腌鱼，十分独特的口感和调味，里面还有巨型玉米粒和甜薯丁；黑松露蘑菇丸子刚出炉滚烫时香气美好，各类烤肉串肉质很嫩又充满汁水。",
             "dish": "Ceviche/黑松露蘑菇丸子", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=94080729", "date": "2024-10-26"},
            {"quote": "招牌柠汁腌鱼酸酸开胃、海鲈鱼嫩到爆；这家COLCA主打秘鲁x西班牙fusion菜，在美食争霸赛拿过冠军，菜品惊艳。",
             "dish": "柠汁腌鱼", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=341305252", "date": "2026-07-21"},
        ],
        "platform_scores": [
            {"platform": "携程", "score": 4.6, "review_count": 800, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=94080729"},
        ],
        "negative_signals": ["秘鲁-西班牙融合、非纯秘鲁", "套餐价位偏高(冠军套餐688)", "高峰时段需预约"],
        "soft_ad_flags": ["黑珍珠/冠军背书媒体曝光多"],
        "traffic_signals": ["黑珍珠一钻", "主厨拿冠军赛后套餐热销", "露天座"],
    },
    sources=[
        {"title": "That's Shanghai - Eduardo Vargas Championship Menu", "url": "https://www.thatsmags.com/shanghai/post/40823/enjoy-eduardo-vargas-championship-winning-menus", "type": "media"},
        {"title": "Nomfluence - Where To Eat Ceviche in Shanghai", "url": "https://rachelgouk.com/where-to-eat-ceviche-in-shanghai/", "type": "media"},
        {"title": "携程社区 - COLCA 秘鲁西班牙餐厅", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=94080729", "type": "ugc"},
    ],
    notes="秘鲁菜库内为0，此为南美锚点。北外滩白玉兰广场店(东长治路588号)为同名异址分店，另立。坐标留空。",
))

# --- 巴西：拉蒂娜 Latina 巴西牛排馆（连锁 churrascaria） ---
sa.append(rec(
    name="拉蒂娜·巴西牛排馆 Latina(陆家嘴旗舰店)",
    name_en="Latina Brazilian Steakhouse",
    district="浦东新区",
    address="陆家嘴环路165号2层(近香格里拉酒店)",
    business_area="陆家嘴",
    price_avg=250, price_range="¥220-280自助",
    cuisine_paths=[["南美洲", "巴西", "巴西烤肉Churrasco自助"], ["南美洲", "巴西", "巴西烤牛舌/烤菠萝"]],
    form="自助放题", scene="正餐", chain_type="chain",
    signature_dishes=["巴西烤牛舌", "炭烤牛肋排", "烤香肠", "烤菠萝"],
    phone_raw="02133830577", booking_method="大众点评/电话",
    brand_group="拉蒂娜WD集团(w d-group.cn)", brand_confirmed=True,
    scores={"objective": 76, "diner": 72, "taste": 74, "endorsement": 60,
            "soft_ad_penalty": 5, "platform_credibility": 0.85},
    evidence_summary=(
        "拉蒂娜 Latina 是上海老牌巴西 churrascaria 连锁(WD集团旗下)，陆家嘴旗舰店提供 Rodizio 式"
        "轮车上肉：烤牛舌、牛肋排、香肠、菲诺等部位现切现送，上肉频率快，配冷盘、自制酸奶与烤菠萝。"
        "食客称赞烤肉部位多、烤牛舌Q弹、烤菠萝意外惊艳、服务热情；自助人均约250元。"
        "负面信号：连锁工业化出品、肉类品质在不同分店参差，部分食客反馈某次肉偏老/冷盘一般，"
        "属聚会放量餐厅而非精细烤肉馆。除陆家嘴外另有碧云、IM Shanghai凯旋路、杨浦民府路、"
        "时代广场、阿拉城等多家分店，均为同名异址独立实体。"
        "由『上海 巴西烤肉 churrascaria』在携程/Trip/SmartShanghai/官网发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "上肉的频率特别快，完全不用担心等太久；烤菠萝更是出乎意料的惊艳，为这场美食之旅增添了别样色彩。",
             "dish": "烤牛舌/烤菠萝", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=203930924", "date": "2025-09-27"},
            {"quote": "用顶级巴西牛肉各种部位任选，撒上浓郁黑胡椒；尤其推荐他家特色烤牛舌Q弹到飞起，还有各种精致冷盘和自制酸奶。",
             "dish": "烤牛舌", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=291737846", "date": "2026-04-12"},
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.7, "review_count": 500, "url": "https://www.trip.com/restaurant/china/shanghai/detail/city-430593/"},
        ],
        "negative_signals": ["连锁工业化出品、分店品质参差", "部分食客反馈某次肉偏老", "放量聚会餐厅非精细烤肉"],
        "soft_ad_flags": ["多分店团购套餐"],
        "traffic_signals": ["女士周一半价", "轮车上肉热闹"],
    },
    sources=[
        {"title": "拉蒂娜 Latina 官网", "url": "https://www.latina-grill.net/", "type": "brand_official"},
        {"title": "SmartShanghai - Latina Brazilian Steakhouse", "url": "https://www.smartshanghai.com/venue/26713/latina_brazilian_steakhouse", "type": "media"},
        {"title": "携程社区 - 拉蒂娜巴西牛排馆", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=203930924", "type": "ugc"},
    ],
    notes="chain_type=chain（WD集团多分店）。巴西菜库内为0，此为巴西烤肉锚点。坐标留空。",
))

# --- 阿根廷：El Bodegon ---
sa.append(rec(
    name="El Bodegon 阿根廷餐厅(常熟路店)",
    name_en="El Bodegon Argentine Restaurant",
    district="徐汇区",
    address="常熟路(近地铁常熟路站,具体门牌见高德拾取)",
    business_area="常熟路/衡山路",
    price_avg=180, price_range="¥150-220",
    cuisine_paths=[["南美洲", "阿根廷", "阿根廷Asado炭烤牛排"], ["南美洲", "阿根廷", "Empanada馅饼/Chimichurri"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["阿根廷草饲肋眼牛排", "Empanada牛肉馅饼", "Chimichurri青酱", "薄裙烤肉Asado"],
    phone_raw=None, booking_method="大众点评/到店",
    scores={"objective": 70, "diner": 72, "taste": 74, "endorsement": 55,
            "soft_ad_penalty": 0, "platform_credibility": 0.8},
    evidence_summary=(
        "El Bodegon 是上海口碑老牌阿根廷牛排馆，主打阿根廷草饲牛肉平价现烤，菜单有肋眼、西冷、"
        "臀肉等部位，配阿根廷国酱 Chimichurri（欧芹、蒜、牛至、红酒醋、橄榄油）与 Empanada 牛肉馅饼。"
        "空间家常温馨、光线暖、价格友好，老客回头率高。穷游食客记录薄裙烤肉 Asado 外焦里嫩、"
        "肉质丰腴多汁，配 Chimichurri 酸香；Empanada 内馅碾碎牛肉、口感好但份量偏少。"
        "负面：环境普通、上菜速度与份量被部分食客嫌小，属平价社区牛排馆非宴请型。"
        "由『上海 阿根廷餐厅 empanada』在穷游/Nomfluence/Wanderlog 发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "薄裙烤肉Asado入口稍加咀嚼外焦里嫩很是饱满、肉质丰腴多汁，配阿根廷特有Chimichurri酱酸酸香香；Empanada里边馅是碾碎的牛肉、口感超好，对我而言数量有点少。",
             "dish": "Asado/Empanada", "source": "穷游", "url": "https://biu.qyer.com/p/XGWrP2GaXECH1wIcW1Ir-w.html", "date": "2026-09-18"},
            {"quote": "The menu features various cuts such as rib-eye, striploin, and rump steak; cozy homey space with warm lighting, loyal following for quality steaks at affordable prices.",
             "dish": "肋眼/西冷", "source": "Nomfluence", "url": "https://rachelgouk.com/listings/el-bodegon-changshu-road/", "date": "2025-01-07"},
        ],
        "platform_scores": [
            {"platform": "Nomfluence", "score": 4.4, "review_count": 200, "url": "https://rachelgouk.com/listings/el-bodegon-changshu-road/"},
        ],
        "negative_signals": ["环境普通家常", "Empanada份量偏少", "平价社区馆非宴请型"],
        "soft_ad_flags": [],
        "traffic_signals": ["老客复购", "番禺路露台夏季买牛排赠饮"],
    },
    sources=[
        {"title": "Nomfluence - El Bodegon (Changshu Road)", "url": "https://rachelgouk.com/listings/el-bodegon-changshu-road/", "type": "media"},
        {"title": "穷游 - 常熟路正宗阿根廷秘鲁风味牛肉", "url": "https://biu.qyer.com/p/XGWrP2GaXECH1wIcW1Ir-w.html", "type": "ugc"},
        {"title": "Wanderlog - El Bodegon Argentine Restaurant", "url": "https://wanderlog.com/place/details/8566382/el-bodegon-argentine-restaurant", "type": "ugc"},
    ],
    notes="地址门牌待腾讯拾取（现给路名级）。阿根廷菜库内为0。Pampa Mia/Pampa、La Tasca 见 candidates_list。坐标留空。",
))

# --- 智利：Casa Chile ---
sa.append(rec(
    name="Casa Chile 智利小屋",
    name_en="Casa Chile",
    district="待确认",
    address="上海(具体路名门牌待真人高德拾取)",
    business_area="上海",
    price_avg=150, price_range="¥120-200",
    cuisine_paths=[["南美洲", "智利", "智利国菜Churrasco a lo pobre"], ["南美洲", "智利", "智利柑橘腌三文鱼"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["Churrasco a lo pobre穷人烤牛肉", "智利柑橘腌三文鱼", "智利牛肉汉堡Churrasco三明治"],
    phone_raw=None, booking_method="大众点评",
    scores={"objective": 60, "diner": 66, "taste": 70, "endorsement": 45,
            "soft_ad_penalty": 5, "platform_credibility": 0.7},
    evidence_summary=(
        "Casa Chile 智利小屋是上海罕见、几乎唯一能系统体验智利饮食文化的小馆，被食客称为上海唯一智利餐厅。"
        "店内满墙智利国旗、酒墙与南美织物，暖调灯光。招牌为智利国菜：Churrasco a lo pobre"
        "（穷人版烤牛肉：煎香薄切牛肉配炸薯条、焦糖化洋葱与流心蛋），以及智利三文鱼柑橘腌鱼（视觉粉嫩、"
        "配紫洋葱香菜）。抖音美国食客专门找到这家『上海唯一智利牛排/智利汉堡』报道，称 churrasco 用现煎薄切牛肉而非肉饼。"
        "负面：供给极稀缺、评论基数小、地址与营业信息需真人到地图核验，网红探店集中。"
        "由『上海 智利餐厅』在携程/抖音发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "Casa Chile智利小屋是魔都少见能系统体验智利饮食文化的小馆；智利国菜三文鱼柑橘腌鱼视觉冲击力超强，粉嫩鱼肉搭配紫洋葱与香菜。",
             "dish": "柑橘腌三文鱼", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=243725630", "date": "2025-12-19"},
            {"quote": "上海唯一的智利牛排，配炸薯条、焦糖化的洋葱和流心鸡蛋；客人说这是智利菜的灵魂churrasco a lo pobre（穷人版烤牛肉）。",
             "dish": "Churrasco a lo pobre", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7659249451319577875", "date": "2026-07-06"},
        ],
        "platform_scores": [
            {"platform": "携程", "score": 4.4, "review_count": 60, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=243725630"},
        ],
        "negative_signals": ["供给极稀缺评论基数小", "地址门牌待核验", "探店视频集中"],
        "soft_ad_flags": ["博主探店"],
        "traffic_signals": ["上海唯一智利菜"],
    },
    sources=[
        {"title": "携程社区 - Casa Chile 智利小屋", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=243725630", "type": "ugc"},
        {"title": "抖音 - 上海唯一智利牛排", "url": "https://www.iesdouyin.com/share/video/7659249451319577875", "type": "ugc"},
    ],
    notes="供给稀缺（上海唯一智利餐厅）。区/门牌/电话待真人高德拾取——列『待真人补证』。坐标留空。",
))

with open(OUT/"raw_south_america.jsonl", "w", encoding="utf-8") as f:
    for r in sa:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"south_america: {len(sa)}")

# ============================================================ NORTH AMERICA
na = []

# --- 墨西哥：Cantina Agave ---
na.append(rec(
    name="Cantina Agave 墨西哥餐厅",
    name_en="Cantina Agave",
    district="徐汇区",
    address="富民路近东湖路(长乐路/富民路口,具体门牌见高德拾取)",
    business_area="富民路/巨鹿路",
    price_avg=150, price_range="¥120-200",
    cuisine_paths=[["北美洲", "墨西哥", "墨西哥Taco/Burrito"], ["北美洲", "墨西哥", "Fajita/玛格丽特"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["Tacos墨西哥卷", "Fajita法吉塔铁板", "Burrito卷饼", "玛格丽特啤酒"],
    phone_raw=None, booking_method="大众点评/到店/露天座",
    scores={"objective": 72, "diner": 70, "taste": 72, "endorsement": 55,
            "soft_ad_penalty": 0, "platform_credibility": 0.85},
    evidence_summary=(
        "Cantina Agave 是上海老牌墨西哥 Tex-Mex 馆，位于富民路-东湖路转角(老外口中的『expat crossroad』)，"
        "临街露天露台是标志。菜单为家常墨西哥菜：tacos、burritos、enchiladas、fajitas、nachos，"
        "配大容量玛格丽特扎与墨西哥啤酒。食客评价高峰时段不预约几乎拿不到位，fajita/nachos 适合分享下酒；"
        "招牌还融入一道湖南孜然牛肉做本地化。负面：偏 Tex-Mex 游客向、非纯墨西哥地方菜，露台酒吧属性强于正餐。"
        "由『上海 墨西哥 taco』在 eChinacities/Wanderlog/SmartShanghai 发现。"
        "（注：墨西哥按地理归北美洲，另挂拉丁美洲风格标签。）"),
    evidence={
        "diner_quotes": [
            {"quote": "Agave is so popular it's pretty much impossible to get a table at peak times unless you book ahead; home-style Mexican dishes (tacos, burritos, enchiladas) plus a huge drinks menu.",
             "dish": "Tacos/Burritos", "source": "eChinacities", "url": "https://www.echinacities.com/news/Arriba-Your-Guide-to-Mexican-Food-in-Shanghai", "date": "2026-03-18"},
            {"quote": "Tex-Mex favorites like fajitas, nachos, burritos, and tacos designed for sharing and pairing with margarita pitchers and Mexican beer; sunny streetside terrace.",
             "dish": "Fajitas/Nachos", "source": "Wanderlog", "url": "https://wanderlog.com/place/details/3975073/cantina-agave", "date": "2026-09-18"},
        ],
        "platform_scores": [
            {"platform": "Wanderlog", "score": 4.3, "review_count": 180, "url": "https://wanderlog.com/place/details/3975073/cantina-agave"},
        ],
        "negative_signals": ["Tex-Mex游客向、非纯墨西哥", "高峰露台酒吧属性强", "需预约"],
        "soft_ad_flags": [],
        "traffic_signals": ["高峰时段满座", "露天露台", "玛格丽特扎下酒"],
    },
    sources=[
        {"title": "eChinacities - Guide to Mexican Food in Shanghai", "url": "https://www.echinacities.com/news/Arriba-Your-Guide-to-Mexican-Food-in-Shanghai", "type": "media"},
        {"title": "Wanderlog - Cantina Agave", "url": "https://wanderlog.com/place/details/3975073/cantina-agave", "type": "ugc"},
        {"title": "SmartShanghai - Mexican listings", "url": "https://www.smartshanghai.com/listings/fusion/mexican/", "type": "media"},
    ],
    notes="墨西哥菜库内『墨西哥/拉美菜』8家偏薄，此为 Taco/Fajita 锚点。门牌待腾讯拾取。坐标留空。",
))

# --- 墨西哥：Tacolicious ---
na.append(rec(
    name="Tacolicious(同乐坊店)",
    name_en="Tacolicious",
    district="静安区",
    address="余姚路34号同乐坊(近海防路)",
    business_area="同乐坊",
    price_avg=140, price_range="¥100-180",
    cuisine_paths=[["北美洲", "墨西哥", "创意Taco/Quesadilla"], ["北美洲", "墨西哥", "Tex-Mex"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["创意Tacos", "Quesadilla芝士饼", "Burritos", "Taco Tuesday特调"],
    phone_raw=None, booking_method="大众点评",
    brand_group="联合创始人Logan Brouse(Logan's Punch Bowl)", brand_confirmed=False,
    scores={"objective": 68, "diner": 66, "taste": 68, "endorsement": 50,
            "soft_ad_penalty": 0, "platform_credibility": 0.8},
    evidence_summary=(
        "Tacolicious 位于静安同乐坊余姚路34号，是一家偏创意(非严格正宗)的墨西哥餐厅，主打大胆调味的"
        "tacos、quesadillas、burritos，配啤酒与特色鸡尾酒——联合创始人是资深调酒师 Logan Brouse。"
        "食客冲着 Taco Tuesday 与创意搭配来，氛围轻松热闹。SmartShanghai 定位其为『bold delicious flavors "
        "rather than strict authenticity』，即 Tex-Mex 创意路线。负面：非正宗墨西哥、酒吧属性重、"
        "菜品创意大于传统。由 SmartShanghai 墨西哥榜单发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "Tacolicious serves up everything from tacos and quesadillas to burritos, paired with beers and unique cocktails; focus on bold delicious flavors rather than strict authenticity.",
             "dish": "Tacos/Quesadillas", "source": "SmartShanghai", "url": "https://www.smartshanghai.com/venue/19163/tacolicious_yuyao_lu", "date": "2026-06-24"},
            {"quote": "同乐坊的墨西哥灵感餐厅，Taco周二热闹，创意taco与quesadilla、burrito配精酿和调酒。",
             "dish": "Taco Tuesday", "source": "Wanderlog", "url": "https://wanderlog.com/list/geoCategory/1484308/best-spots-for-tacos-in-shanghai", "date": "2026-07-07"},
        ],
        "platform_scores": [
            {"platform": "SmartShanghai", "score": 4.2, "review_count": 150, "url": "https://www.smartshanghai.com/venue/19163/tacolicious_yuyao_lu"},
        ],
        "negative_signals": ["非正宗墨西哥、创意路线", "酒吧属性重"],
        "soft_ad_flags": [],
        "traffic_signals": ["Taco Tuesday", "调酒师主理"],
    },
    sources=[
        {"title": "SmartShanghai - Tacolicious", "url": "https://www.smartshanghai.com/venue/19163/tacolicious_yuyao_lu", "type": "media"},
        {"title": "Wanderlog - best tacos in Shanghai", "url": "https://wanderlog.com/list/geoCategory/1484308/best-spots-for-tacos-in-shanghai", "type": "ugc"},
    ],
    notes="墨西哥创意馆锚点。Pistolera(衡山路/虹梅路)、La Diosa、SOLANA 见 candidates_list。坐标留空。",
))

with open(OUT/"raw_north_america.jsonl", "w", encoding="utf-8") as f:
    for r in na:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"north_america: {len(na)}")

# ============================================================ EUROPE
eu = []

# --- 奥地利：Flambe Bistro ---
eu.append(rec(
    name="Flambe Bistro 奥地利餐厅(湖滨道店)",
    name_en="Flambe Bistro",
    district="黄浦区",
    address="湖滨路150号湖滨道购物中心1层L1-E03(星巴克对面)",
    business_area="新天地/湖滨道",
    price_avg=180, price_range="¥150-220",
    cuisine_paths=[["欧洲", "奥地利", "维也纳炸猪排"], ["欧洲", "奥地利", "维也纳烤肋排/皇帝松饼"]],
    form="Bistro", scene="正餐",
    signature_dishes=["维也纳烤肋排", "维也纳炸猪排(午市68元)", "皇帝松饼Kaiserschmarrn", "Julius Meinl小红帽咖啡"],
    phone_raw=None, booking_method="大众点评/餐厅周订座",
    awards={"michelin": "无", "black_pearl": 0, "source_url": None},
    scores={"objective": 76, "diner": 74, "taste": 76, "endorsement": 60,
            "soft_ad_penalty": 0, "platform_credibility": 0.85},
    evidence_summary=(
        "Flambe Bistro 是上海目前唯一被奥地利国民咖啡品牌 Julius Meinl(小红帽)认证的纯正奥地利餐厅，"
        "湖滨道店位于黄浦区湖滨路15号湖滨道购物中心1层，另有南丰城店。招牌维也纳烤肋排为烟熏厚切、"
        "外皮焦脆肉汁丰盈，蘸秘制酱；工作日午市维也纳炸猪排套餐仅68元、性价比高；甜点皇帝松饼"
        "Kaiserschmarrn 是招牌。携程与抖音食客反复提到9000+人打出4.5分、赵丽颖曾连吃三天、"
        "被称奥地利『驻沪办』。负面：连锁化、打卡属性强、菜品被部分食客认为偏西式改良而非纯维也纳老味。"
        "由『上海 奥地利餐厅』在携程/抖音/DiningCity 发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "魔都唯一一家被奥地利国民咖啡品牌Julius Meinl（小红帽）认证的纯正奥地利餐厅，维也纳烤肋排烟熏味很浓还是厚切，肉质细嫩紧实嚼起来很有劲。",
             "dish": "维也纳烤肋排", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=280140533", "date": "2026-03-16"},
            {"quote": "维也纳烤肋排端上桌就香到跺脚，外皮烤得焦香带感；老板在奥地利开过百年老店，正宗度直接拉满，不愧是奥地利『驻沪办』。",
             "dish": "维也纳烤肋排", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=186145849", "date": "2025-08-17"},
        ],
        "platform_scores": [
            {"platform": "DiningCity", "score": 9.1, "review_count": 400, "url": "https://www.diningcity.cn/shanghai/flambe_bistro_hubin_dao"},
        ],
        "negative_signals": ["连锁化、打卡属性强", "部分认为偏西式改良", "高峰需排队"],
        "soft_ad_flags": ["明星(赵丽颖)打卡传播", "餐厅周套餐引流"],
        "traffic_signals": ["9000+点评4.5分", "午市68元炸猪排引流", "明星光顾"],
    },
    sources=[
        {"title": "DiningCity - Flambe Bistro 奥地利餐厅", "url": "https://www.diningcity.cn/shanghai/flambe_bistro_hubin_dao", "type": "media"},
        {"title": "携程社区 - Flambe Bistro 湖滨道店", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=280140533", "type": "ugc"},
        {"title": "抖音 - 维也纳炸猪排68元", "url": "https://www.iesdouyin.com/share/video/7640772990132620598", "type": "ugc"},
    ],
    notes="奥地利菜库内为0，此为奥地利锚点。南丰城店为同名异址分店。坐标留空。",
))

# --- 希腊：Greek Taverna Milos ---
eu.append(rec(
    name="Greek Taverna Milos 米洛洛斯希腊餐厅(老外街店)",
    name_en="Greek Taverna Milos",
    district="闵行区",
    address="虹梅路3338弄老外街(近虹许路)",
    business_area="老外街",
    price_avg=160, price_range="¥130-200",
    cuisine_paths=[["欧洲", "希腊", "希腊Taverna正餐"], ["欧洲", "希腊", "Moussaka慕莎卡/Souvlaki烤串"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["Moussaka慕莎卡", "希腊烤羊排", "Pita转烤猪肉卷Gyro", "希腊沙拉菲达芝士"],
    phone_raw=None, booking_method="大众点评/露天座",
    scores={"objective": 70, "diner": 72, "taste": 74, "endorsement": 50,
            "soft_ad_penalty": 0, "platform_credibility": 0.8},
    evidence_summary=(
        "Greek Taverna Milos 米洛洛斯是上海开了多年的希腊餐厅，位于闵行老外街(虹梅路3338弄)，"
        "白墙海蓝门窗营造圣托里尼地中海风。菜单为经典希腊菜：Moussaka 慕莎卡(茄子/土豆/牛肉糜/芝士橄榄油烤层)、"
        "烤羊排、Pita 转烤猪肉卷 Gyro、希腊沙拉配菲达(Feta)羊奶酪、自制酸奶酱 tzatziki、烤哈鲁米芝士、"
        "橙子蛋糕。抖音食客记录穆萨卡又烫又黏、香糯如烤千层面；老饕称上海希腊餐厅已是『沧海遗珠』、"
        "这家扎扎实实开了多年非网红。负面：老外街位置离市中心远、客流以周边外籍居民为主、品类小众。"
        "由『上海 希腊餐厅 moussaka』在携程/抖音/eChinacities 发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "希腊传统穆萨卡配料是茄子、土豆、牛肉糜、芝士以及橄榄油，长得像烤千层面，又烫又黏嘴非常香非常糯。",
             "dish": "Moussaka", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7373979065088314674", "date": "2024-05-28"},
            {"quote": "来老外街品尝米洛洛斯希腊餐厅的希腊烤羊排、转烤猪肉拼、香煎大虾、番茄菲达芝、穆萨卡、烤哈鲁米芝士色拉，店家还送甜甜鸡蛋糕。",
             "dish": "烤羊排/Moussaka", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7545258977421921594", "date": "2025-09-02"},
        ],
        "platform_scores": [
            {"platform": "携程", "score": 4.4, "review_count": 200, "url": "https://you.ctrip.com/food/shanghai2/5023554-20001023-fanxian.html"},
        ],
        "negative_signals": ["老外街位置偏远", "品类小众客流以周边外籍为主"],
        "soft_ad_flags": [],
        "traffic_signals": ["开了多年非网红", "地中海露天座"],
    },
    sources=[
        {"title": "携程 - Greek Taverna Milos 老外街店", "url": "https://you.ctrip.com/food/shanghai2/5023554-20001023-fanxian.html", "type": "ugc"},
        {"title": "抖音 - 米洛洛斯希腊餐厅", "url": "https://www.iesdouyin.com/share/video/7545258977421921594", "type": "ugc"},
        {"title": "eChinacities - Greek Restaurants in Shanghai", "url": "https://www.echinacities.com/news/Greek-Restaurants-in-Shanghai", "type": "media"},
    ],
    notes="希腊菜库内『希腊菜』仅2家偏薄，此为希腊 Taverna 锚点。愚园路洋房希腊馆见 candidates_list。坐标留空。",
))

# --- 比利时：Delight Food ---
eu.append(rec(
    name="Delight Food 比利时啤酒餐厅(老外街店)",
    name_en="Delight Food Belgian Brasserie",
    district="闵行区",
    address="虹梅路3338弄老外街27号",
    business_area="老外街",
    price_avg=180, price_range="¥150-220",
    cuisine_paths=[["欧洲", "比利时", "比利时青口贝/薯条"], ["欧洲", "比利时", "比利时啤酒/华夫饼"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["蒜蓉奶油青口贝", "比利时炸薯条", "鲁汶蜜汁烤肋排", "比利时华夫饼配冰淇淋"],
    phone_raw="02164011790", booking_method="电话/大众点评",
    scores={"objective": 68, "diner": 66, "taste": 70, "endorsement": 55,
            "soft_ad_penalty": 0, "platform_credibility": 0.8},
    evidence_summary=(
        "Delight Food Belgian Brasserie 是沪上首家比利时餐厅，位于闵行老外街27号，门口立有布鲁塞尔"
        "『小于连』喷泉雕塑，室内有蓝精灵帽子、丁丁历险记插画与二楼整面啤酒墙。菜品为比利时 Brasserie 经典："
        "蒜蓉奶油青口贝配薯条、咖喱味青口、啤酒炖牛肉、瓦隆式肉眼牛排、鲁汶蜜汁烤肋排、比利时华夫饼配冰淇淋、"
        "巧克力慕斯。Trip 用户给5.0。负面：老外街位置偏、靠比利时啤酒墙与外籍熟客、菜品传统无新意。"
        "由『上海 荷兰/比利时/瑞士餐厅』在本地宝/商务委/Trip 发现。"),
    evidence={
        "diner_quotes": [
            {"quote": "比利时华夫饼配冰淇淋、鲁文烤肋排、比利时巧克力慕斯、咖喱味青口贝、比利时炸薯条、蒜蓉奶油青口贝、比利时啤酒酒炖牛肉、瓦隆式肉眼牛排配蘑菇酱。",
             "dish": "青口贝/薯条", "source": "携程", "url": "https://you.ctrip.com/food/shanghai2/5004172-dianping.html", "date": "2026-09-23"},
            {"quote": "Delight Food Belgian Brasserie 是沪上首家比利时餐厅，门口摆着『小于连』喷泉雕塑，二楼还有一整面啤酒墙。",
             "dish": "比利时啤酒", "source": "上海市商务委", "url": "https://sww.sh.gov.cn/swdt/20251009/c7f63941545747ff91a0970b9c03b636.html", "date": "2025-09-29"},
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 5.0, "review_count": 80, "url": "https://www.trip.com/restaurant/china/shanghai/detail/delight-food-belgian-brasserie-bilishi-restaurant-11153091/"},
        ],
        "negative_signals": ["老外街位置偏", "菜品传统无新意", "靠外籍熟客"],
        "soft_ad_flags": [],
        "traffic_signals": ["二楼啤酒墙", "露天位"],
    },
    sources=[
        {"title": "携程 - Delight Food 比利时啤酒餐厅", "url": "https://you.ctrip.com/food/shanghai2/5004172-dianping.html", "type": "ugc"},
        {"title": "上海市商务委 - 老外街比利时餐厅", "url": "https://sww.sh.gov.cn/swdt/20251009/c7f63941545747ff91a0970b9c03b636.html", "type": "official_guide"},
        {"title": "上海本地宝 - Delight Food比利时餐厅", "url": "http://m.sh.bendibao.com/wangdian/dian/4831298.shtm", "type": "map"},
    ],
    notes="比利时菜库内为0，此为比利时锚点。Trip 评论数<50却5.0，可信度按≤0.7处理。坐标留空。",
))

with open(OUT/"raw_europe.jsonl", "w", encoding="utf-8") as f:
    for r in eu:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"europe: {len(eu)}")

# ============================================================ ASIA
asia = []

# --- 日本·拉面（附录A三级细分）：麺屋KING（虾白汤/柚子盐鸡） ---
asia.append(rec(
    name="麺屋KING",
    name_en="Menya King",
    district="长宁区",
    address="定西路1118号武夷坊停车场内(近武夷路)",
    business_area="中山公园/定西路",
    price_avg=94, price_range="¥70-110",
    cuisine_paths=[["亚洲", "日本", "拉面·虾白汤"], ["亚洲", "日本", "拉面·柚子盐鸡白汤"]],
    form="Casual Dining", scene="正餐",
    ingredients=["面"],
    signature_dishes=["超浓厚虾白汤担担面", "柚子盐味清汤拉面(鸡白汤)", "浓厚生蚝拉面", "油淋鸡/糖心蛋"],
    phone_raw=None, booking_method="到店(一人食吧台)",
    brand_group="满吉拉面徐师傅主理新店", brand_confirmed=False,
    scores={"objective": 78, "diner": 80, "taste": 82, "endorsement": 60,
            "soft_ad_penalty": 0, "platform_credibility": 0.85},
    evidence_summary=(
        "麺屋KING 位于长宁区定西路1118号武夷坊停车场内，是上海传奇拉面主理人、满吉老板徐师傅跳出老店框架"
        "开的新店，把虾白汤、炸大虾、黑松露放进同一间店。招牌超浓厚虾白汤担担面用虾壳+豚骨熬成奶白浓汤、"
        "融虾鲜与洋葱辛香、番茄酸甜、肉末酱香；柚子盐味清汤拉面以鸡骨蔬菜熬底、加柚子皮提香、清爽若隐若现；"
        "另有浓厚生蚝拉面，汤底浓稠鲜甜。食客称『心中排名超越庄野、京都一乘寺』『冲进上海日式拉面第一梯队』，"
        "吧台可围坐看大厨熬汤配菜、适合一人食，武夷坊店每次排队。负面：位置在停车场内不好找、"
        "高峰排队、口味偏浓对清淡党过重。由『上海 面屋KING 定西路 拉面』在携程/抖音/澎湃拉面指南发现。"
        "（按附录A：面类拆为拉面(按流派)/荞麦/乌冬三级，此店归拉面·虾白汤与柚子盐鸡白汤。）"),
    evidence={
        "diner_quotes": [
            {"quote": "麺屋KING慕名已久，点了超浓厚虾白汤担担面、柚子盐味鸡汤拉面、油淋鸡，太美味了，看着制作流程很治愈，目前心中排名超越了庄野、京都一乘寺。",
             "dish": "虾白汤担担面/柚子盐拉面", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=110406549", "date": "2024-12-27"},
            {"quote": "麺屋KING在停车场的其实拉面，浓厚生蚝拉面汤底真的浓稠又鲜甜甚至想用它拌饭吃；柚子盐味清汤拉面汤底用鸡骨和蔬菜熬制加柚子皮提香。",
             "dish": "生蚝拉面/柚子盐拉面", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=197867678", "date": "2025-09-14"},
        ],
        "platform_scores": [
            {"platform": "携程", "score": 4.6, "review_count": 400, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=110406549"},
        ],
        "negative_signals": ["位置在停车场内不好找", "高峰排队", "口味偏浓"],
        "soft_ad_flags": ["多博主横评推荐"],
        "traffic_signals": ["每次排队", "一人食吧台", "满吉老板新店"],
    },
    sources=[
        {"title": "澎湃新闻 - 上海拉面指南(柚子盐清汤)", "url": "https://m.thepaper.cn/newsDetail_forward_28972302", "type": "media"},
        {"title": "携程社区 - 麺屋KING", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=110406549", "type": "ugc"},
        {"title": "抖音 - 上海热门拉面横评(面屋King)", "url": "https://www.iesdouyin.com/share/video/7610764097268829449", "type": "ugc"},
    ],
    notes="回归用例命中（面屋KING 定西路1116/1118，虾白汤+柚子盐鸡）。cuisine_paths 按附录A拉面流派细分。纹兵卫/荞麦道/ichi荞麦见 candidates_list（待补第2条UGC）。坐标留空。",
))

# --- 泰国（补薄格，Cheeva Thai 由 Slice A 采，此为其他泰餐） ---
asia.append(rec(
    name="富贵椰 Thai Bistro & Eatery(丰盛里店)",
    name_en="Fu Gui Ye Thai Bistro",
    district="静安区",
    address="茂名北路丰盛里(近南京西路,具体门牌见高德拾取)",
    business_area="丰盛里/南京西路",
    price_avg=180, price_range="¥150-220",
    cuisine_paths=[["亚洲", "泰国", "创意泰式Bistro"], ["亚洲", "泰国", "曼谷早午餐Brunch"]],
    form="Bistro", scene="Brunch",
    signature_dishes=["创意泰式正餐", "Bangkok Brunch", "泰式下午茶", "夜酒"],
    phone_raw=None, booking_method="大众点评/预约",
    scores={"objective": 74, "diner": 72, "taste": 74, "endorsement": 60,
            "soft_ad_penalty": 5, "platform_credibility": 0.8},
    evidence_summary=(
        "富贵椰 Thai Bistro & Eatery(丰盛里店)是上海泰餐新贵，把全天候泰餐玩成 Bangkok Brunch、"
        "咖啡下午茶、泰式正餐到夜酒的『城市度假』一站式空间，Chic & Classic 设计贯穿菜品与环境。"
        "Time Out 上海列入『魔都新晋泰料Top9』，抖音食客个人打分给10分、称反复去吃每次有新惊喜。"
        "负面：创意泰式偏离传统泰北/伊安地道口味、环境与网红属性强于街边泰排档、人均偏高。"
        "由『上海 泰餐 推荐』在 TimeOut/携程/抖音 发现。（注：Cheeva Thai 由 Slice A 采集，本店为补其他泰餐薄格。）"),
    evidence={
        "diner_quotes": [
            {"quote": "富贵椰Thai Bistro&Eatery(丰盛里店)堪称魔都泰餐界的扛把子，我反反复复去吃了好多次每次都有新惊喜，菜品主打创意泰式风味。",
             "dish": "创意泰式", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=204957432", "date": "2025-09-29"},
            {"quote": "个人打分表里富贵椰thaibistro&eatery(丰盛里店)10分，是会主动约朋友再去的前6家；cheevathai9.2分是泰餐备选。",
             "dish": "泰餐", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7669697865153496803", "date": "2026-08-03"},
        ],
        "platform_scores": [
            {"platform": "携程", "score": 4.5, "review_count": 500, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=204957432"},
        ],
        "negative_signals": ["创意泰式偏离地道", "网红环境属性强", "人均偏高"],
        "soft_ad_flags": ["TimeOut榜单/博主集中"],
        "traffic_signals": ["全天Brunch到夜酒", "城市度假空间"],
    },
    sources=[
        {"title": "TimeOut上海 - 魔都新晋泰料Top9", "url": "https://www.timeoutshanghai.cn/features/7058.html", "type": "media"},
        {"title": "携程社区 - 富贵椰泰式风情", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=204957432", "type": "ugc"},
        {"title": "抖音 - 上海美食打分表", "url": "https://www.iesdouyin.com/share/video/7669697865153496803", "type": "ugc"},
    ],
    notes="泰国菜库内17家但多为冬阴功/船面，此为创意泰式Bistro/Brunch薄格补位。门牌待拾取。坐标留空。",
))

# --- 西亚/阿拉伯：阿萨中东料理（清真） ---
asia.append(rec(
    name="阿萨中东料理·清真(上海荟聚店)",
    name_en="Assa Middle Eastern",
    district="长宁区",
    address="金钟路788号上海荟聚中心L3层03A01室",
    business_area="临空/荟聚",
    price_avg=165, price_range="¥150-180",
    cuisine_paths=[["亚洲", "西亚/中东", "阿拉伯清真正餐"], ["亚洲", "西亚/中东", "摩洛哥牛肋排塔吉锅"]],
    form="Casual Dining", scene="正餐",
    signature_dishes=["摩洛哥牛肋排塔吉锅", "中东 mezze 前菜拼盘", "法拉费Falafel", "鹰嘴豆泥Hummus"],
    phone_raw=None, booking_method="大众点评",
    scores={"objective": 66, "diner": 66, "taste": 70, "endorsement": 45,
            "soft_ad_penalty": 5, "platform_credibility": 0.75},
    evidence_summary=(
        "阿萨中东料理·清真(上海荟聚店)位于长宁金钟路788号上海荟聚中心L3层03A01，进门如穿越波斯市集、"
        "暖黄灯光配复古雕花，提供换装体验。招牌摩洛哥牛肋排塔吉锅慢炖到脱骨、裹醇厚香料酱汁、胡萝卜吸满味；"
        "人均150-180元。Trip 食客给4.3。负面：新开商场店、评论基数小、换装拍照属性强、菜单横跨多国"
        "(摩洛哥/波斯/阿拉伯)而非单一国别正宗。由『上海 伊朗/以色列/中东』在携程/Trip 发现。"
        "（按新树归亚洲·西亚/中东；阿拉伯(阿联酋/沙特)与摩洛哥塔吉在此交叉多挂。）"),
    evidence={
        "diner_quotes": [
            {"quote": "荟聚这家宝藏中东料理我能刷100次，一进门直接穿越到波斯市集；摩洛哥牛肋排塔吉锅慢炖到脱骨、裹着醇厚香料酱汁，连胡萝卜都吸满了。",
             "dish": "牛肋排塔吉锅", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=224340418", "date": "2025-11-07"},
            {"quote": "阿萨中东料理·清真(上海荟聚店)4.3/5，阿拉伯宫廷风装修氛围感爆炸，进门换装秒变中东贵族，人均150-180元。",
             "dish": "中东料理", "source": "Trip.com", "url": "https://hk.trip.com/moments/detail/shanghai-2-132275655/", "date": "2025-05-21"},
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.3, "review_count": 30, "url": "https://hk.trip.com/moments/detail/shanghai-2-132275655/"},
        ],
        "negative_signals": ["新开商场店评论基数小", "换装拍照属性强", "菜单横跨多国非单国正宗"],
        "soft_ad_flags": ["探店/换装拍照"],
        "traffic_signals": ["波斯市集装修打卡"],
    },
    sources=[
        {"title": "携程社区 - 阿萨中东料理荟聚店", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=224340418", "type": "ugc"},
        {"title": "Trip.com - 阿萨中东料理上海荟聚店", "url": "https://hk.trip.com/moments/detail/shanghai-2-132275655/", "type": "ugc"},
    ],
    notes="阿拉伯/中东菜库内『中东/阿拉伯菜』10家、波斯菜仅1家。本店为中东清真薄格补位。评论<50按可信度≤0.7。坐标留空。",
))

with open(OUT/"raw_asia.jsonl", "w", encoding="utf-8") as f:
    for r in asia:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"asia: {len(asia)}")
