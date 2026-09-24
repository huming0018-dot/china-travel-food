#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, pathlib

rows = []

# 1. 翡翠36
rows.append({
  "name": "翡翠36", "name_en": "Jade on 36", "district": "浦东新区",
  "address": "浦东新区富城路33号浦东香格里拉紫金楼36楼",
  "price_avg": 800, "price_range": "午晚餐套餐/单点",
  "price_sources": [{"platform": "米其林指南", "value": 800, "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/jade-on-36"},
                    {"platform": "Trip.com", "value": 800, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/jade-on-11144298/"}],
  "signature_dishes": ["嫩煎牛蛙腿配蛤蜊欧芹酱汁", "脆皮妙龄鸽", "黑松露炒蛋", "三色巧克力法式炖蛋配黄油土司", "奶油龙虾汤"],
  "cuisine_paths": [["西餐", "法国菜"]], "form": "Finedining", "meals": ["午餐", "晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "入选", "black_pearl": 0, "source_url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/jade-on-36"},
  "phone_raw": "021-68828888", "booking_method": "电话(香格里拉总机转翡翠36)/订座",
  "brand_group": "香格里拉集团", "brand_confirmed": True, "scene": "高空江景法餐",
  "special_tags": ["江景位", "靠窗位需提前订"], "lat": None, "lng": None,
  "scores": {"objective": 78, "diner": 75, "taste": 78, "endorsement": 80, "soft_ad_penalty": 0, "platform_credibility": 0.85},
  "evidence": {
    "diner_quotes": [
      {"quote": "嫩煎牛蛙腿外酥里嫩，搭配蛤蜊欧芹酱汁，咸鲜中带着清新，是一道令人印象深刻的招牌前菜。", "dish": "嫩煎牛蛙腿配蛤蜊欧芹酱汁", "source": "Trip.com", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/jade-on-11144298/", "date": "2025-10-21"},
      {"quote": "甜品是三色巧克力法式炖蛋配法式黄油土司，三个小碟分别是略甜的白巧克力、香浓的牛奶巧克力和微微苦的黑巧克力炖蛋，细腻绵密，最爱的是黑巧克力那一碟。餐前面包种类多，配的三色黄油味道很特别。", "dish": "三色巧克力法式炖蛋", "source": "Trip.com", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/Jade%20on%2036-480911/", "date": "2025-03-29"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.7, "review_count": 527, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/jade-on-11144298/"},
      {"platform": "米其林指南", "score": 4.0, "review_count": None, "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/jade-on-36"}
    ],
    "negative_signals": ["人均偏高，江景溢价明显", "部分食客反映出品与早年Paul Pairet时期有落差"],
    "soft_ad_flags": [],
    "traffic_signals": ["靠窗江景位需提前预订", "陆家嘴高空约会/宴请场景"]
  },
  "sources": [
    {"title": "米其林指南 - 翡翠36", "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/jade-on-36", "type": "official_guide"},
    {"title": "香格里拉官网 - Jade on 36", "url": "https://www.shangri-la.com/cn/shanghai/pudongshangrila/dining/restaurants/jade-on-36/", "type": "brand_official"},
    {"title": "Trip.com食客点评 - 翡翠36", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/jade-on-11144298/", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "翡翠36位于浦东香格里拉紫金楼36层，是陆家嘴高空法餐的代表，落地窗正对外滩与黄浦江，黄昏到夜景时段景观最佳。食客实测中，嫩煎牛蛙腿是被反复点名的招牌前菜，外酥里嫩、配蛤蜊欧芹酱汁咸鲜带清新；甜品收尾的三色巧克力法式炖蛋分白巧、牛奶巧、黑巧三碟，口感绵密，黑巧那一碟最受好评。餐前面包配三色黄油也被记住。作为米其林入选餐厅，它的核心卖点是景观与法式经典的平衡，适合约会纪念日宴请；但也有食客认为人均八百的价格里江景溢价占比不小，出品相比早年名厨主理时期趋于稳妥。横向看，它与半岛艾利爵士同属高空江景Fine Dining，翡翠36偏法式传统、艾利爵士偏北意，可按菜系偏好二选一。",
  "notes": "电话为香格里拉总机，订座需转餐厅。"
})

# 2. Aster by Joshua Paris
rows.append({
  "name": "Aster by Joshua Paris", "name_en": "Aster by Joshua Paris", "district": "静安区",
  "address": "静安区永源路150号208室(近南京西路)",
  "price_avg": 627, "price_range": "品鉴套餐约627-2670元",
  "price_sources": [{"platform": "携程笔记", "value": 627, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=242862873"},
                    {"platform": "抖音", "value": 1335, "url": "https://www.iesdouyin.com/share/video/7631621883833986118"}],
  "signature_dishes": ["湖州醉鸽子", "法式填充鸡Poulet Farci", "新西兰帝王鲑", "黑鳕鱼马赛鱼汤汁", "甜菜根沙拉"],
  "cuisine_paths": [["西餐", "欧陆菜"]], "form": "Finedining", "meals": ["晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "入选", "black_pearl": 0, "source_url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/aster-by-joshua-paris"},
  "phone_raw": "15618828656", "booking_method": "电话预约15618828656，周二至周日18:00-24:00",
  "brand_group": None, "brand_confirmed": False, "scene": "Modern European bistro-fine",
  "special_tags": ["约会"], "lat": None, "lng": None,
  "scores": {"objective": 72, "diner": 78, "taste": 80, "endorsement": 75, "soft_ad_penalty": 0, "platform_credibility": 0.8},
  "evidence": {
    "diner_quotes": [
      {"quote": "Aster位于静安区永源路150号，算是一家Fine Bistro，介于小酒馆和Fine Dining中间。菜单很精简只有一页。前菜点了招牌湖州醉鸽子，主菜点了新西兰帝王鲑、法式填充鸡、羊排、羊腩。", "dish": "湖州醉鸽子/法式填充鸡", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7631621883833986118", "date": "2026-04-23"},
      {"quote": "法式填充鸡是道功夫菜，鸡肉混着菌菇奶油打成慕斯手工填进鸡胸鸡翅里，淋上鸡肝奶油浓缩酱，配碳烤羊肚菌和马德拉酒汁，整道菜就一个字香。恒温油封慢煮的新西兰帝王鲑，口感宛若果冻，配上橘粉色摆盘。", "dish": "法式填充鸡/新西兰帝王鲑", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260635859", "date": "2026-01-28"}
    ],
    "platform_scores": [
      {"platform": "携程", "score": 4.6, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=242862873"},
      {"platform": "米其林指南", "score": 4.0, "review_count": None, "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/aster-by-joshua-paris"}
    ],
    "negative_signals": ["新店评价基数尚小", "仅晚市营业，周二休息"],
    "soft_ad_flags": [],
    "traffic_signals": ["前UV紫外线主厨背景", "静安区新晋约会热门"]
  },
  "sources": [
    {"title": "米其林指南 - Aster by Joshua Paris", "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/aster-by-joshua-paris", "type": "official_guide"},
    {"title": "SmartShanghai场馆页 - Aster", "url": "https://www.smartshanghai.com/venue/34492/aster_by_joshua_paris", "type": "media"},
    {"title": "抖音食客探店 - Aster by Joshua Paris", "url": "https://www.iesdouyin.com/share/video/7631621883833986118", "type": "ugc"},
    {"title": "携程笔记 - 魔都新晋Fine Bistro", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260635859", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "Aster by Joshua Paris是前米其林三星UV紫外线主厨Josh Paris在静安开出的Modern European新店，定位介于Bistro与Fine Dining之间，菜单精简到一页。食客实测记忆点集中在两道功夫菜：招牌湖州醉鸽子用黄酒醉制替代绍兴酒处理鸽馔，去掉野味；法式填充鸡Poulet Farci把鸡肉混菌菇奶油打成慕斯手工填进鸡胸鸡翅，再淋鸡肝奶油酱、配碳烤羊肚菌与马德拉酒汁，被形容为'整道菜就一个字香'。恒温油封慢煮的新西兰帝王鲑口感像果冻。横向上，它走的是克制而有技法密度的欧陆 contemporary 路线，比同片区纯Bistro更精致，但又不像一星餐厅那样紧绷。适合约会。需注意仅做晚市、周二店休。",
  "notes": "地址以多数UGC(永源路150号208室)为准，米其林英文页写作132号，疑似同楼不同门牌表述。"
})

# 3. 之舞 La Scene Ronde
rows.append({
  "name": "之舞", "name_en": "La Scene Ronde", "district": "黄浦区",
  "address": "黄浦区茂名南路59号锦江饭店锦楠楼底层大堂B座03",
  "price_avg": 1400, "price_range": "品鉴套餐1380-1580元+10%服务费",
  "price_sources": [{"platform": "抖音自费探店", "value": 1380, "url": "https://www.iesdouyin.com/share/video/7660916623000611761"},
                    {"platform": "携程笔记", "value": 1580, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=341196129"}],
  "signature_dishes": ["海胆宴(季节限定)", "燕皮包和牛奶浆菌", "脆甜马蹄笋配5J伊比利亚火腿", "手工大地豆腐虎松茸贝贝南瓜", "牛里脊昆布"],
  "cuisine_paths": [["西餐", "创新菜"]], "form": "Finedining", "meals": ["晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "入选", "black_pearl": 0, "source_url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/la-scene-ronde"},
  "phone_raw": None, "booking_method": "预约制板前，仅8座；海胆季1580+10%",
  "brand_group": "成隆行集团", "brand_confirmed": True, "scene": "日法板前Omakase",
  "special_tags": ["板前", "季节菜单"], "lat": None, "lng": None,
  "scores": {"objective": 72, "diner": 76, "taste": 78, "endorsement": 75, "soft_ad_penalty": 0, "platform_credibility": 0.8},
  "evidence": {
    "diner_quotes": [
      {"quote": "来吃日法finedining叫SR之舞，刚搬到锦江饭店，门口有很漂亮的日式庭院。光餐费1380一位加10%服务费。开头是清爽开胃饮品里面有奇亚籽，两道前菜摆成漂亮画面，这个是土豆脆片中间加火腿和酸奶酱。", "dish": "开胃饮品/土豆脆片火腿酸奶酱", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7660916623000611761", "date": "2026-07-10"},
      {"quote": "燕皮包住软嫩和牛，融入奶浆菌独有的山野香气，口感柔和不压味。脆甜马蹄笋配5J伊比利亚火腿，橄榄轻轻提味，脆感和油脂香平衡得刚好。手工大地豆腐嫩滑，配虎松茸与绵甜贝贝南瓜，清淡素口缓冲肉食厚重。牛里脊火候到位，软嫩多汁，昆布衬出淡淡海味。", "dish": "燕皮包和牛/马蹄笋火腿/大地豆腐", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=361398885", "date": "2026-08-22"}
    ],
    "platform_scores": [
      {"platform": "携程", "score": 4.7, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=361398885"},
      {"platform": "米其林指南", "score": 4.0, "review_count": None, "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/la-scene-ronde"}
    ],
    "negative_signals": ["老店新开搬迁后仍在磨合", "席位仅8座难订", "服务费另计10%"],
    "soft_ad_flags": [],
    "traffic_signals": ["海胆季限马粪海胆最好两周", "加入成隆行后客流上升"]
  },
  "sources": [
    {"title": "米其林指南 - La Scene Ronde", "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/la-scene-ronde", "type": "official_guide"},
    {"title": "抖音自费生日探店 - SR之舞", "url": "https://www.iesdouyin.com/share/video/7660916623000611761", "type": "ugc"},
    {"title": "携程笔记 - 赶上SR海胆季尾巴", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=361398885", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "之舞La Scene Ronde SR是主厨山野勇辉(日本熊本出身，法意比米其林副厨背景)主理的日法融合板前，2026年从恒基旭辉天地搬迁至茂名南路锦江饭店锦楠楼并加入成隆行集团，新空间仅8个板前席位。食客实测，套餐节奏从前调开胃饮品(加奇亚籽)、土豆脆片夹火腿酸奶酱前菜起，一路推进到燕皮包和牛奶浆菌、脆甜马蹄笋配5J伊比利亚火腿、手工大地豆腐配虎松茸贝贝南瓜、牛里脊昆布收尾，被评价为调味平衡、轻盈不腻。夏季限定海胆宴(1580+10%)把马粪海胆拆进整套菜单而非最后端整板。它的定位是独膳友好的板前圆舞，与同集团成隆行的中式宴请形成互补；缺点是席位极少、服务费另计，新店磨合期出品仍需观察。",
  "notes": "已搬迁：旧址恒基旭辉天地(Lane 458 Madang Rd)，现址锦江饭店锦楠楼。电话未取得可靠直线，留空。"
})

# 4. 古铜 Cuivre
rows.append({
  "name": "古铜法式餐厅", "name_en": "Cuivre", "district": "徐汇区",
  "address": "徐汇区淮海中路1502号-1临(近乌鲁木齐南路)",
  "price_avg": 273, "price_range": "人均约273元",
  "price_sources": [{"platform": "携程(点评聚合)", "value": 273, "url": "https://you.ctrip.com/food/shanghai2/448393-dianping193072629.html"},
                    {"platform": "穷游", "value": 327, "url": "https://m.qyer.com/place/poi/V2UJZVFlBzNTYVI_Cm0/reviews"}],
  "signature_dishes": ["油封鸭腿", "罗西尼菲力牛排配法式红酒鹅肝", "乡村蒜香蜗牛", "法式洋葱汤", "三文鱼惠灵顿", "鹅肝配chorizo"],
  "cuisine_paths": [["西餐", "法国菜"]], "form": "Bistro", "meals": ["午餐", "晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "入选", "black_pearl": 0, "source_url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/cuivre"},
  "phone_raw": "021-64374219", "booking_method": "电话021-64374219，周二休息",
  "brand_group": None, "brand_confirmed": False, "scene": "南法小酒馆Bistro",
  "special_tags": ["老牌bistro"], "lat": None, "lng": None,
  "scores": {"objective": 70, "diner": 76, "taste": 76, "endorsement": 60, "soft_ad_penalty": 0, "platform_credibility": 0.8},
  "evidence": {
    "diner_quotes": [
      {"quote": "法领馆旁边开了十几年的法式小馆，把格调、出品和性价比拿捏得很舒服，旁边80%都是法国人。乡村菜蜗牛是要点的，蒜香浓郁，摆盘落落大方。", "dish": "乡村蒜香蜗牛", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7481655959312518463", "date": "2025-03-14"},
      {"quote": "黑松露罗西尼菲力牛排配法式红酒鹅肝，菲力肉质嫩得像云朵一样，鹅肝入口即化还带着酒香，吃到这里已经值回票价。另一道主菜外皮烤得酥脆，鸡肉鲜嫩多汁。", "dish": "罗西尼菲力配鹅肝", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7570568957896607473", "date": "2025-11-09"}
    ],
    "platform_scores": [
      {"platform": "Google(经wanderlog聚合)", "score": 4.3, "review_count": None, "url": "https://wanderlog.com/place/details/1078912/cuivre-french-restaurant"},
      {"platform": "米其林指南", "score": 4.0, "review_count": None, "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/cuivre"}
    ],
    "negative_signals": ["老店装修偏陈旧", "部分食客反映意面分量偏少", "性价比多年后略有下滑"],
    "soft_ad_flags": [],
    "traffic_signals": ["周边法国侨民常客", " upstairs儿童区适合家庭"]
  },
  "sources": [
    {"title": "米其林指南 - Cuivre", "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/cuivre", "type": "official_guide"},
    {"title": "TimeOut - Cuivre venue", "url": "https://www.timeoutshanghai.com/venue/Restaurants__Cafes-European-French/3872/Cuivre.html", "type": "media"},
    {"title": "抖音食客 - 古铜Cuivre生日周", "url": "https://www.iesdouyin.com/share/video/7481655959312518463", "type": "ugc"},
    {"title": "穷游食客点评 - Cuivre", "url": "https://m.qyer.com/place/poi/V2UJZVFlBzNTYVI_Cm0/reviews", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "古铜Cuivre是淮海中路近乌鲁木齐南路上开了十几年的南法小酒馆，是上海老牌法餐brasserie的活化石。食客实测，它的客群里约八成是在沪法国人，出品走量大而稳的乡村路线：乡村蒜香蜗牛蒜香浓郁；罗西尼菲力配法式红酒鹅肝被反复点名，菲力嫩如云朵、鹅肝入口即化带酒香；油封鸭腿、法式洋葱汤、三文鱼惠灵顿是常备点单。穷游食客还推荐牛眼肉牛排与水波蛋。横向上，它不是创意法餐而是正统南法家常bistro，价格人均两百多在米其林入选餐厅里属亲民档；缺点是装修陈旧、部分菜品分量(如意面)偏少，性价比相比早年略有下滑。适合想认真吃一顿不折腾的法国家常菜。",
  "notes": "米其林标注徐汇区，TATLER旧页误标黄浦区，实为徐汇区淮海中路1502号。"
})

# 5. Shaughnessy
rows.append({
  "name": "Shaughnessy", "name_en": "Shaughnessy", "district": "黄浦区",
  "address": "黄浦区淮海东路45-49号东淮海国际大厦22楼(近大世界)",
  "price_avg": 1250, "price_range": "人均约1250元",
  "price_sources": [{"platform": "DiningCity", "value": 1250, "url": "https://www.diningcity.cn/zh/shanghai/shaughnessy_restaurant_bar_shangnasi"}],
  "signature_dishes": ["干式熟成西冷(28天)", "干式熟成肉眼", "得克萨斯烤猪肋排", "香草烤羊小排", "熟成乳鸽", "鸡尾酒大虾"],
  "cuisine_paths": [["西餐", "牛排馆"]], "form": "Finedining", "meals": ["午餐", "晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "入选", "black_pearl": 0, "source_url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/shaughnessy"},
  "phone_raw": "021-60296789", "booking_method": "电话021-60296789",
  "brand_group": None, "brand_confirmed": False, "scene": "美式干式熟成牛排馆",
  "special_tags": ["高空景", "约会"], "lat": None, "lng": None,
  "scores": {"objective": 74, "diner": 78, "taste": 78, "endorsement": 70, "soft_ad_penalty": 0, "platform_credibility": 0.8},
  "evidence": {
    "diner_quotes": [
      {"quote": "团的998双人餐，是28天的西冷牛排，高温炭烤过口感确实不一般。得克萨斯烤猪肋排烟熏味十足。每日精选生蚝和鸡尾酒虾口感鲜甜。甜品选了芝士浓郁的巴斯克蛋糕和焦糖布丁。生日纪念日店里还有免费花瓣布置。", "dish": "28天干式熟成西冷/烤猪肋排", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7176068683305995553", "date": "2022-12-12"},
      {"quote": "点了招牌干式熟成西冷，端上桌滋滋作响，焦香外皮泛着焦糖色，一刀切下内里粉嫩，丰盈肉汁溢出。干式熟成带来独特风味，肉质紧实弹牙，带着淡淡坚果香与发酵的醇厚感，没有普通牛排的油腻。", "dish": "干式熟成西冷", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=251266912", "date": "2026-01-05"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.6, "review_count": None, "url": "https://www.trip.com/restaurant/china/shanghai/detail/shaughnessy-130890829/"},
      {"platform": "DiningCity", "score": 9.4, "review_count": None, "url": "https://www.diningcity.cn/zh/shanghai/shaughnessy_restaurant_bar_shangnasi"}
    ],
    "negative_signals": ["高空写字楼餐厅，景观与价格匹配度见仁见智", "双人套餐团购与正价单点落差被提及"],
    "soft_ad_flags": [],
    "traffic_signals": ["28-180天干式熟成柜", "大世界地铁站高空约会位"]
  },
  "sources": [
    {"title": "米其林指南 - Shaughnessy", "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/shaughnessy", "type": "official_guide"},
    {"title": "Trip.com - Shaughnessy", "url": "https://www.trip.com/restaurant/china/shanghai/detail/shaughnessy-130890829/", "type": "ugc"},
    {"title": "抖音食客 - 尚纳斯圣诞约会", "url": "https://www.iesdouyin.com/share/video/7176068683305995553", "type": "ugc"},
    {"title": "携程笔记 - 干式熟成西冷食记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=251266912", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "Shaughnessy(尚纳斯)是一家坐在东淮海国际大厦22楼的美式干式熟成牛排馆，俯瞰外滩与陆家嘴天际线，主打在店内熟成柜熟成28到180天的Black Angus牛排，桌边切配配pan jus。食客实测，28天干式熟成西冷高温炭烤后外皮焦脆、内里粉嫩多汁，被形容带坚果香与发酵醇厚感、不腻；得克萨斯烤猪肋排烟熏味足；鸡尾酒大虾与生蚝鲜甜；巴斯克蛋糕与焦糖布丁收尾稳定。除牛排外还提供熟成乳鸽、苏格兰蓝龙虾等海鲜。横向上，它是上海少数坚持自制长天期干式熟成的扒房，比连锁牛排馆更有老纽约风味；但高空位有景观溢价，团购双人餐与正价单点的出品落差被部分食客提及。适合纪念日约会。",
  "notes": "勿与武夷路168号B1那家低温慢烤牛排馆混淆(不同店)。"
})

# 6. Arva
rows.append({
  "name": "Arva", "name_en": "Arva", "district": "闵行区",
  "address": "闵行区元江路6161号养云安缦酒店1楼",
  "price_avg": 800, "price_range": "人均800-1200元",
  "price_sources": [{"platform": "DiningCity", "value": 800, "url": "https://www.diningcity.cn/zh/shanghai/arva_italian_restaurant_amanyangyun"},
                    {"platform": "高德", "value": 784, "url": "https://www.diningcity.cn/zh/shanghai/arva_italian_restaurant_amanyangyun"}],
  "signature_dishes": ["牛肝菌清汤松露意式饺子", "香煎银鳕鱼", "海螯虾南瓜阿玛菲柠檬", "羊乳奶酪饺子黑松露", "小青龙海鲜烩饭", "提拉米苏"],
  "cuisine_paths": [["西餐", "意大利菜"]], "form": "Finedining", "meals": ["午餐", "晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "入选", "black_pearl": 0, "source_url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/arva-563644"},
  "phone_raw": "021-80119999", "booking_method": "电话(养云安缦总机021-80119999)，窗边日落位提前3天",
  "brand_group": "安缦Aman", "brand_confirmed": True, "scene": "湖畔托斯卡纳农场到餐桌",
  "special_tags": ["酒店餐厅", "湖景"], "lat": None, "lng": None,
  "scores": {"objective": 74, "diner": 76, "taste": 80, "endorsement": 82, "soft_ad_penalty": 0, "platform_credibility": 0.85},
  "evidence": {
    "diner_quotes": [
      {"quote": "餐厅在养云安缦酒店一楼。牛肝菌清汤松露意式饺子有5颗，份量可以。香煎银鳕鱼切了厚厚的一片，鲜美无比，这个超赞。嫩煎雪白带子有三颗。", "dish": "牛肝菌松露意饺/香煎银鳕鱼", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=99832118", "date": "2024-11-16"},
      {"quote": "干式熟成三文鱼加金橘是酸甜碰撞，清新平衡。海螯虾配南瓜阿玛菲柠檬，韩国辣椒酱带来微妙刺激。黑鳕鱼鳗鱼花椰菜，味噌山葵让海鲜层次感爆棚。羊乳奶酪饺子配黑松露，榛子黄油泡沫香到跺脚。", "dish": "海螯虾南瓜/羊乳奶酪饺子", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=223827934", "date": "2025-11-06"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.8, "review_count": None, "url": "https://www.trip.com/moments/poi-arva-47743980/"},
      {"platform": "DiningCity", "score": 9.2, "review_count": None, "url": "https://www.diningcity.cn/zh/shanghai/arva_italian_restaurant_amanyangyun"}
    ],
    "negative_signals": ["位置偏远(闵行马桥)，非住客专程前往成本高", "人均800-1200含酒店溢价"],
    "soft_ad_flags": [],
    "traffic_signals": ["食材多来自酒店自有生态菜园", "日落窗边位需提前3天约"]
  },
  "sources": [
    {"title": "米其林指南 - Arva", "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/arva-563644", "type": "official_guide"},
    {"title": "安缦官网 - Arva at Amanyangyun", "url": "https://www.aman.com/zh-cn/resorts/amanyangyun/dining", "type": "brand_official"},
    {"title": "携程笔记 - 安缦意大利菜", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=223827934", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "Arva是养云安缦酒店内的湖畔意大利餐厅，隐于樟树林与水景之间，主打cucina del raccolto'从农场到餐桌'，食材多用酒店自有生态菜园。食客实测，牛肝菌清汤松露意式饺子一份五颗、香煎银鳕鱼厚切鲜美、嫩煎雪白带子三颗；限定菜单里干式熟成三文鱼配金橘、海螯虾配南瓜阿玛菲柠檬加韩式辣椒酱、黑鳕鱼鳗鱼花椰菜配味噌山葵、羊乳奶酪饺子配黑松露榛子黄油泡沫被反复夸赞意式灵魂与亚洲调味的碰撞。提拉米苏与小青龙烩饭也是常驻高分项。横向上，它的核心价值是安缦空间加稳定的当代地中海料理，米其林连获推荐；缺点是地处闵行马桥、远离市区，专程前往的时间成本与酒店溢价都不低，更适合住店或半日 escape。",
  "notes": "电话为养云安缦总机。高德评分4.4人均784。"
})

# 7. Ortensia Shanghai
rows.append({
  "name": "Ortensia Shanghai", "name_en": "Ortensia", "district": "静安区",
  "address": "静安区茂名北路240号张园W14栋(19世纪石库门老宅)",
  "price_avg": 1688, "price_range": "品鉴套餐1288/1688/2288元三档(+10%服务费)",
  "price_sources": [{"platform": "Rolling Grace/官网", "value": 1688, "url": "https://rollinggrace.com/2026/07/15/ortensia-shanghai/"}],
  "signature_dishes": ["龙井绿茶烟熏乳鸽", "鱼子酱牛肉塔塔", "提灯鸡翅", "木姜子金沙参扇贝", "海鳌虾节瓜花天妇罗"],
  "cuisine_paths": [["西餐", "法餐"]], "form": "私宴会所", "meals": ["午餐", "晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
  "phone_raw": "19101630530", "booking_method": "官网restaurantortensia.com预约，每月15号开放下月预订，晚餐订金1000/位",
  "brand_group": "巴黎Ortensia二店", "brand_confirmed": True, "scene": "张园石库门法餐",
  "special_tags": ["预订制", "包厢"], "lat": None, "lng": None,
  "scores": {"objective": 72, "diner": 78, "taste": 82, "endorsement": 80, "soft_ad_penalty": 5, "platform_credibility": 0.8},
  "evidence": {
    "diner_quotes": [
      {"quote": "这道乳鸽是这顿里最惊艳的，鸽子先用龙井茶烟熏过再用备长炭烤。这条菲力又弹又软又嫩，像果冻一样，娇艳欲滴的粉色。烟熏草木味在鸽腿上会有点过重。", "dish": "龙井茶烟熏乳鸽", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7649759233739395685", "date": "2026-06-10"},
      {"quote": "鸡翅从盆栽里拿出来，咬的时候小心真的一口爆浆，鸡翅里包了一颗提灯，溏心带着花雕酒香溢出来。招牌牛肉塔塔从上到下是鱼子酱、烟熏土豆慕斯、牛肉塔塔高汤啫喱，一勺下去牛肉很柔润，整体轻盈蓬松。", "dish": "提灯鸡翅/鱼子酱牛肉塔塔", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7579891012798090537", "date": "2025-12-04"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.5, "review_count": None, "url": "https://tw.trip.com/restaurant/china/shanghai/detail/ortensia-restaurant-149568493"},
      {"platform": "官网/预订制", "score": None, "review_count": None, "url": "https://www.restaurantortensia.com/shanghai"}
    ],
    "negative_signals": ["曾因前女主厨'猪扒饭'争议被网暴", "不接受素食/无麸质特殊饮食", "鳗鱼一道偏咸(搜狐食客差评)", "套餐固定不可调"],
    "soft_ad_flags": ["部分探店为媒体 hosted tasting"],
    "traffic_signals": ["每月15号开放下月预订秒光", "张园石库门空间出片"]
  },
  "sources": [
    {"title": "Rolling Grace - Ortensia Shanghai", "url": "https://rollinggrace.com/2026/07/15/ortensia-shanghai/", "type": "media"},
    {"title": "Ortensia官网-预订规则", "url": "https://www.restaurantortensia.com/shanghai", "type": "brand_official"},
    {"title": "抖音食客 - Ortensia新婚漂亮饭", "url": "https://www.iesdouyin.com/share/video/7649759233739395685", "type": "ugc"},
    {"title": "抖音食客 - 被攻击的Ortensia实测", "url": "https://www.iesdouyin.com/share/video/7579891012798090537", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "Ortensia是巴黎一星法餐厅在张园石库门老宅开出的上海二店，走东方茶香与法式炭烤结合的路线。食客实测的最大记忆点是龙井绿茶烟熏乳鸽：先用龙井茶低温烟熏再备长炭烤，鸽胸粉嫩如果冻、烟熏香在口中萦绕，但也有食客觉得鸽腿部位烟熏味略重。招牌牛肉塔塔以鱼子酱、烟熏土豆慕斯、牛肉塔塔高汤啫喱三层叠成，入口柔润蓬松；提灯鸡翅把溏心提灯包进烤鸡翅里，咬开带花雕酒香爆浆。横向上，它是上海'漂亮饭'赛道里技法密度较高的一家，环境与出片属性拉满；但争议不断——前女主厨事件、不接受特殊饮食、套餐固定，也有食客给出'不好意思给差评'的中庸评价，认为主菜乳鸽鸭肝鳗鱼组合里鳗鱼偏咸。预订制、每月15号放号秒光是常态。",
  "notes": "巴黎一星二店，2024年10月开业。Trip.com页写茂名北路230号，与raw240号有出入，以张园W14栋门牌为准。"
})

# 8. Endo
rows.append({
  "name": "Endo", "name_en": "Endo", "district": "徐汇区",
  "address": "徐汇区武夷路320弄Wuyi MIX320街区",
  "price_avg": 600, "price_range": "甜点品鉴套餐配茶/酒，人均550-600元",
  "price_sources": [{"platform": "抖音食客", "value": 600, "url": "https://www.iesdouyin.com/share/video/7448307649822641465"}],
  "signature_dishes": ["鼠尾草酸奶油青提开场甜品", "洋甘菊啫喱意式奶冻配黑豆纳豆", "茉莉青梅露", "米布丁伪装burrata(蜂蜜酸奶慕斯百香果雪芭)", "桃子芬诺雪葩配核桃奶酪无花果叶"],
  "cuisine_paths": [["西餐", "甜品"]], "form": "私宴会所", "meals": ["下午茶"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
  "phone_raw": "15221274511", "booking_method": "电话预约15221274511，至少提前3天",
  "brand_group": None, "brand_confirmed": False, "scene": "甜点Omakase品鉴",
  "special_tags": ["预约制", "甜品专门店"], "lat": None, "lng": None,
  "scores": {"objective": 60, "diner": 72, "taste": 74, "endorsement": 60, "soft_ad_penalty": 0, "platform_credibility": 0.75},
  "evidence": {
    "diner_quotes": [
      {"quote": "和朋友打卡Endo冬季菜单，人均600的甜品omakase。第二道小点底部是意式奶冻，上面有洋甘菊啫喱和凤梨渍，黑豆是店里自制黑豆纳豆，糖分来自椴树蜜结晶。这道味道比第一道好，但我建议把黑豆拿掉，因为黑豆的突兀感有点抢。", "dish": "洋甘菊啫喱意式奶冻", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7448307649822641465", "date": "2024-12-15"},
      {"quote": "店家自酿茉莉青梅露，质地在果冻和液体的临界点，喝着像果冻入口化成茶，很特别。第二大点看着像布拉塔其实是米布丁，下面是蜂蜜酸奶慕斯、奶粉饼，上面还有百香果雪芭。", "dish": "茉莉青梅露/米布丁burrata", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7408011084268981541", "date": "2024-08-28"}
    ],
    "platform_scores": [
      {"platform": "TimeOut(推荐)", "score": None, "review_count": None, "url": "http://www.timeoutshanghai.com/features/Feature/105570/8-Eateries-in-Shanghai-Where-Reservations-Are-Rather-Necessary.html"}
    ],
    "negative_signals": ["有食客认为'中看不中吃'、味道仍有提升空间", "黑豆纳豆等元素接受度两极", "仅甜品非正餐，定位小众"],
    "soft_ad_flags": [],
    "traffic_signals": ["上海首家盘式甜品配酒专门店", "需提前3天预约，难订"]
  },
  "sources": [
    {"title": "TimeOut EN - Endo dessert degustation", "url": "http://www.timeoutshanghai.com/features/Feature/105570/8-Eateries-in-Shanghai-Where-Reservations-Are-Rather-Necessary.html", "type": "media"},
    {"title": "人民网 - Wuyi MIX320街区", "url": "http://sh.people.com.cn/BIG5/n2/2021/1212/c134768-35047126.html", "type": "media"},
    {"title": "抖音食客 - Endo冬季菜单甜品omakase", "url": "https://www.iesdouyin.com/share/video/7448307649822641465", "type": "ugc"},
    {"title": "抖音食客 - Endo是不是真值得", "url": "https://www.iesdouyin.com/share/video/7408011084268981541", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "Endo是上海首家盘式甜品品鉴(degustation)专门店，开在武夷路MIX320，把法式西点技法做成一套配茶或配酒的omakase，需提前电话预约。食客实测，菜单随季节更换：开场是鼠尾草酸奶油配青提的清爽道；中段有洋甘菊啫喱意式奶冻配自制黑豆纳豆与椴树蜜结晶——有食客明确建议去掉黑豆，觉得突兀抢味；自酿茉莉青梅露质地介于果冻与液体之间，入口化茶被记住；伪装成布拉塔的米布丁由蜂蜜酸奶慕斯、奶粉饼与百香果雪芭构成。横向上，它是甜品爱好者的仪式感体验，但单价五六百仅吃甜品对普通食客偏高，评价两极：有人觉得是艺术、有人觉得'中看不中吃'。适合甜点头尾专门去。",
  "notes": "仅TimeOut一篇媒体稿+抖音食客，无点评平台分。"
})

# 9. Hide the Smoked Room
rows.append({
  "name": "Hide the Smoked Room", "name_en": "Hide The Smoked Room", "district": "徐汇区",
  "address": "徐汇区复兴中路1331号黑石公寓3幢2层201",
  "price_avg": 600, "price_range": "板前/卡座/包间，炭火融合料理",
  "price_sources": [{"platform": "TimeOut", "value": 600, "url": "https://www.timeoutshanghai.cn/features/7400.html"}],
  "signature_dishes": ["烟熏梅菜黑猪肋排", "中华烤鸡翅", "花椒火焰竹蛏王", "云南素番茄配布拉塔", "烤西兰苔刷寄居蟹酱", "贵州糟粕汁炸鱼"],
  "cuisine_paths": [["西餐", "融合菜"], ["中餐", "融合菜"]], "form": "私宴会所", "meals": ["晚餐", "夜宵"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
  "phone_raw": None, "booking_method": "预约制，18:00-次日3:00，大厅21点后供水烟",
  "brand_group": None, "brand_confirmed": False, "scene": "原火炭烤融合lounge",
  "special_tags": ["板前", "水烟", "营业至凌晨"], "lat": None, "lng": None,
  "scores": {"objective": 62, "diner": 76, "taste": 76, "endorsement": 65, "soft_ad_penalty": 5, "platform_credibility": 0.75},
  "evidence": {
    "diner_quotes": [
      {"quote": "黑石公寓二楼，一个红色按钮打开门，低调的奢华像王家卫电影。烟熏梅菜黑猪肋排，果木高温炭烤，经过15年花雕酒低温慢煮，肉质松软香味浓郁，搭配原汤肉汁的梅干菜，真的绝了。", "dish": "烟熏梅菜黑猪肋排", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=56085163", "date": "2024-06-13"},
      {"quote": "炸鱼鳞脆得像薯片，鱼肉嫩到锁满汁水没有腥味，贵州糟粕汁带着类似冬阴功的鲜爽。中华烤鸡翅表皮焦香裹着甜口秘制酱，咬开直接爆汁，烟熏味克制得不抢鸡肉本身的香。还有柔煮章鱼佐中东甜椒。", "dish": "贵州糟粕汁炸鱼/中华烤鸡翅", "source": "携程", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=325369899", "date": "2026-06-22"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.5, "review_count": None, "url": "https://us.trip.com/restaurant/china/shanghai/detail/restaurant-143238914/"},
      {"platform": "TimeOut(推荐)", "score": None, "review_count": None, "url": "https://www.timeoutshanghai.cn/features/7400.html"}
    ],
    "negative_signals": ["21点后变水烟lounge，餐与酒氛围混杂", "王嘉尔打卡后网红化、偶遇属性大于纯粹餐", "私宴属性偏弱"],
    "soft_ad_flags": ["王嘉尔/林更新社媒分享后人流涌入"],
    "traffic_signals": ["黑石公寓楼上隐蔽空间(红色按钮进门)", "营业到凌晨3点"]
  },
  "sources": [
    {"title": "TimeOut上海 - Hide the Smoked Room", "url": "https://www.timeoutshanghai.cn/features/7400.html", "type": "media"},
    {"title": "携程笔记 - 原火炭烤真的香", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=56085163", "type": "ugc"},
    {"title": "携程笔记 - 王嘉尔同款暗黑Bistro", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=325369899", "type": "ugc"},
    {"title": "Trip.com - Hide the Smoked Room", "url": "https://us.trip.com/restaurant/china/shanghai/detail/restaurant-143238914/", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "Hide the Smoked Room藏在黑石公寓3幢二楼，按门牌上红色i按钮才开门，是米其林二星团队背景厨师长主理的亚洲原火炭烤融合餐酒馆。食客实测，烟熏梅菜黑猪肋排是头牌：云南黑猪猪肋排经15年花雕酒低温慢煮再果木高温炭烤，配原汤梅干菜，肉质松软入味；贵州糟粕汁炸鱼鱼鳞脆如薯片、鱼肉锁汁，糟粕汁类似冬阴功的鲜酸；中华烤鸡翅表皮焦甜、咬开爆汁、烟熏克制；花椒火焰竹蛏王、云南素番茄配布拉塔、烤西兰苔刷寄居蟹酱也是常客必点。横向上，它的菜有真功夫，但21点后大厅转水烟lounge、王嘉尔打卡后网红属性强，更像氛围感晚餐+微醺而非纯粹Fine Dining；营业到凌晨3点是差异化卖点。",
  "notes": "电话未取得可靠直线，留空。"
})

# 10. EIGHT UNDER (八eight)
rows.append({
  "name": "EIGHT UNDER", "name_en": "UNDER at EIGHT", "district": "徐汇区",
  "address": "徐汇区永康路73号(近嘉善路)",
  "price_avg": 888, "price_range": "楼下UNDER 8座chef's table品鉴888/位；楼上CANTINA散点",
  "price_sources": [{"platform": "SmartShanghai", "value": 888, "url": "https://www.smartshanghai.com/articles/dining/shanghai-s-best-chef-s-tables-and-how-much-they-cost"},
                    {"platform": "Nomfluence", "value": 888, "url": "https://rachelgouk.com/the-shanghai-scoop-food-drink-news-may-2026/"}],
  "signature_dishes": ["鹅肝鳗鱼Tapas叠萝卜糕", "球形玉子烧裹火腿半流心", "麻酱油泼辣子意面", "桂花康普茶", "蟹沙拉咸churros", "鸭cannelloni担担酱"],
  "cuisine_paths": [["西餐", "融合菜"], ["中餐", "融合菜"]], "form": "私宴会所", "meals": ["晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
  "phone_raw": None, "booking_method": "预约制，楼下8座chef's table，楼上CANTINA散点",
  "brand_group": "Chef Gabo", "brand_confirmed": True, "scene": "Chifané融合chef's table",
  "special_tags": ["chef's table", "8座"], "lat": None, "lng": None,
  "scores": {"objective": 66, "diner": 78, "taste": 80, "endorsement": 70, "soft_ad_penalty": 0, "platform_credibility": 0.78},
  "evidence": {
    "diner_quotes": [
      {"quote": "餐厅名字就是八，套餐888一位一共八道菜。一个架在刀上的Tapas，鹅肝和鳗鱼下面叠的是中式萝卜糕。鸭子把里面鸡给kill了，鸡里面有龙虾还有公婆虾，完全无厘头但很好吃。", "dish": "鹅肝鳗鱼Tapas/鸭包鸡", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7645310594514511525", "date": "2026-05-29"},
      {"quote": "玉子烧做成球形裹上火腿，中间是半流心蛋液，芹菜的清香很巧妙地化解了蛋腥味，不吃芹菜的朋友也觉得好吃。意面是麻酱加上油泼辣子，就是万万岁。他家的桂花康普茶也要推荐，冰爽解腻。", "dish": "球形玉子烧/麻酱油泼辣子意面", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7671623676143357218", "date": "2026-08-08"}
    ],
    "platform_scores": [
      {"platform": "SmartShanghai(推荐)", "score": None, "review_count": None, "url": "https://www.smartshanghai.com/articles/dining/shanghai-s-best-chef-s-tables-and-how-much-they-cost"}
    ],
    "negative_signals": ["楼下8座极难订", "楼上楼下两个概念易混", "Chifané风味混沌，爱者极爱、不合者皱眉"],
    "soft_ad_flags": [],
    "traffic_signals": ["Chef Gabo在沪16年，前8 by Anarkia主理人", "工厂风装修+中式元素"]
  },
  "sources": [
    {"title": "SmartShanghai - Shanghai's Best Chef's Tables", "url": "https://www.smartshanghai.com/articles/dining/shanghai-s-best-chef-s-tables-and-how-much-they-cost", "type": "media"},
    {"title": "Nomfluence - EIGHT by Chef Gabo Yongkang Lu", "url": "https://rachelgouk.com/the-shanghai-scoop-food-drink-news-may-2026/", "type": "media"},
    {"title": "抖音食客 - 八eight约会餐厅", "url": "https://www.iesdouyin.com/share/video/7645310594514511525", "type": "ugc"},
    {"title": "抖音食客 - 上海top难约的男人八eight", "url": "https://www.iesdouyin.com/share/video/7671623676143357218", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "EIGHT(八eight)是委内瑞拉出身、在沪生活16年的主厨Gabo在永康路重启的chef's table，楼下仅8座、套餐888元八道菜，楼上CANTINA做散点小馆。它的料理体系叫Chifané，源自秘鲁中餐Chifa(粤语'食饭')，把中国味觉拆进南美-地中海结构。食客实测：架在刀上的鹅肝鳗鱼Tapas底下叠中式萝卜糕；'鸭包鸡'里还藏着龙虾和公婆虾；球形玉子烧裹火腿、半流心蛋液加芹菜去腥；麻酱油泼辣子意面被称'万万岁'；桂花康普茶解腻。横向上，Gabo是上海融合圈辨识度极高的主厨，混沌而自洽的菜品让老饕反复打卡；但8座极难订、风味极端，不爱融合的食客会觉得无厘头。适合追主厨、爱创意料理的人。",
  "notes": "原名EIGHT UNDER，现多称八eight/EIGHT by Chef Gabo。电话未公开。"
})

# 11. 艾利爵士 Sir Elly's
rows.append({
  "name": "艾利爵士餐厅", "name_en": "Sir Elly's", "district": "黄浦区",
  "address": "黄浦区中山东一路32号上海半岛酒店13楼",
  "price_avg": 1160, "price_range": "人均约1160元",
  "price_sources": [{"platform": "米其林指南", "value": 1160, "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/sir-elly-s"}],
  "signature_dishes": ["手工意面Carbonara配Guanciale海胆", "黑松露可颂", "鸭肝寿司配芒果", "意式馅料烤鸡", "出汁白酱煮笋壳鱼"],
  "cuisine_paths": [["西餐", "意大利菜"]], "form": "Finedining", "meals": ["午餐", "晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "入选", "black_pearl": 0, "source_url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/sir-elly-s"},
  "phone_raw": "021-23276756", "booking_method": "电话021-23276756/半岛订座",
  "brand_group": "半岛酒店集团", "brand_confirmed": True, "scene": "外滩北意高空餐厅",
  "special_tags": ["江景露台", "约会"], "lat": None, "lng": None,
  "scores": {"objective": 76, "diner": 74, "taste": 78, "endorsement": 82, "soft_ad_penalty": 0, "platform_credibility": 0.85},
  "evidence": {
    "diner_quotes": [
      {"quote": "半岛顶楼的米其林餐厅艾利爵士，露台视野开阔，清楚看到对面三件套和外滩。第一道前菜是鸭肝寿司，寿司米上加了芒果，西式做法米粒有点夹生，感觉还是传统寿司更稳妥。", "dish": "鸭肝寿司配芒果", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/6959464930168835368", "date": "2021-05-07"},
      {"quote": "晚上7点步入餐厅，调暗的灯光下窗外陆家嘴和外滩夜景尽收眼底，吃饭时点上蜡烛氛围感拉满。刚入座派送面包品种任选，选了黑松露可颂还是温的，又脆又酥，一口气吃了两个。", "dish": "黑松露可颂", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7208346939526548788", "date": "2023-03-09"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.8, "review_count": None, "url": "https://ph.trip.com/restaurant/china/shanghai/detail/sir-elly-s-restaurant-11153150/"},
      {"platform": "高德", "score": 4.4, "review_count": None, "url": None}
    ],
    "negative_signals": ["露台景观位溢价明显", "鸭肝寿司等融合前菜有食客觉得米粒夹生、不如传统做法", "人均偏高"],
    "soft_ad_flags": [],
    "traffic_signals": ["半岛13楼270度江景露台", "日落/夜景露台位难订"]
  },
  "sources": [
    {"title": "米其林指南 - 艾利爵士餐厅", "url": "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/sir-elly-s", "type": "official_guide"},
    {"title": "半岛酒店官网 - Sir Elly's", "url": "https://www.peninsula.com/zh-cn/shanghai/5-star-luxury-hotel-bund", "type": "brand_official"},
    {"title": "Trip.com - Sir Elly's", "url": "https://ph.trip.com/restaurant/china/shanghai/detail/sir-elly-s-restaurant-11153150/", "type": "ugc"},
    {"title": "抖音食客 - 外滩大露台吃一顿", "url": "https://www.iesdouyin.com/share/video/6959464930168835368", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "艾利爵士Sir Elly's位于外滩半岛酒店13楼，是270度俯瞰黄浦江、苏州河口与浦东天际线的北意餐厅，露台U型视角是其最大卖点。食客实测，派送面包篮里的黑松露可颂温热酥脆、被一口气吃两个；鸭肝寿司作为西式融合前菜配芒果，但有食客觉得寿司米夹生、不如传统做法稳妥。据媒体食评，手工意面Carbonara用风干猪脸肉Guanciale、佩科里诺奶酪加海胆，面条Al Dente；主菜可选出汁白酱煮笋壳鱼、意大利醋烹崇明鸽或意式馅料烤鸡。横向上，它与翡翠36同属高空江景Fine Dining，艾利爵士偏北意、翡翠36偏法式，景观是两者共同的溢价来源；缺点是景观位价格贵、部分融合前菜评价两极。适合纪念日与商务宴请。",
  "notes": "电话为半岛酒店订座。"
})

# 12. 2乙酒馆 (保留记录，UGC不足标记存疑)
rows.append({
  "name": "2乙酒馆", "name_en": "Alley1293", "district": "长宁区",
  "address": "长宁区愚园路1293弄小区内(居民楼)",
  "price_avg": 300, "price_range": "off-menu每日变化，配酒",
  "price_sources": [{"platform": "TimeOut EN/网易", "value": 300, "url": "https://c.m.163.com/news/a/JD106R1R05228HQE.html"}],
  "signature_dishes": ["私藏煲仔饭(云南火腿牛肝菌)", "Vitello Tonnato小牛肉金枪鱼酱", "每日off-menu"],
  "cuisine_paths": [["西餐", "融合菜"], ["中餐", "融合菜"]], "form": "私宴会所", "meals": ["晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
  "phone_raw": "13166091028", "booking_method": "电话预约13166091028，17:30-00:30周二店休",
  "brand_group": "主理人竹马(戏班乐队)", "brand_confirmed": False, "scene": "居民楼off-menu小酒馆",
  "special_tags": ["预约制", "隐藏店"], "lat": None, "lng": None,
  "scores": {"objective": 60, "diner": 62, "taste": 72, "endorsement": 55, "soft_ad_penalty": 0, "platform_credibility": 0.7},
  "evidence": {
    "diner_quotes": [
      {"quote": "这个是云南火腿煲仔饭，又香又烫，里向有股浓浓的西班牙火腿味道，还有云南牛肝菌。这个饭也不是很甜，饭上面酱油做了改良。要吃这个私藏煲仔饭你必须报主理人名字，后台留言没用。", "dish": "云南火腿牛肝菌煲仔饭", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7417318994639703308", "date": "2024-09-22"},
      {"quote": "主理人是戏班乐队班主竹马，把这里打造成私密感十足的第三空间。酒至微醺幸运的客人还能巧遇老板现场即兴solo。Atmospheric dim lighting, off-menu items change daily. Try Bodega Matador red wine with Vitello Tonnato.", "dish": "Vitello Tonnato", "source": "网易/TimeOut", "url": "https://c.m.163.com/news/a/JD106R1R05228HQE.html", "date": "2024-09-26"}
    ],
    "platform_scores": [
      {"platform": "DiningCity", "score": 9.0, "review_count": None, "url": "https://www.diningcity.cn/shanghai/2_alley1293"}
    ],
    "negative_signals": ["居民楼内位置隐蔽难找", "off-menu每日变化不可预知", "电话预约门槛高", "评价基数小"],
    "soft_ad_flags": [],
    "traffic_signals": ["煲仔饭需报主理人名字", "老板即兴live", "下次有位可能等数周"]
  },
  "sources": [
    {"title": "TimeOut EN - 2乙 Tavern", "url": "http://www.timeoutshanghai.com/features/Feature/105570/8-Eateries-in-Shanghai-Where-Reservations-Are-Rather-Necessary.html", "type": "media"},
    {"title": "网易 - 魔都9月漂亮饭2乙酒馆", "url": "https://c.m.163.com/news/a/JD106R1R05228HQE.html", "type": "media"},
    {"title": "抖音 - 2乙酒馆文艺小酒馆", "url": "https://www.iesdouyin.com/share/video/7417318994639703308", "type": "ugc"},
    {"title": "企查查-东腔西调文化传播", "url": "https://www.qcc.com/ccomment/a15dbdda9512aa8271f2b38452ab4cd9", "type": "map"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "2乙酒馆Alley1293藏在长宁区愚园路1293弄居民楼里，是戏班乐队班主'竹马'主理的off-menu小酒馆，电话预约、周二店休。食客实测，招牌私藏煲仔饭要报主理人名字才做得到位：云南火腿与西班牙火腿风味叠加、加云南牛肝菌，酱油做了改良不甜；Vitello Tonnato小牛肉配金枪鱼酱配Bodega Matador红酒是常驻搭配。店里灯光昏暗私密，酒至微醺可能遇上老板现场即兴solo。横向上，它走的是熟人社会、第三空间路线，菜单每日off-menu、不可预知；缺点是位置隐蔽、预约门槛高、公开食客评价基数小，第二人视角的真实堂食原话仍需补证。适合熟客带新客。",
  "notes": "存疑：真实食客UGC原话目前仅抖音1条(煲仔饭)，第二条为媒体稿(网易/TimeOut)，需真人补第二条自费堂食UGC。工商主体=东腔西调(上海)文化传播。"
})

# 13. Tuttu
rows.append({
  "name": "Tuttu", "name_en": "Tuttu", "district": "静安区",
  "address": "静安区延平路(近胶州路，夜间营业，红色招牌，预约告知具体门牌)",
  "price_avg": 300, "price_range": "融合意餐小馆，人均约300元",
  "price_sources": [{"platform": "抖音", "value": 300, "url": "https://www.iesdouyin.com/share/video/7683929221689008497"}],
  "signature_dishes": ["XO酱炒蚬子", "野生虎虾冷食盘", "和牛薄片(酸辣)", "熟成烤鸡", "意式低温慢炖牛筋"],
  "cuisine_paths": [["西餐", "意餐"]], "form": "Bistro", "meals": ["晚餐"],
  "status": "open", "closed_date": None, "closed_source": None,
  "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
  "phone_raw": None, "booking_method": "预约制，17:00开始营业",
  "brand_group": "主厨Giorgio.Woo", "brand_confirmed": False, "scene": "融合意式小馆Bistro",
  "special_tags": ["夜间小馆"], "lat": None, "lng": None,
  "scores": {"objective": 55, "diner": 68, "taste": 74, "endorsement": 55, "soft_ad_penalty": 3, "platform_credibility": 0.7},
  "evidence": {
    "diner_quotes": [
      {"quote": "主厨Giorgio.Woo从意大利ICIF学院到日本惠比寿名店进修，把意大利传统技法结合本地时令食材。这道XO酱炒蚬子，意式海鲜做法融合中式XO酱，鲜度直接拉满。野生虎虾冷食盘也不错。", "dish": "XO酱炒蚬子/虎虾冷食盘", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7683929221689008497", "date": "2026-09-10"},
      {"quote": "第一道和牛薄片分量不一般，调味酸辣酸辣的，意大利南部菜很像中餐。还点了熟成烤鸡，鸡皮脆脆鸡肉又多汁。老板做酱汁很有一套，很对胃口。上面的巧克力珠珠脆也喜欢。", "dish": "和牛薄片/熟成烤鸡", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7622230741578121626", "date": "2026-03-28"}
    ],
    "platform_scores": [
      {"platform": "抖音", "score": 4.6, "review_count": None, "url": "https://www.iesdouyin.com/share/video/7683929221689008497"}
    ],
    "negative_signals": ["地址仅夜间可见、不公开具体门牌", "新店公开评价基数小", "酱汁风格见仁见智"],
    "soft_ad_flags": ["部分抖音视频偏氛围种草"],
    "traffic_signals": ["延平路夜间红色招牌", "主厨ICIF+日本进修背景"]
  },
  "sources": [
    {"title": "抖音 - Tuttu意式小馆Giorgio.Woo", "url": "https://www.iesdouyin.com/share/video/7683929221689008497", "type": "ugc"},
    {"title": "抖音 - 周末打卡Tuttu延平路", "url": "https://www.iesdouyin.com/share/video/7682015980004840613", "type": "ugc"}
  ],
  "data_updated_at": "2026-09-24",
  "evidence_summary": "Tuttu是主厨Giorgio.Woo在延平路开出的融合意式小馆，傍晚5点亮起红色招牌营业。主厨履历为意大利ICIF餐饮学院、日本惠比寿老牌名店进修，此前参与筹备的餐厅拿过Tatler苏州最佳餐厅。食客实测，XO酱炒蚬子把意式海鲜做法与中式XO酱结合、鲜度拉满；野生虎虾冷食盘清爽；和牛薄片走酸辣路线，像意大利南部菜；熟成烤鸡鸡皮脆、肉多汁，被评价'老板做酱汁很有一套'；收尾巧克力珠珠脆讨喜。横向上，它走的是小而 intimate 的夜间Bistro路线，用意大利技法重组本地时令与中式调味，人均三百在融合意餐里属亲民档；缺点是具体门牌不公开、依赖预约，公开评价基数小，平台分与媒体背书尚缺。适合约会与小聚。",
  "notes": "存疑：sources目前仅抖音UGC一类，缺官方指南/媒体/地图第二来源；具体门牌与直线电话未公开。district按食客所述延平路(近胶州路)修正为静安区。"
})

path = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/_deep/shard1_deep.jsonl")
path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
print("written", len(rows), "rows to", path)
