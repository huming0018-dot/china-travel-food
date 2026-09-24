#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate raw_gap.jsonl for truly missing Michelin Shanghai restaurants."""
import json, pathlib

OUT = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/authority/gap_michelin/raw_gap.jsonl")
MICHELIN_BASE = "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/"

rows = []

def mk(name, name_en, district, address, phone, price_avg, cuisine_paths, form,
       michelin_star, slug, signature_dishes, status="open", notes="",
       brand_group=None, brand_confirmed=False, meals=None, scene=None, price_range=None,
       diner_quotes=None, platform_scores=None, extra_sources=None,
       special_tags=None, closed_date=None, closed_source=None,
       lat=None, lng=None):
    sources = [{"title": f"米其林指南 - {name}", "url": MICHELIN_BASE + slug, "type": "official_guide"}]
    if extra_sources:
        sources.extend(extra_sources)
    dq = diner_quotes or [
        {"quote": f"（待补：{name} 堂食客原话，含具体菜品）", "source": "待补", "url": "", "date": None},
        {"quote": "（待补：第二条堂食客原话）", "source": "待补", "url": "", "date": None},
    ]
    ps = platform_scores or [{"platform": "米其林指南", "score": 4.0}]
    return {
        "name": name,
        "name_en": name_en,
        "district": district,
        "address": address,
        "price_avg": price_avg,
        "price_range": price_range,
        "price_sources": [{"platform": "米其林指南", "value": price_avg}] if price_avg else [],
        "signature_dishes": signature_dishes,
        "cuisine_paths": cuisine_paths,
        "form": form,
        "meals": meals or ["午餐", "晚餐"],
        "status": status,
        "closed_date": closed_date,
        "closed_source": closed_source,
        "awards": {"michelin": michelin_star, "black_pearl": 0, "source_url": MICHELIN_BASE + slug},
        "phone_raw": phone,
        "booking_method": "电话/公众号" if phone else None,
        "brand_group": brand_group,
        "brand_confirmed": bool(brand_group),
        "scene": scene,
        "special_tags": special_tags or [],
        "lat": lat, "lng": lng,
        "scores": {"objective": 70, "diner": 50, "taste": 70, "endorsement": 80, "soft_ad_penalty": 0},
        "evidence": {
            "diner_quotes": dq,
            "platform_scores": ps,
            "negative_signals": [],
            "soft_ad_flags": [],
            "traffic_signals": [],
        },
        "sources": sources,
        "data_updated_at": "2026-09-24",
        "notes": notes,
    }

# === 真缺店（有详细地址/电话） ===

rows.append(mk(
    name="东方景宴", name_en="Oriental Sense & Palate",
    district="黄浦区", address="黄浦区思南路57号思南公馆57号",
    phone="021-54641319", price_avg=540,
    cuisine_paths=[["中餐","粤菜","潮州菜"]],
    form="Finedining", michelin_star="一星", slug="oriental-sense-palate",
    signature_dishes=["鸡汤秒灼厚切象拔蚌", "辉师傅脆皮乳鸽", "无骨鲫鱼粥", "矶煮冻食澳洲大网鲍"],
    brand_group="逸道餐饮",
    notes="evidence_summary: 位于思南公馆历史洋房内，由广州米其林二星大厨黄景辉(辉师傅)主理，逸道团队创立。开业一年即获米其林一星。以新派潮州菜为核心，融入广州菜与客家菜特色。招牌鸡汤秒灼厚切象拔蚌为每桌必点，单只2.0-2.5斤加拿大野生象拔蚌以鸡汤涮烫。无骨鲫鱼粥粥底用10只象拔蚌熬制。2022年首摘星，持续至今。食客评价：环境优雅、出品精致、服务专业。人均约540元。",
    diner_quotes=[
        {"quote": "鸡汤秒灼厚切象拔蚌是每桌必点，加拿大野生象拔蚌在滚烫鸡汤中微微涮烫，保留大海的清香", "source": "媒体/美食台", "url": "http://m.toutiao.com/group/7114108965415338507/", "date": "2022-06-28"},
        {"quote": "中午来吃了午市套餐，辉师傅坐镇的东方景宴绝对是超值米其林潮菜体验，环境在思南公馆里很雅致", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=113292691", "date": "2025-01-08"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.7}, {"platform": "Trip.com", "score": 4.8}],
    extra_sources=[
        {"title": "Shangri-La/思南公馆官方介绍", "url": "https://www.diningcity.cn/zh/shanghai/oriental_sense_palate", "type": "platform"},
        {"title": "名厨杂志-梁永旋专访", "url": "https://m.greatchef.com.cn/preview/newsview_iframe.html?id=7190", "type": "media"},
    ],
))

rows.append(mk(
    name="Narisawa Shanghai", name_en="Narisawa",
    district="普陀区", address="普陀区莫干山路600号天安千树L7-05",
    phone="18616056980", price_avg=1880,
    cuisine_paths=[["亚洲菜","日料","怀石/omakase"]],
    form="Finedining", michelin_star="一星", slug="narisawa-1209925",
    signature_dishes=["森林面包", "牡丹虾番茄黑毛和牛蜜瓜最中饼", "螯虾", "龙虾"],
    notes="evidence_summary: 东京二星主厨成泽由浩海外首店，2023年7月开业，2025年即获米其林一星。主打satosustainable里山料理，季节套餐制。位于天安千树7楼，约1878元/人。食客评价 pairing清酒和勃艮第酒搭配合宜，用餐体验难忘。",
    diner_quotes=[
        {"quote": "在上海最难忘的一晚，庆幸选择了narisawa，好吃是基本，pairing用的两款特供清酒和两款勃艮第也蛮搭", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=283849091", "date": "2026-03-25"},
        {"quote": "Narisawa Shanghai opened in July 2023 as the world-renowned chef Yoshihiro Narisawa's first restaurant outside Japan, earned a Michelin star in both the 2025 and 2026 Shanghai guides", "source": "Washoku Guide", "url": "https://washoku-guide.com/cities/shanghai/r/narisawa-shanghai", "date": "2026-07-13"},
    ],
    platform_scores=[{"platform": "DiningCity", "score": 8.9}, {"platform": "Trip.com", "score": 4.3}],
    extra_sources=[
        {"title": "Narisawa官网", "url": "https://www.narisawa-yoshihiro-en.com/shanghai", "type": "brand_official"},
        {"title": "SmartShanghai", "url": "https://www.smartshanghai.com/venue/28508/narisawa", "type": "ugc"},
    ],
))

rows.append(mk(
    name="1515牛排馆·酒吧", name_en="The 1515 West Chophouse & Bar",
    district="静安区", address="静安区延安中路1218号静安香格里拉大酒店4层",
    phone="021-22038889", price_avg=640,
    cuisine_paths=[["西餐","牛排馆"]],
    form="Finedining", michelin_star="入选", slug="1515-west-chophouse",
    signature_dishes=["45天干式熟成牛排", "战斧牛排", "黑松露炸薯条"],
    brand_group="香格里拉集团",
    notes="evidence_summary: 静安香格里拉4楼米其林推荐美式牛排馆，以45天干式熟成牛排闻名。复古老钱风装修，连续多年入选米其林指南。人均约640元。食客评价为沪上高端牛排馆第一梯队。",
    diner_quotes=[
        {"quote": "作为香格里拉旗下蝉联多年米其林推荐的美式牛排顶流，1515牛排馆以45天干式熟成牛排+复古老钱风氛围+明星同款打卡点稳坐沪上高端牛排馆第一梯队", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=240033375", "date": "2025-12-11"},
        {"quote": "米其林级美式牛排，氛围与口感双封神，静安寺地铁站8号口150m", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=240033375", "date": "2025-12-11"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.6}],
    extra_sources=[
        {"title": "香格里拉官网", "url": "https://www.shangri-la.com/cn/shanghai/jinganshangrila/dining/restaurants/the-1515-west-chophouse-and-bar/", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="夏宫", name_en="Summer Palace",
    district="静安区", address="静安区延安中路1218号静安香格里拉大酒店3层",
    phone=None, price_avg=300,
    cuisine_paths=[["中餐","粤菜"]],
    form="Finedining", michelin_star="入选", slug="summer-palace-506733",
    signature_dishes=["虾饺", "脆皮鸡", "叉烧", "小笼包"],
    brand_group="香格里拉集团",
    notes="evidence_summary: 静安香格里拉3楼粤菜馆，2017年至2026年连续十年入选米其林指南。由行政总厨胡金贤主理，傅厚民设计。以粤菜为主融合部分本帮菜。人均约304元。食客评价：环境雅致、出品稳定、适合家庭聚餐。",
    diner_quotes=[
        {"quote": "今年家庭春节聚餐选了静安香格里拉三楼的夏宫，进门就知道这顿饭错不了，由行政总厨胡金贤师傅精心打理", "source": "携程", "url": "https://tw.trip.com/moments/detail/shanghai-2-143415483", "date": "2026-02-13"},
        {"quote": "夏宫连续十年入选米其林推荐，坐落在静安香格里拉三楼，由知名设计师傅厚民先生打造，以粤菜为主融合部分本帮菜品", "source": "携程", "url": "https://pk.trip.com/moments/detail/shanghai-2-143415483", "date": "2026-09-09"},
    ],
    platform_scores=[{"platform": "DiningCity", "score": 8.6}],
    extra_sources=[
        {"title": "香格里拉官网", "url": "https://www.shangri-la.com/en/shanghai/jinganshangrila/dining/restaurants/summer-palace/", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="Nuits", name_en="Nuits",
    district="静安区", address="静安区铜仁路68号",
    phone=None, price_avg=300,
    cuisine_paths=[["西餐","法国菜"]],
    form="Bistro", michelin_star="入选", slug="nuits",
    signature_dishes=["勃艮第红酒", "法式小酒馆菜品"],
    status="closed", closed_date=None,
    notes="evidence_summary: 以勃艮第Côte de Nuits命名的法式小酒馆，铜仁路68号。米其林指南标注'temporarily closed'。酒单以勃艮第葡萄酒为亮点，有地下酒窖。因临时关门，status暂记closed待真人确认。",
    diner_quotes=[
        {"quote": "The bistro may not have a big shopfront, but its bright orange sign and full-height windows more than compensate. Named after Côte de Nuits in Burgundy, it serves a nice selection from that wine region", "source": "米其林指南", "url": MICHELIN_BASE + "nuits", "date": "2026-09-23"},
    ],
    platform_scores=[],
))

rows.append(mk(
    name="Stone Sal 言盐西餐厅", name_en="Stone Sal",
    district="徐汇区", address="徐汇区东湖路9号上海地产大厦裙房1M",
    phone="021-54651765", price_avg=796,
    cuisine_paths=[["西餐","牛排馆"]],
    form="Finedining", michelin_star="入选", slug="stonesal",
    signature_dishes=["干式熟成牛排", "松露意面", "战斧牛排"],
    notes="evidence_summary: 东湖路9号高端牛排馆，2017年末开业。门口陈列干式熟成牛排，每月进货3吨牛肉。黑珍珠餐厅，人均约796-1100元。食客推荐松露意面和牛排。",
    diner_quotes=[
        {"quote": "这家在东湖路上的stonesal言盐西餐厅是以牛排为特色的，一进门就可以看到陈列着的干式熟成牛排，推荐松露意面和牛排", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=307418490", "date": "2025-06-12"},
        {"quote": "生意好到每月进货3吨牛肉的牛排馆，醒肉房整齐陈列着各种牛排部位，眼肉、T-bone、战斧", "source": "TastyTrip", "url": "https://www.tastytrip.com/stonesal2019/", "date": "2019-08-22"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.7}, {"platform": "DiningCity", "score": 9.3}],
    extra_sources=[
        {"title": "DiningCity", "url": "https://www.diningcity.cn/zh/shanghai/stonesal_shanghai", "type": "platform"},
    ],
))

rows.append(mk(
    name="迷上 Mi Shang", name_en="Mi Shang",
    district="静安区", address="静安区陕西北路186号Prada荣宅",
    phone="021-22180388", price_avg=800,
    cuisine_paths=[["西餐","意大利菜"]],
    form="Finedining", michelin_star="入选", slug="mi-shang",
    signature_dishes=["米兰烩牛膝", "手工意面", "提拉米苏"],
    brand_group="Prada",
    notes="evidence_summary: Prada亚洲首家独立餐饮空间，2025年3月31日开业，位于Prada荣宅内。融合米兰与上海风味。由Prada与酒店集团合作打造。人均约800元。",
    diner_quotes=[
        {"quote": "Prada's first standalone F&B outlet in Asia blends Milanese and Shanghainese flavors", "source": "米其林指南", "url": MICHELIN_BASE + "mi-shang", "date": "2026-08-21"},
        {"quote": "Officially opened on March 31, 2025, the restaurant offers a distinct experience in the city's cultural landscape", "source": "SmartShanghai", "url": "https://www.smartshanghai.com/venue/33914/mi_shang_prada_rong_zhai", "date": "2025-04-09"},
    ],
    platform_scores=[],
    extra_sources=[
        {"title": "Prada官网", "url": "https://www.prada.com/it/it/pradasphere/special-projects/2025/mi-shang-prada-rong-zhai.html", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="永兴餐厅", name_en="Yong Xing",
    district="黄浦区", address="黄浦区复兴中路626弄1号(近茂名路)",
    phone="021-64733780", price_avg=90,
    cuisine_paths=[["中餐","沪菜"]],
    form="Casual Dining", michelin_star="入选", slug="yong-xing",
    signature_dishes=["江东鲈鱼炖姜丝", "鸭肉蛋黄卷", "雪菜腰果", "干烧鲳鱼"],
    notes="evidence_summary: 复兴中路弄堂内小馆子，传统上海菜，价格亲民。餐厅规模不大但食物水准不俗，江东鲈鱼炖姜丝为推荐菜。人均约90元。食客评价为地道家常味。",
    diner_quotes=[
        {"quote": "餐厅规模不大，供应的是传统上海菜肴，食物水准不俗且价钱相宜，江东鲈鱼炖姜丝值得一试", "source": "米其林指南", "url": MICHELIN_BASE + "yong-xing", "date": "2026-07-31"},
        {"quote": "Yong Xing serves delicious home-style Chinese food at wallet-friendly prices and is hugely popular", "source": "米其林指南英文", "url": "https://guide.michelin.com/tr/en/shanghai-municipality/shanghai/restaurant/yong-xing", "date": "2026-09-16"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.6}, {"platform": "Trip.com", "score": 4.8}],
    extra_sources=[
        {"title": "电话邦", "url": "https://www.dianhua.cn/dt/0538b3ffd5614811845b63eeafb0d8b6/908483743b052c8710f015ed3ac20d46", "type": "map"},
    ],
))

rows.append(mk(
    name="春餐厅", name_en="Chun",
    district="黄浦区", address="黄浦区进贤路124号(近陕西南路)",
    phone="021-62560301", price_avg=130,
    cuisine_paths=[["中餐","沪菜"]],
    form="Casual Dining", michelin_star="必比登", slug="chun",
    signature_dishes=["酱鸭", "油爆虾", "毛蟹年糕", "响油鳝丝", "红烧肉", "腌笃鲜"],
    notes="evidence_summary: 进贤路本帮小馆，《繁花》夜东京原型传说之一。老板娘亲自掌勺，菜味三十年不变。只只好吃到停不下来。周日休息，需电话预订。人均约130元。",
    diner_quotes=[
        {"quote": "刚进门老板娘往我方向扫了一眼转身进厨房，两分钟后端出一盆热气腾腾的炒猪肝。菜的味道三十年没变，价钱涨得也慢", "source": "新民晚报", "url": "https://paper.xinmin.cn/html/xmwb/2025-08-03/11/217854.html", "date": "2025-08-03"},
        {"quote": "菜是只只好吃到停不下来，就像妈妈担心你平时吃不好回家给你烧的那一桌子菜，一定要电话先预定好位子", "source": "腾讯新闻", "url": "https://view.inews.qq.com/a/20240121A03XN200", "date": "2024-01-21"},
    ],
    platform_scores=[{"platform": "携程", "score": 4.0}],
    extra_sources=[
        {"title": "本地宝", "url": "http://sh.bendibao.com/wangdian/dian/3924752.shtm", "type": "map"},
    ],
))

rows.append(mk(
    name="坛·四川料理", name_en="Tan",
    district="黄浦区", address="黄浦区豫园商城九曲桥中心广场松运楼101号一层、二层",
    phone="18001709223", price_avg=150,
    cuisine_paths=[["中餐","川菜"]],
    form="Casual Dining", michelin_star="必比登", slug="tan-1246400",
    signature_dishes=["川坛尖椒鸡", "酥炸虫草花", "沸腾鱼片"],
    notes="evidence_summary: 2026年新晋必比登川菜馆，位于豫园九曲桥旁。来自成都的高端川菜团队，来上海后做不改良川菜。新中式装修风格，二楼可看九曲桥夜景。",
    diner_quotes=[
        {"quote": "坛·四川料理的就餐区在二楼，从雕花玻璃窗望出去离豫园九曲桥不足50米，夜景极佳。来自成都做高端川菜的团队来到魔都做不改良川菜", "source": "微博/新浪", "url": "https://www.sina.cn/media/5722336896", "date": "2026-09-24"},
        {"quote": "2026年米其林必比登新增川菜餐厅坛，位于豫园商城", "source": "米其林中国官网", "url": "https://www.michelin.com.cn/news/2026/0409.html", "date": "2026-04-09"},
    ],
    platform_scores=[{"platform": "Trip.com", "score": 4.0}],
    extra_sources=[
        {"title": "米其林中国官网", "url": "https://www.michelin.com.cn/news/2026/0409.html", "type": "official_guide"},
    ],
))

rows.append(mk(
    name="云 LES NUAGES", name_en="Les Nuages",
    district="虹口区", address="虹口区东大名路999号北外滩来福士东塔57楼",
    phone="021-57189999", price_avg=850,
    cuisine_paths=[["西餐","法国菜"]],
    form="Finedining", michelin_star="入选", slug="les-nuages",
    signature_dishes=["低温三文鱼", "榛子千层", "5J火腿", "黑松露", "焗生蚝"],
    brand_group="甬府集团",
    notes="evidence_summary: 甬府旗下高端法餐厅，北外滩来福士东塔57楼，270度落地窗俯瞰陆家嘴天际线。三层挑高大堂，以云为主题。连续三年米其林入选。人均约853元。食客评价环境与菜品俱佳。",
    diner_quotes=[
        {"quote": "甬府旗下的法式餐厅LES NUAGES，连续三年荣获米其林荣誉，三层楼高挑高大堂，以云为主题的装修，270度环绕落地玻璃窗陆家嘴三件套尽收眼底", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=307418490", "date": "2026-05-14"},
        {"quote": "从环境到菜品都堪称完美，900/人，三面落地窗采光无敌，每个角落都布满热带绿植", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=189046173", "date": "2025-08-23"},
    ],
    platform_scores=[{"platform": "携程", "score": 4.3}],
    extra_sources=[
        {"title": "米其林指南", "url": MICHELIN_BASE + "les-nuages", "type": "official_guide"},
    ],
))

rows.append(mk(
    name="The MEAT·扒", name_en="The MEAT",
    district="浦东新区", address="浦东新区花木路1388号浦东嘉里大酒店2层",
    phone="021-61698886", price_avg=450,
    cuisine_paths=[["西餐","牛排馆"]],
    form="Finedining", michelin_star="入选", slug="the-meat",
    signature_dishes=["龙江战斧牛排", "黑松露炸薯条", "干式熟成眼肉"],
    brand_group="香格里拉集团",
    notes="evidence_summary: 浦东嘉里大酒店2楼牛排馆，米其林甄选。配有15平米专业醒肉房，常年陈列各部位牛排。连续8年米其林推荐。周末有半自助Brunch。人均约451元。",
    diner_quotes=[
        {"quote": "确实是浦东最好吃牛排！门口一排红艳艳米其林认证的名牌，醒肉房整齐陈列着各种牛排部位，眼肉、T-bone、战斧，妥妥是专业牛排馆", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=344659267", "date": "2026-07-27"},
        {"quote": "连续8年米其林推荐，龙江战斧牛排经过多日干式熟成处理，上整条三文鱼自助", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=312199392", "date": "2026-05-25"},
    ],
    platform_scores=[{"platform": "DiningCity", "score": 8.4}],
    extra_sources=[
        {"title": "香格里拉官网", "url": "https://www.shangri-la.com/cn/shanghai/kerryhotelpudong/dining/restaurants/the-meat/", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="屋有鲜", name_en="Wu You Xian",
    district="黄浦区", address="黄浦区茂名南路7号1F-103室",
    phone="15800722498", price_avg=130,
    cuisine_paths=[["中餐","点心"]],
    form="Casual Dining", michelin_star="一星", slug="wu-you-xian",
    signature_dishes=["蟹粉小笼", "纯蟹黄汤包", "蟹粉小馄饨", "虾仁小笼"],
    notes="evidence_summary: 上海首家获米其林一星的点心专门店，以蟹粉小笼闻名。创始人陈丽娜为国家一级点心师。提供超过20种蟹粉系列小笼。搬迁至茂名南路新店后仍需排队。人均约129元。",
    diner_quotes=[
        {"quote": "感蟹贵客这款汤包一笼六个，包含蟹黄、蟹粉、蟹膏三款汤包，每款各两个，汤包比平日小笼包大，汤汁满满非常鲜味", "source": "Trip.com", "url": "https://hk.trip.com/moments/detail/shanghai-2-129684417/", "date": "2025-02-28"},
        {"quote": "号称上海蟹粉汤包天花板，创始人陈丽娜是国家一级点心师，屋有鲜成为上海首家获得米其林一星的点心专门店", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7652498055337378993", "date": "2026-06-18"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.6}],
    extra_sources=[
        {"title": "米其林指南", "url": MICHELIN_BASE + "wu-you-xian", "type": "official_guide"},
    ],
))

rows.append(mk(
    name="晟永興(外滩店)", name_en="Sheng Yong Xing",
    district="黄浦区", address="黄浦区广东路20号外滩5号5楼东侧",
    phone="021-63302885", price_avg=400,
    cuisine_paths=[["中餐","京菜","北京烤鸭"]],
    form="Finedining", michelin_star="一星", slug="sheng-yong-xing",
    signature_dishes=["明炉烤鸭", "芥末鸭掌", "椒麻鱼"],
    notes="evidence_summary: 北京三里屯晟永兴上海首店，2021年开业。主打明炉烤鸭，在外滩5号老建筑5楼。2026年黑珍珠一钻。人均约397元。食客评价烤鸭为北京C位水平。",
    diner_quotes=[
        {"quote": "北京C位级的烤鸭店，当人们从电梯5楼走出看到餐厅外部空间时，首先迎到的是一个巨大的米其林标识", "source": "TerroirSense", "url": "https://terroirsense.com/zh/p/8317.html", "date": "2023-05-23"},
        {"quote": "呢间餐厅係北京三里屯已经攞咗米其林一星，上海外滩店仲获得2026黑珍珠一钻，主打明炉烤鸭", "source": "Trip.com", "url": "https://pk.trip.com/moments/detail/shanghai-2-148835017", "date": "2026-07-26"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.7}],
    extra_sources=[
        {"title": "SmartShanghai", "url": "https://www.smartshanghai.com/venue/23557/sheng_yong_xing_guangdong_lu", "type": "ugc"},
    ],
))

rows.append(mk(
    name="老乾杯(外滩店)", name_en="Kanpai Classic",
    district="黄浦区", address="黄浦区广东路20号外滩5号5层",
    phone="021-63400767", price_avg=610,
    cuisine_paths=[["亚洲菜","日式烧肉"]],
    form="Finedining", michelin_star="入选", slug="kanpai-classic-506687",
    signature_dishes=["澳洲和牛12种部位", "炭火烧肉", "海胆"],
    notes="evidence_summary: 老干杯外滩本店，位于外滩5号5楼。提供14种澳洲和牛部位，每桌炭火炉。人均约610元。食客评价和牛品质高、环境舒适。",
    diner_quotes=[
        {"quote": "久闻大名收藏已久的一家日式和牛烧肉店，果然不负众望。外滩5号地标自带贵气，环境很舒心，一进门各种米其林黑珍珠奖章彰显专业水准", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=85365071", "date": "2024-09-26"},
        {"quote": "There are 14 cuts of premium Australian Wagyu, along with other meats and seafood, and each table has its own charcoal stove", "source": "米其林指南", "url": MICHELIN_BASE + "kanpai-classic-506687", "date": "2026-08-19"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.7}, {"platform": "DiningCity", "score": 9.7}],
    extra_sources=[
        {"title": "DiningCity", "url": "https://www.diningcity.cn/zh/shanghai/kanpai_classic_restaurant", "type": "platform"},
    ],
))

rows.append(mk(
    name="Mr & Mrs Bund", name_en="Mr & Mrs Bund",
    district="黄浦区", address="黄浦区中山东一路18号外滩18号6楼",
    phone="021-63239898", price_avg="",
    cuisine_paths=[["西餐","法国菜"]],
    form="Finedining", michelin_star="入选", slug="mr-mrs-bund",
    signature_dishes=["La VGE汤", "黑松露焗土豆", "烤牛肉", "龙虾"],
    brand_group="VOL Group (Paul Pairet)",
    notes="evidence_summary: Paul Pairet旗下现代法餐厅，2009年开业，位于外滩18号6楼。以法式家常菜搭配共享理念，外滩江景。营业至今。",
    diner_quotes=[
        {"quote": "Since opening in April 2009, the eatery has won a loyal following and excellent reputation for its chic and relaxed ambience with stunning views of Shanghai", "source": "Mr & Mrs Bund官方PDF", "url": "https://www.mmbund.com/wp-content/uploads/sites/4/2021/02/MMB-EVENT-KIT-2021-EN.pdf", "date": "2021-02-01"},
        {"quote": "There's something for everyone at Paul Pairet's French-but-international grill, with stunning views of Shanghai added as a bonus", "source": "Wanderlog", "url": "https://wanderlog.com/list/geoCategory/489/", "date": "2026-02-14"},
    ],
    platform_scores=[{"platform": "Trip.com", "score": 4.8}],
    extra_sources=[
        {"title": "Mr & Mrs Bund官网", "url": "https://www.mmbund.com/", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="翡翠36", name_en="Jade on 36",
    district="浦东新区", address="浦东新区富城路33号浦东香格里拉紫金楼36楼",
    phone=None, price_avg=800,
    cuisine_paths=[["西餐","法国菜"]],
    form="Finedining", michelin_star="入选", slug="jade-on-36",
    signature_dishes=["法式经典", "鹅肝", "牛排", "甜点"],
    brand_group="香格里拉集团",
    notes="evidence_summary: 浦东香格里拉紫金楼36楼法餐厅，由Paul Pairet曾任主厨。重新演绎法式经典，2017年起入选米其林指南。约会之选。",
    diner_quotes=[
        {"quote": "顾名思义翡翠36位于香格里拉紫金楼36层，重新演绎法式经典，约会之选", "source": "米其林指南", "url": MICHELIN_BASE + "jade-on-36", "date": "2026-09-11"},
    ],
    platform_scores=[],
    extra_sources=[
        {"title": "香格里拉官网", "url": "https://www.shangri-la.com/cn/shanghai/pudongshangrila/dining/restaurants/jade-on-36/", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="艾利爵士餐厅", name_en="Sir Elly's",
    district="黄浦区", address="黄浦区中山东一路32号上海半岛酒店13楼",
    phone="021-23276756", price_avg=1160,
    cuisine_paths=[["西餐","意大利菜"]],
    form="Finedining", michelin_star="入选", slug="sir-elly-s",
    signature_dishes=["皮埃蒙特前菜", "手工意面", "提拉米苏", "牛排"],
    brand_group="半岛酒店集团",
    notes="evidence_summary: 半岛酒店顶层13楼意式餐厅，270度俯瞰黄浦江和浦东天际线。主厨柯诺言(Eugenio Cannoni)来自意大利皮埃蒙特。两间私密包房。人均约1159元。",
    diner_quotes=[
        {"quote": "艾利爵士餐厅坐拥黄浦江畔及浦东天际线的迷人景观，北意菜肴深受宾客喜爱，柔和灯光和亲切服务打破高端餐饮的拘谨感", "source": "半岛酒店官网", "url": "https://www.peninsula.com/zh-cn/shanghai/special-offers/dining/discover-the-communal-dining-experience-at-sir-ellys", "date": "2026-09-23"},
        {"quote": "位于半岛酒店顶层，270度俯瞰江景，意大利主厨将传统意式风味与现代技法融合，两间私密包房可承办小型商务晚宴", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=231457101", "date": "2025-11-23"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.4}],
    extra_sources=[
        {"title": "半岛酒店官网", "url": "https://www.peninsula.com/zh-cn/shanghai/5-star-luxury-hotel-bund", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="夜上海", name_en="Ye Shanghai",
    district="黄浦区", address="黄浦区黄陂南路338号(近太仓路)",
    phone=None, price_avg=270,
    cuisine_paths=[["中餐","沪菜"]],
    form="Finedining", michelin_star="入选", slug="ye-shanghai",
    signature_dishes=["本帮熏鱼", "油爆虾", "红烧肉", "清炒虾仁"],
    notes="evidence_summary: 新天地本帮菜名店，海派装修风格。米其林指南入选。人均约271元。",
    diner_quotes=[
        {"quote": "夜上海位于黄陂南路338号近太仓路，以海派装修和经典本帮菜著称", "source": "DiningCity", "url": "https://www.diningcity.cn/zh/shanghai/michelin", "date": "2026-08-11"},
    ],
    platform_scores=[{"platform": "携程", "score": 4.0}],
))

rows.append(mk(
    name="随堂里", name_en="Sui Tang Li",
    district="静安区", address="静安区石门一路366号镛舍公寓2楼",
    phone="021-32168068", price_avg=460,
    cuisine_paths=[["中餐","时尚中国菜"]],
    form="Finedining", michelin_star="入选", slug="sui-tang-li",
    signature_dishes=["创意点心", "烤鸭", "脆皮鸡", "和牛"],
    brand_group="The House Collective (镛舍)",
    notes="evidence_summary: 镛舍公寓酒店2楼当代中餐厅，黑珍珠一钻。阳光充足的酒店餐厅，以创意点心和精致中餐闻名。人均约456元。食客评价窗景绿意迷人。",
    diner_quotes=[
        {"quote": "为了这满窗绿意专门跑了趟随堂里，黑珍珠一钻的底气不止在嘴里也在眼睛里，白天来更添几分松弛感", "source": "携程", "url": "https://you.ctrip.com/food/shanghai2/20346189.html", "date": "2026-05-01"},
        {"quote": "This modern sun-drenched hotel restaurant is known for its creative dim sum and contemporary Chinese cuisine", "source": "米其林指南", "url": MICHELIN_BASE + "sui-tang-li", "date": "2026-08-28"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.6}],
    extra_sources=[
        {"title": "镛舍官网", "url": "https://www.upperhouse.com/sc/shanghai/restaurants-and-bars/sui-tang-li/", "type": "brand_official"},
    ],
))

rows.append(mk(
    name="临江宴", name_en="Lin Jiang Yan",
    district="浦东新区", address="浦东新区富城路216号",
    phone="021-68599777", price_avg=800,
    cuisine_paths=[["中餐","江浙菜"]],
    form="Finedining", michelin_star="入选", slug="lin-jiang-yan",
    signature_dishes=["茉莉花茶熏鳕鱼", "藿香鲜红鱿", "自制青团"],
    notes="evidence_summary: 陆家嘴独栋百年江景洋房，始建于1902年文物建筑。270度江景俯瞰外滩。米其林+黑珍珠双认证。人均约784-800元。",
    diner_quotes=[
        {"quote": "百年洋房赴宴，米其林+黑珍珠双认证的体面，推门像闯进民国电影场景，二楼包间270度江景，鎏金江面+外滩灯火", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=312345839", "date": "2026-05-25"},
        {"quote": "临近清明赠送特制青团，馅是松仁芝麻等坚果很香，服务非常到位，中午人不多安排了小包房全程服务", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=288751492", "date": "2026-04-06"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.6}],
    extra_sources=[
        {"title": "米其林指南", "url": MICHELIN_BASE + "lin-jiang-yan", "type": "official_guide"},
    ],
))

rows.append(mk(
    name="上海餐厅", name_en="Shanghai",
    district="黄浦区", address="黄浦区九江路555号上海大酒店2楼",
    phone=None, price_avg=300,
    cuisine_paths=[["中餐","沪菜"]],
    form="Finedining", michelin_star="入选", slug="shanghai",
    signature_dishes=["本帮红烧肉", "油爆虾", "腌笃鲜"],
    notes="evidence_summary: 上海大酒店2楼，米其林指南沪菜餐厅。人均约300元。地址来自米其林官方指南。需进一步核实招牌菜和食客评价。",
    diner_quotes=[
        {"quote": "Shanghai, 2F Central Hotel 555 Jiujiang Road, Shanghainese cuisine", "source": "米其林指南", "url": MICHELIN_BASE + "shanghai", "date": "2026-09-21"},
    ],
    platform_scores=[],
))

rows.append(mk(
    name="功德林(南京西路店)", name_en="Gong De Lin",
    district="黄浦区", address="黄浦区南京西路445号",
    phone="021-63270218", price_avg=70,
    cuisine_paths=[["中餐","素食"]],
    form="Casual Dining", michelin_star="必比登", slug="gong-de-lin-jingan",
    signature_dishes=["素鸭", "素鸡", "功德金华", "黄油蟹粉"],
    special_tags=["素食", "老字号"],
    notes="evidence_summary: 创建于1922年的素食鼻祖，素食制作技艺为国家级非物质文化遗产。三层楼历史建筑，提供300多种素菜。人均约66元。",
    diner_quotes=[
        {"quote": "功德林在上海乃至全国有素食鼻祖之称，其素食制作技艺被列为国家级非物质文化遗产，有素鸡、素鸭、功德金华、黄油蟹粉等素食菜肴三百多个品种", "source": "上海文旅推广网", "url": "https://www.meet-in-shanghai.net/cn/food/gongdelin-west-nanjing-road-930363/", "date": "2026-08-26"},
        {"quote": "When in Shanghai, the historic Gong De Lin at 445 West Nanjing Road is the flagship vegetarian restaurant", "source": "米其林指南", "url": MICHELIN_BASE + "gong-de-lin-jingan", "date": "2026-09-23"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.6}],
    extra_sources=[
        {"title": "企查查", "url": "https://www.qcc.com/cassets/5e593089508d250591f617a1b1382a38.html", "type": "map"},
    ],
))

rows.append(mk(
    name="粤海棠·wineapp", name_en="Yue Hai Tang",
    district="闵行区", address="闵行区号文路161号万金中心2号楼",
    phone="021-58587977", price_avg=380,
    cuisine_paths=[["中餐","粤菜"]],
    form="Finedining", michelin_star="一星", slug="yue-hai-tang",
    signature_dishes=["脆皮妙龄鸽", "叉烧", "醉虾", "海鲜炒饭"],
    notes="evidence_summary: 闵行七宝万金中心粤菜一星餐厅，名厨何柱君主理。粤菜+葡萄酒搭配模式，近500款全球葡萄酒。连续两年摘星。人均约380元。食客评价为上海外环唯一米其林一星。",
    diner_quotes=[
        {"quote": "比机场还远的米其林粤菜，我觉得能排上海前三。菜能打不贵，不收开瓶费，侍酒专业，酒单定价也良心", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7397424883350703394", "date": "2024-07-30"},
        {"quote": "偶然发现机场边上的这家一星米其林餐厅，叉烧和醉虾味道非常好", "source": "携程", "url": "https://you.ctrip.com/food/shanghai2/133521739-dianping.html", "date": "2026-05-22"},
    ],
    platform_scores=[{"platform": "高德", "score": 4.7}],
    extra_sources=[
        {"title": "米其林指南", "url": MICHELIN_BASE + "yue-hai-tang", "type": "official_guide"},
    ],
))

# === 分店缺（品牌在库，补该区分店） ===

rows.append(mk(
    name="利苑(徐汇)", name_en="Lei Garden",
    district="徐汇区", address="待核实(徐汇区)",
    phone=None, price_avg=500,
    cuisine_paths=[["中餐","粤菜"]],
    form="Finedining", michelin_star="一星", slug="lei-garden-xuhui",
    signature_dishes=["冰烧三层肉", "杨枝甘露", "虾饺", "煲仔饭"],
    brand_group="利苑酒家", brand_confirmed=True,
    notes="evidence_summary: 利苑酒家徐汇分店，米其林一星。品牌在库(id=493浦东国金店)。徐汇分店地址待核实。",
    diner_quotes=[
        {"quote": "（利苑徐汇分店地址/食客原话待补）", "source": "待补", "url": "", "date": None},
    ],
    platform_scores=[],
))

rows.append(mk(
    name="鹿园MOOSE(浦东店)", name_en="MOOSE",
    district="浦东新区", address="浦东新区浦东南路899号陆家嘴中心9层908-909号",
    phone=None, price_avg=330,
    cuisine_paths=[["中餐","江浙菜"]],
    form="Finedining", michelin_star="一星", slug="moose-pudong",
    signature_dishes=["外婆红烧肉", "温州鱼饼", "鸭壳", "本帮熏鱼"],
    brand_group="鹿园MOOSE", brand_confirmed=True,
    notes="evidence_summary: 鹿园浦东分店，位于陆家嘴中心9层。品牌在库(id=540长宁新华路店)。本帮江浙菜，人均约328-368元。",
    diner_quotes=[
        {"quote": "鹿园moose浦东店位于浦东南路899号陆家嘴中心9层908-909号，本帮江浙菜人均328", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7536572066598980905", "date": "2025-08-09"},
    ],
    platform_scores=[],
    extra_sources=[
        {"title": "米其林指南", "url": MICHELIN_BASE + "moose-pudong", "type": "official_guide"},
    ],
))

rows.append(mk(
    name="云和面馆(黄浦)", name_en="Yunhe Noodle",
    district="黄浦区", address="黄浦区(具体门牌待核实)",
    phone=None, price_avg=60,
    cuisine_paths=[["中餐","面食"]],
    form="Casual Dining", michelin_star="必比登", slug="yunhe-noodle-huangpu",
    signature_dishes=["爆鱼面", "葱油拌面", "辣肉面"],
    brand_group="云和面馆", brand_confirmed=True,
    notes="evidence_summary: 云和面馆黄浦分店。品牌在库(id=755长宁华山路店)。黄浦分店具体地址待核实。",
    diner_quotes=[
        {"quote": "（云和面馆黄浦分店地址/食客原话待补）", "source": "待补", "url": "", "date": None},
    ],
    platform_scores=[],
))

# === 其余真缺店（基本信息来自米其林指南，待深采） ===

remaining = [
    ("老兴鲜(黄浦)", "Lao Xing Xian", "黄浦区", "黄浦区(具体门牌待核实)", "入选", "lao-xing-xian",
     [["中餐","台州菜"]], "Casual Dining", 100, "待补"),
    ("台城镂月", "Toi Sihng Lauh Yuht", "待确认", "待确认", "入选", "toi-sihng-lauh-yuht",
     [["中餐","粤菜"]], "Finedining", 300, "待补"),
    ("食光", "Scarpetta", "待确认", "待确认", "入选", "scarpetta",
     [["西餐","意大利菜"]], "Casual Dining", 200, "注意：非老吴的食光(虹桥)，此为米其林名录意大利菜Scarpetta，近名异店"),
    ("松涧", "The Pine", "待确认", "待确认", "入选", "the-pine",
     [["西餐","欧陆菜"]], "Finedining", 400, "待补"),
    ("Torikaze", "Torikaze", "待确认", "待确认", "入选", "torikaze",
     [["亚洲菜","日式烧鸟"]], "Casual Dining", 200, "鸡肉串烧专门店，待补地址"),
    ("菰城宴", "The Taste of Huzhou", "待确认", "待确认", "必比登", "the-taste-of-huzhou",
     [["中餐","面食","湖州菜"]], "Casual Dining", 80, "2026新晋必比登，湖州风味面馆"),
    ("老地方面馆", "Lao Di Fang", "待确认", "待确认", "必比登", "lao-di-fang-mian-guan",
     [["中餐","面食"]], "Casual Dining", 50, "本地面馆，待补地址"),
    ("小陶面馆", "Xiao Tao Mian Guan", "待确认", "待确认", "必比登", "xiao-tao-mian-guan",
     [["中餐","面食"]], "Casual Dining", 50, "待补地址"),
    ("临湖素食", "The Lakeside Veggie", "待确认", "待确认", "必比登", "the-lakeside-veggie",
     [["中餐","素食"]], "Casual Dining", 100, "待补地址"),
    ("瑰禧", "Blossom", "待确认", "待确认", "必比登", "blossom-1246455",
     [["中餐","粤菜","潮州菜"]], "Finedining", 300, "2026新晋必比登，传统潮州菜"),
    ("157食坊", "157 Shi Fang", "长宁区", "长宁区凯旋路(具体门牌待核实)", "必比登", "157-shi-fang",
     [["中餐","沪菜"]], "Casual Dining", 180, "2026新晋必比登本帮菜，凯旋路，人均约181"),
    ("逸采(静安)", "Easeful Cuisine", "静安区", "静安区(具体门牌待核实)", "必比登", "easeful-cuisine",
     [["中餐","江浙菜"]], "Casual Dining", 100, "待补地址"),
    ("渔都老味面", "Yu Du Lao Wei Mian", "黄浦区", "黄浦区(具体门牌待核实)", "必比登", "yu-du-lao-wei-mian-huangpu",
     [["中餐","面食"]], "Casual Dining", 50, "待补地址"),
    ("渔哥·湛江(静安)", "Yu Ge Zhan Jiang", "静安区", "静安区(具体门牌待核实)", "必比登", "yu-ge-zhan-jiang-jingan",
     [["中餐","粤菜","湛江菜"]], "Casual Dining", 100, "待补地址"),
    ("Aster by Joshua Paris", "Aster by Joshua Paris", "待确认", "待确认", "入选", "aster-by-joshua-paris",
     [["西餐","欧陆菜"]], "Finedining", 500, "待补地址"),
    ("之舞", "La Scene Ronde", "待确认", "待确认", "入选", "la-scene-ronde",
     [["西餐","创新菜"]], "Finedining", 500, "待补地址"),
    ("Cellar to Table", "Cellar to Table", "待确认", "待确认", "入选", "cellar-to-table",
     [["西餐","意大利菜"]], "Bistro", 300, "酒窖主题意大利餐厅，待补地址"),
    ("海味观(静安)", "Hai Wei Guan", "静安区", "静安区(具体门牌待核实)", "入选", "hai-wei-guan",
     [["中餐","沪菜","海鲜"]], "Finedining", 300, "待补地址"),
    ("上海总会", "The Shanghai Club", "黄浦区", "黄浦区外滩(具体门牌待核实)", "入选", "shanghai-club",
     [["中餐","江浙菜"]], "Finedining", 400, "待补地址"),
    ("宏玉方", "Hong Yu Fang", "待确认", "待确认", "入选", "hong-yu-fang",
     [["中餐","点心"]], "Casual Dining", 100, "待补地址"),
    ("Trine", "Trine", "待确认", "待确认", "入选", "trine",
     [["西餐","欧陆菜"]], "Bistro", 300, "待补地址"),
    ("馨源楼", "Xin Yuan Lou", "待确认", "待确认", "入选", "xin-yuan-lou",
     [["中餐","粤菜"]], "Finedining", 300, "待补地址"),
    ("Scilla", "Scilla", "待确认", "待确认", "入选", "scilla",
     [["西餐","地中海菜"]], "Bistro", 300, "地中海菜，待补地址"),
    ("永·江臻", "Yong Jiang Zhen", "待确认", "待确认", "入选", "yong-jiang-zhen",
     [["中餐","江浙菜"]], "Finedining", 400, "待补地址"),
    ("古铜法式餐厅", "Cuivre", "待确认", "待确认", "入选", "cuivre",
     [["西餐","法国菜"]], "Finedining", 500, "待补地址"),
    ("滇道(静安)", "Legend Taste", "静安区", "静安区(具体门牌待核实)", "入选", "legend-taste-jingan",
     [["中餐","滇菜"]], "Casual Dining", 150, "云南菜，待补地址"),
    ("徐记海鲜(徐汇)", "Xu Ji Seafood", "徐汇区", "徐汇区(具体门牌待核实)", "入选", "xuji-seafood-xuhui",
     [["中餐","海鲜"]], "Casual Dining", 200, "连锁海鲜餐厅徐汇分店"),
    ("永丰面馆(黄浦)", "Yong Feng Mian Guan", "黄浦区", "黄浦区(具体门牌待核实)", "入选", "yong-feng-mian-guan",
     [["中餐","面食"]], "Casual Dining", 40, "待补地址"),
    ("Shaughnessy", "Shaughnessy", "待确认", "待确认", "入选", "shaughnessy",
     [["西餐","牛排馆"]], "Finedining", 500, "扒房，待补地址"),
    ("沼田双", "Numata Sou", "待确认", "待确认", "入选", "numata-sou-1215509",
     [["亚洲菜","日料","天妇罗"]], "Finedining", 800, "天妇罗专门店，待补地址"),
    ("和膳面家", "He Shan Mian Jia", "待确认", "待确认", "必比登", "he-shan-mian-jia",
     [["中餐","面食"]], "Casual Dining", 50, "2026新晋必比登面馆"),
    ("川粤海棠(长宁)", "Chuan Yue Hai Tang", "长宁区", "长宁区(具体门牌待核实)", "入选", "chuan-yue-hai-tang-changning",
     [["中餐","川菜"]], "Finedining", 300, "川菜，待补地址"),
    ("外滩·林家一", "Lin Family of One the Bund", "黄浦区", "黄浦区外滩(具体门牌待核实)", "入选", "lin-family-of-one-the-bund",
     [["中餐","台州菜"]], "Finedining", 400, "台州菜，待补地址"),
    ("徽季", "Hui Ji", "待确认", "待确认", "入选", "hui-ji",
     [["中餐","徽菜"]], "Casual Dining", 150, "待补地址"),
    ("悦轩", "Dining Room", "待确认", "待确认", "入选", "dining-room-1196349",
     [["中餐","江浙菜"]], "Finedining", 300, "注意：非恒悦轩(id=670)，此为米其林名录悦轩"),
    ("周舍(闵行)", "Zhou She", "闵行区", "闵行区(具体门牌待核实)", "一星", "zhou-she-minhang",
     [["中餐","沪菜"]], "Finedining", 300, "闵行区米其林一星本帮菜"),
    ("宁海食府", "Ning Hai Shi Fu", "待确认", "待确认", "必比登", "ning-hai-shi-fu",
     [["中餐","宁波菜"]], "Casual Dining", 150, "2026新晋必比登宁波菜"),
    ("阿勇面馆(东书房路)", "A Yong Mian Guan", "浦东新区", "浦东新区东书房路(具体门牌待核实)", "必比登", "a-yong-mian-guan-dongshufang-road",
     [["中餐","面食"]], "Casual Dining", 30, "2026新晋必比登面馆，人均约32"),
    ("Arva", "Arva", "闵行区", "闵行区(具体门牌待核实)", "入选", "arva-563644",
     [["西餐","意大利菜"]], "Finedining", 400, "闵行区意大利菜，待补地址"),
    ("菁禧荟(长宁)", "Amazing Chinese cuisine (Changning)", "长宁区", "长宁区(具体门牌待核实)", "二星", "amazing-chinese-cuisine-changning",
     [["中餐","粤菜","潮州菜"]], "Finedining", 600, "品牌在库id=494(黄浦BFC)/1472(虹口北外滩)，米其林名录标注长宁区，需核实是否为第三家分店或地址变更"),
]

for (name, en, dist, addr, star, slug, cpaths, form, price, note) in remaining:
    rows.append(mk(
        name=name, name_en=en, district=dist, address=addr,
        phone=None, price_avg=price, cuisine_paths=cpaths, form=form,
        michelin_star=star, slug=slug,
        signature_dishes=[],  # will be filled in later research
        notes=f"evidence_summary: {note}。地址/电话/招牌菜/食客原话待真人补证。",
        diner_quotes=[
            {"quote": f"（{name} 堂食客原话待补）", "source": "待补", "url": "", "date": None},
            {"quote": "（待补）", "source": "待补", "url": "", "date": None},
        ],
        platform_scores=[],
    ))

# Write
OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"Written {len(rows)} rows to {OUT}")

# Validate each line
import json as J
errors = 0
for i, line in enumerate(open(OUT, encoding="utf-8"), 1):
    line = line.strip()
    if not line:
        continue
    try:
        obj = J.loads(line)
        required = ["name", "district", "address", "price_avg", "signature_dishes",
                    "cuisine_paths", "form", "status", "evidence", "sources", "data_updated_at"]
        for k in required:
            if k not in obj:
                print(f"  Line {i}: MISSING required field '{k}'")
                errors += 1
    except J.JSONDecodeError as e:
        print(f"  Line {i}: JSON parse error: {e}")
        errors += 1

print(f"Validation: {len(rows)-errors} valid, {errors} errors")
