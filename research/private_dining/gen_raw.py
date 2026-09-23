#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Slice B 私房菜/私宴 raw_private_dining.jsonl"""
import json, pathlib

OUT = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/private_dining/raw_private_dining.jsonl")
TODAY = "2026-09-23"

rows = []

# 1. Cheeva Thai
rows.append({
  "name": "Cheeva Thai",
  "name_en": "Cheeva Thai",
  "district": "徐汇区",
  "address": "上海市徐汇区永福路125号永福里3号楼3楼302号",
  "price_avg": 1280,
  "price_range": "套餐1280元/人起(4人起订)；香槟晚宴2588元/人",
  "cuisine_paths": [["亚洲菜", "泰国菜"]],
  "form": "私宴会所",
  "signature_dishes": ["打抛罗勒牛肉", "冬阴功虾汤", "马沙曼咖喱", "芒果糯米饭", "木姜子烤鱼"],
  "phone_raw": "18964184568",
  "booking_method": "电话/微信预约，4人起订，包厢定金2000元，提前数月预约；不接待16岁以下儿童",
  "status": "open",
  "awards": {"michelin": "无", "black_pearl": 0, "source_url": None},
  "price_sources": [{"platform": "网易携程黑钻", "value": 1280, "url": "https://c.m.163.com/news/a/KROUFB8H0522DVT9.html"}],
  "evidence_summary": "Cheeva Thai 起源于疫情期间老板临时开的一桌泰国家庭厨房，因全城爆火搬入永福路永福里三层小洋楼，是上海公认最难预约的泰国私房菜，食客称'想吃要提前半年预约'。定位为包厢制泰式私宴，4人起订、不接待16岁以下儿童，套餐1280元/人起、包厢定金2000元。主厨沿用泰国本土做法，打抛罗勒牛肉香气细腻，冬阴功虾汤汤底浸透虾肉；食客对马沙曼咖喱评价两极，认为主菜咖喱偏重、香料味未必人人适应。环境为法式洋房混搭泰式花艺陈设，适合拍照。Trip.com 仅6条评论却打出4.8分，评论样本过少可信度需打折；另有槟客文化联合举办2588元/人香槟晚宴。",
  "evidence": {
    "diner_quotes": [
      {"quote": "This must be the hardest Thai restaurant in Shanghai to book... My favorite is the basil beef, with its delicate aroma. The Tom Yum soup with prawns is so satisfying, the broth soaks into the prawn meat, one bite is pure bliss.", "source": "Trip.com", "url": "https://sg.trip.com/restaurant/china/shanghai/detail/cheeva-thai-126184677/", "date": "2026-04-21"},
      {"quote": "The appetizers are meticulously prepared, but the main courses rely heavily on curry. The Masamum curry's spice flavor might not be to everyone's liking. They could adjust the curry mix and explore the true essence of Thai cuisine.", "source": "Trip.com", "url": "https://sg.trip.com/restaurant/china/shanghai/detail/cheeva-thai-126184677/", "date": "2026-04-21"},
      {"quote": "Cheeva thai是上海最火爆的泰国菜没有之一。据说老板本来没想开餐厅，是受到疫情影响，凑巧开了家只能接待一桌的私房菜，没想到全城爆火，想吃得提前半年预约。因为生意实在太好，他们找了更大的地方装修开了新店。", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=84533142", "date": "2024-09-24"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.8, "review_count": 6, "url": "https://sg.trip.com/restaurant/china/shanghai/detail/cheeva-thai-126184677/"}
    ],
    "negative_signals": ["评论仅6条却4.8分，样本过少可信度≤0.7", "食客反馈主菜过度依赖咖喱，马沙曼咖喱香料味不合众口", "4人起订+2000定金门槛高，不接待散客与儿童"],
    "soft_ad_flags": ["携程黑钻WOW礼遇抢购渠道有导流嫌疑"],
    "traffic_signals": ["提前半年预约仍一位难求", "疫情期间从一桌家庭厨房爆火扩店", "香槟晚宴11席秒光"]
  },
  "sources": [
    {"title": "Cheeva Thai - Trip.com", "url": "https://sg.trip.com/restaurant/china/shanghai/detail/cheeva-thai-126184677/", "type": "ugc"},
    {"title": "携程笔记-Cheeva Thai上海最难约泰国私房菜", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=84533142", "type": "ugc"},
    {"title": "槟客文化-Cheeva Thai香槟晚宴", "url": "http://www.sparklingplus.com/index.php/6f6bad85a1/", "type": "brand"},
    {"title": "网易-携程黑钻难订餐厅Cheeva Thai预订信息", "url": "https://c.m.163.com/news/a/KROUFB8H0522DVT9.html", "type": "media"}
  ],
  "scores": {"objective": 70, "diner": 72, "taste": 80, "endorsement": 72, "soft_ad_penalty": 5, "platform_credibility": 0.7},
  "data_updated_at": TODAY,
  "notes": "起源一桌私房菜的泰餐私宴，与 Slice A authority 片重叠采集，已独立取证。坐标留空待腾讯拾取。"
})

# 2. 聪菜馆
rows.append({
  "name": "聪菜馆",
  "district": "黄浦区",
  "address": "上海市黄浦区六合路158号六合大厦1楼(近第一百货)",
  "price_avg": 268,
  "cuisine_paths": [["中餐", "本帮菜"]],
  "form": "私宴会所",
  "signature_dishes": ["葱姜蒸比目鱼", "招牌炒鳝糊", "虾酱茭白丝", "青鱼秃肺", "招牌醉鸡", "藤椒白水鱼"],
  "phone_raw": "02163335531",
  "booking_method": "电话预约，包房需提前订",
  "status": "open",
  "awards": {"michelin": "必比登", "black_pearl": 0, "source_url": "https://guide.michelin.com/sg/zh_CN/shanghai-municipality/shanghai/restaurant/cong-s-kitchen"},
  "evidence_summary": "聪菜馆是米其林必比登推介(2024/2025)的本帮菜馆，藏在黄浦区六合路158号六合大厦一楼，老板聪叔亲自掌勺并到包房寒暄，讲究食材选择与火候控制，坚持本帮原汁原味。招牌包括葱姜蒸比目鱼、招牌炒鳝糊、虾酱茭白丝、青鱼秃肺(几近失传的本帮经典)、招牌醉鸡、藤椒白水鱼等。食客评价清炖牛肉、虾酱茭白丝、荠菜馄饨百吃不厌，青鱼秃肺让人对本帮菜有更高层次认识。人均约268元，兼具家常菜的亲切与私房菜的精细，适合家庭聚餐与团体聚会。注意英文站 joinpearl/EnPrimeurClub 写地址为浦东民生路480号，与米其林官方及电话邦的六合路158号不一致，疑为搬迁前地址或另设分店，正名地址以米其林官方为准。",
  "evidence": {
    "diner_quotes": [
      {"quote": "在这里，你可以品尝到味道最惊艳的家常菜，清炖牛肉、虾酱茭白丝甚至是荠菜馄饨都令人百吃不厌，还可品尝到几近失传的经典本帮菜——青鱼秃肺，让你对上海本帮菜有更高层次的认识。", "source": "穷游网", "url": "https://m.qyer.com/place/poi/V2UJZVFlBzFTYFI3Cms/", "date": "2026-09-13"},
      {"quote": "位于六合路158号的临街店面，门口就是路侧公共停车位，下车直接进店。家人聚餐定了一个包房，落座点好菜，一位爷叔径直向门里走来，以为是旁边房间的客人认错门了，结果是老板过来关照，聪叔本尊，浅聊了几句，感觉聪叔还是有点派头的。", "source": "微博", "url": "https://www.sina.cn/media/5539501154", "date": "2026-09-21"}
    ],
    "platform_scores": [
      {"platform": "米其林指南", "score": 4.0, "review_count": None, "url": "https://guide.michelin.com/sg/zh_CN/shanghai-municipality/shanghai/restaurant/cong-s-kitchen"},
      {"platform": "携程(人均)", "score": None, "review_count": None, "url": "https://you.ctrip.com/food/shanghai2/12647819.html"}
    ],
    "negative_signals": ["英文源(joinpearl/EnPrimeurClub)地址写民生路480号浦东，与官方六合路158号冲突，疑搬迁/分店待核", "临街店非纯无门头私宴，私宴属性偏会馆包房"],
    "soft_ad_flags": [],
    "traffic_signals": ["米其林必比登连续推介", "聪叔本人到包房寒暄，老客带新客"]
  },
  "sources": [
    {"title": "聪菜馆-米其林指南", "url": "https://guide.michelin.com/sg/zh_CN/shanghai-municipality/shanghai/restaurant/cong-s-kitchen", "type": "official_guide"},
    {"title": "聪菜馆-穷游美食攻略", "url": "https://m.qyer.com/place/poi/V2UJZVFlBzFTYFI3Cms/", "type": "ugc"},
    {"title": "电话邦-聪菜馆", "url": "https://www.dianhua.cn/dt/44a5d06b5f1c4f138ca79ba55b98bcf/e7c6aa36e4b3fd71178615ef86c20d7e", "type": "map"},
    {"title": "微博-聪菜馆六合大厦店", "url": "https://www.sina.cn/media/5539501154", "type": "ugc"}
  ],
  "scores": {"objective": 75, "diner": 78, "taste": 82, "endorsement": 80, "soft_ad_penalty": 0, "platform_credibility": 0.9},
  "data_updated_at": TODAY,
  "notes": "回归用例(聪菜馆)。地址冲突：米其林官方+电话邦+携程=六合路158号；joinpearl/EnPrimeurClub=民生路480号。正名取六合路，冲突待人工核。"
})

# 3. 豪生酒家
rows.append({
  "name": "豪生酒家",
  "district": "徐汇区",
  "address": "上海市徐汇区广元路156号(近天平路)",
  "price_avg": 150,
  "price_range": "100/150/200三档配菜",
  "cuisine_paths": [["中餐", "本帮菜"]],
  "form": "私宴会所",
  "signature_dishes": ["花雕糟鸡", "清蒸鱼", "本帮红烧肉", "干烧明虾", "白切猪肝", "八宝辣酱"],
  "phone_raw": "02162826446",
  "booking_method": "电话提前一周预约，无菜单按所选餐标配菜，约不上不接待",
  "status": "open",
  "awards": {"michelin": "必比登", "black_pearl": 0, "source_url": "https://guide.michelin.com/my/en/shanghai-municipality/shanghai/restaurant/hao-sheng"},
  "evidence_summary": "豪生酒家藏在徐汇广元路156号弄堂里，1997年开业，是上海最著名的本帮omakase——没有固定菜单，老板(一位山东籍鲁姓爷叔)每天去菜场采购，按客人所选100/150/200三档餐标配菜，上什么吃什么。整个餐厅仅5张桌、老板一人身兼厨师与服务员，需提前一周电话预约，约不上不接待。连续多年入选米其林必比登(2024/2025)。出品偏清淡家烧，浓油赤酱但不过分，花雕糟鸡用花雕级好酒、酒味把控恰到好处，另有清蒸鱼、红烧肉、干烧明虾、白切猪肝、八宝辣酱等家常本味。食客称'有妈妈的味道'，装潢低调像回家吃饭。",
  "evidence": {
    "diner_quotes": [
      {"quote": "到这来吃饭得提前一个礼拜预订，并且吃什么喝什么你自己说了不算，老板上什么你吃什么，妥妥一个上海本帮菜的omakase。米其林2005年起推荐，进来一共5张桌，一个人五张桌，连续7年米其林推荐，关键整个餐厅就一个人，厨师服务员都是阿叔。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7598384902741087601", "date": "2026-01-23"},
      {"quote": "他的菜就是100、150、200三个餐标，没有菜单，只要告诉老板我要吃150块钱的，一个人然后他就帮你配菜。这家本帮菜来吃过的上海人都觉得有妈妈的味道，虽然也算是浓油赤酱，但是就比较稍微清淡一点。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7517517873775447354", "date": "2025-06-19"},
      {"quote": "一到夏天，就想起豪生的这一盘糟鸡，用的是花雕级别的好酒，酒味把控的恰到好处，入口就有酒的清香，又有鸡肉的鲜香。不能点菜，按照所能承受的人均配菜。", "source": "上海热线", "url": "https://t.online.sh.cn/hi/content/2019-07/18/content_9339800_9.htm", "date": "2019-07-18"}
    ],
    "platform_scores": [
      {"platform": "高德地图", "score": 4.6, "review_count": None, "url": None},
      {"platform": "城市吧(人均)", "score": None, "review_count": None, "url": "https://sh.city8.com/cater/8d9k9c794emub89fd4"}
    ],
    "negative_signals": ["需提前一周且约不上不接待，门槛高", "一人经营5桌，出品节奏慢、量小", "无菜单无法指定菜品，众口难调"],
    "soft_ad_flags": [],
    "traffic_signals": ["连续7年米其林必比登推荐", "一人5桌仍不扩张", "老客带新客熟客制"]
  },
  "sources": [
    {"title": "Hao Sheng-米其林指南", "url": "https://guide.michelin.com/my/en/shanghai-municipality/shanghai/restaurant/hao-sheng", "type": "official_guide"},
    {"title": "抖音-最孤独的米其林豪生酒家", "url": "https://www.iesdouyin.com/share/video/7598384902741087601", "type": "ugc"},
    {"title": "上海热线-本帮菜寻味指南豪生酒家", "url": "https://t.online.sh.cn/hi/content/2019-07/18/content_9339800_9.htm", "type": "media"},
    {"title": "城市吧-豪生酒家地址电话", "url": "https://sh.city8.com/cater/8d9k9c794emub89fd4", "type": "map"}
  ],
  "scores": {"objective": 78, "diner": 85, "taste": 85, "endorsement": 82, "soft_ad_penalty": 0, "platform_credibility": 0.9},
  "data_updated_at": TODAY,
  "notes": "回归用例。本帮omakase标杆，老板鲁姓一人经营。高德坐标121.439812,31.199198(GCJ02)留空待stage2。"
})

# 4. 黄公子
rows.append({
  "name": "黄公子",
  "district": "徐汇区",
  "address": "上海市徐汇区天平路320弄21号1-2层(衡山坊内)",
  "price_avg": 3000,
  "cuisine_paths": [["中餐", "融合菜"]],
  "form": "私宴会所",
  "signature_dishes": ["雪蟹炖蛋配海鲜泡沫", "伊比利亚火腿坚果色拉", "黑松露鲍鱼红烧肉"],
  "phone_raw": "15316869328",
  "booking_method": "电话预约，每日仅两席，两层小洋房各一桌，无固定菜单按时令及客人口味安排",
  "status": "open",
  "evidence_summary": "黄公子是沪上顶级私房菜代表，藏在徐家汇后花园衡山坊天平路320弄一栋两层小洋房内，低调招牌与绿植掩映，另设通往二楼的隐蔽北门，每日仅限两席、两层客人互不打扰。一楼欧式复古装潢如欧洲古堡，二楼侘寂风配艺术家孙尧《影之痕》系列画作，满屋子当代艺术私藏，皇室品牌烛台餐具。私宴无固定菜单，由主厨按时令及客人偏好安排，从前菜色拉汤品刺身到主菜主食甜品多道式：冬日雪蟹炖蛋配海鲜泡沫暖胃、伊比利亚火腿坚果色拉脂香迷人、黑松露鲍鱼红烧肉丰腴Q弹。人均3000元起入场券，5000元/位套餐，连劳斯莱斯也曾在此连摆6场。食客称8人包场花4万还另收10%服务费。",
  "evidence": {
    "diner_quotes": [
      {"quote": "在魔都混了这么多年，本吃货终于打卡了传说中的黄公子私房菜！藏在徐家汇天平路的小洋房里，一进门就感受到什么叫低调奢华有内涵。作为沪上顶级私房菜代表，菜单根据时令调整，环境是复古风小洋房，每桌都是独立包间，服务员全程安静贴心。8个人花了4万多包场。", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=176410179", "date": "2025-07-27"},
      {"quote": "花4万都不够，还要另收10%的服务费。包场上海这家9年来始终最难约、人均最高的私房菜天花板，每晚只接待两桌，人均3000只是入场券，连劳斯莱斯也在这连摆过6场。定制私宴，满屋子的当代艺术私藏。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7531224043119349034", "date": "2025-07-26"}
    ],
    "platform_scores": [
      {"platform": "TimeOut上海推荐", "score": None, "review_count": None, "url": "https://www.timeoutshanghai.cn/features/6238.html"}
    ],
    "negative_signals": ["人均3000入场券+10%服务费，性价比争议大", "每晚仅两席，预约难度极高", "5k套餐被部分食客认为'吃环境大于吃味道'"],
    "soft_ad_flags": ["劳斯莱斯摆场等高端营销事件易显炒作"],
    "traffic_signals": ["9年始终最难约私宴", "每晚两席仍一位难求", "当代艺术私藏空间成为社交货币"]
  },
  "sources": [
    {"title": "TimeOut上海-年终私宴黄公子", "url": "https://www.timeoutshanghai.cn/features/6238.html", "type": "media"},
    {"title": "携程笔记-黄公子包场", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=176410179", "type": "ugc"},
    {"title": "抖音-上海最贵最难约私房菜黄公子", "url": "https://www.iesdouyin.com/share/video/7531224043119349034", "type": "ugc"}
  ],
  "scores": {"objective": 72, "diner": 75, "taste": 80, "endorsement": 85, "soft_ad_penalty": 8, "platform_credibility": 0.85},
  "data_updated_at": TODAY,
  "notes": "回归用例。高端融合私宴，TimeOut背书。价格锚点3000-5000/人。"
})

# 5. AmoyA
rows.append({
  "name": "AmoyA",
  "name_en": "AmoyA",
  "district": "徐汇区",
  "address": "上海市徐汇区长乐路长乐村里弄(无招牌，预约告知，需敲门找号)",
  "price_avg": 1500,
  "cuisine_paths": [["中餐", "闽菜", "厦门菜"]],
  "form": "私宴会所",
  "signature_dishes": ["鱼子酱水蜜桃", "老香黄海胆塔", "盐焗河田鸡(含花胶公)", "厦门润饼", "玫瑰龙虾啫啫"],
  "phone_raw": None,
  "booking_method": "微信/熟客介绍预约，每天只开一桌一顿，主厨不露脸，无菜单，月开约10天",
  "status": "open",
  "evidence_summary": "AmoyA(Amoy即厦门的闽南语音)是2026年上海私房菜圈最强黑马，藏在长乐村长乐村里弄联排中，连招牌都没有，要一户户敲门找过去。以福建沿海食材为基底、加广西云南沿海风味，每天只做一桌、一顿饭，主厨全员不露脸，人均1500元。开篇是龙泉驿水蜜桃配鱼子酱的开胃菜，老香黄海胆塔，福建泉州龙湖鳖，广西北海刀贝，弄堂版蚝&牛，玫瑰龙虾啫啫，压轴盐焗福建河田鸡焗了四个多钟头、鸡肚里塞整条花胶公、配盐焗鸡饭，收尾厦门润饼与漳州水果。食客称刚开就订到10月，月开仅10天、只接待朋友熟客，做研发展示功能。",
  "evidence": {
    "diner_quotes": [
      {"quote": "每天只开一桌1500块的私房菜，这个餐厅连招牌都没有，开在里弄联排里，一户一户找过去。Amoy念出来就是厦门的意思，是以福建菜为基底加沿海地区食材。里面只有一桌，每天只做一顿，厨师全员不露脸。压轴盐焗福建河田鸡焗了四个多钟头，鸡肚子里加了整条花胶公，盐焗出来汁水像熬了一锅鸡汤。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7658165141149650226", "date": "2026-07-03"},
      {"quote": "在闹中取静的长乐村，最近冒出一个神龙见首不见尾的空间，只接待自己的朋友们，只做研发和展示，菜肴主题是厦门菜在上海的融合，所以就叫amoy。用自家发酵的康普茶和龙泉驿水蜜桃鱼子酱组合的开胃前菜。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7654869929824827337", "date": "2026-06-24"}
    ],
    "platform_scores": [
      {"platform": "抖音探店", "score": None, "review_count": None, "url": "https://www.iesdouyin.com/share/video/7658165141149650226"}
    ],
    "negative_signals": ["新店(2026年)无公开平台分与评论样本", "无招牌无电话，纯熟客微信预约，普通食客难以触达", "主厨不露脸、无固定菜单，出品稳定性待观察"],
    "soft_ad_flags": ["抖音探店集中轰炸'最强黑马'，新店营销味需警惕"],
    "traffic_signals": ["刚开即订到10月", "月开仅10天熟客制", "长乐村神龙见首不见尾空间"]
  },
  "sources": [
    {"title": "抖音-每天只开一桌AmoyA私房菜", "url": "https://www.iesdouyin.com/share/video/7658165141149650226", "type": "ugc"},
    {"title": "抖音-长乐村熟客制amoy厦门菜", "url": "https://www.iesdouyin.com/share/video/7654869929824827337", "type": "ugc"},
    {"title": "百度地图-AmoyA私房菜POI(待真人核精确楼栋)", "url": "https://map.baidu.com/search/AmoyA%E7%A7%81%E6%88%BF%E8%8F%9C", "type": "map"}
  ],
  "scores": {"objective": 55, "diner": 70, "taste": 78, "endorsement": 60, "soft_ad_penalty": 8, "platform_credibility": 0.7},
  "data_updated_at": TODAY,
  "notes": "回归用例。2026新黑马，无门牌电话，坐标与精确楼栋待真人到店补。UGC仅抖音两条，平台分缺失，可信度待观察。"
})

# 6. 来去Laichill
rows.append({
  "name": "来去Laichill",
  "name_en": "Laichill Benbang Jiaoshao Bistro",
  "district": "徐汇区",
  "address": "上海市徐汇区五原路281弄4号一楼(老洋房居民楼内)",
  "price_avg": 298,
  "price_range": "298元/位配餐制(含一杯酒水饮料)",
  "cuisine_paths": [["中餐", "本帮菜"]],
  "form": "私宴会所",
  "signature_dishes": ["腐乳红烧肉", "响油鳝丝", "剁椒鮰鱼煲", "油爆虾", "百叶包", "狮子头"],
  "phone_raw": None,
  "booking_method": "预约制(微信)，不能点菜按人数配本帮家烧，含一杯酒水饮料",
  "status": "open",
  "evidence_summary": "来去Laichill藏在五原路281弄一栋老洋房居民楼一楼，穿过小巷找到4号门进去是个小院子，用餐区仅3-4桌，复古气息浓郁。走配餐制，不能点菜，人均298元含一杯酒水或饮料，按两人量上七八道冷菜热菜，店家随人数与口味调整分量，主打甜甜的本帮家烧口味。食客推荐腐乳红烧肉软糯入味甜咸交织，响油鳝丝热油浇淋香气扑鼻、鳝丝滑嫩弹牙，剁椒鮰鱼煲鲜辣开胃、鱼肉嫩到入口即化，油爆虾外壳酥脆内里鲜嫩，另有百叶包、狮子头。距地铁10号线上海图书馆站步行约900米，是梧桐区居民楼里的宝藏本帮小馆。注意与五原路312弄另一家'厨子变乐手'私房馆为不同店。",
  "evidence": {
    "diner_quotes": [
      {"quote": "这里不能点菜，人均是298元，包含一杯酒水或是饮料，其他全是配菜，菜品是本帮口味甜甜的很家常。按两个人的量一共上了七八道菜，冷菜热菜都有。油爆虾、百叶包、狮子头、红烧肉都是小时候记忆里的味道。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7672755070039820722", "date": "2026-08-11"},
      {"quote": "腐乳红烧肉软糯入味，甜咸交织的口感超地道；响油鳝丝热油浇淋的瞬间香气扑鼻，鳝丝滑嫩弹牙；剁椒鮰鱼煲鲜辣开胃，鱼肉嫩到入口即化，油爆虾更是外壳酥脆内里鲜嫩，每一道都是正宗的本帮味道。", "source": "Trip.com", "url": "https://hk.trip.com/moments/detail/shanghai-2-139700499/", "date": "2025-12-23"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 5.0, "review_count": None, "url": "https://hk.trip.com/moments/detail/shanghai-2-139700499/"}
    ],
    "negative_signals": ["仅3-4桌，周末预约紧张", "配餐制不能点菜，忌口需提前沟通", "居民楼内停车不便"],
    "soft_ad_flags": [],
    "traffic_signals": ["梧桐区老洋房小馆，本地年轻食客收藏", "配餐制回头客"]
  },
  "sources": [
    {"title": "抖音-来去Laichill五原路老洋房配餐", "url": "https://www.iesdouyin.com/share/video/7672755070039820722", "type": "ugc"},
    {"title": "Trip.com-来去Laichill本帮家烧", "url": "https://hk.trip.com/moments/detail/shanghai-2-139700499/", "type": "ugc"},
    {"title": "百度地图-来去Laichill五原路POI(待真人核门牌)", "url": "https://map.baidu.com/search/%E6%9D%A5%E5%8E%BBLaichill", "type": "map"}
  ],
  "scores": {"objective": 68, "diner": 78, "taste": 78, "endorsement": 55, "soft_ad_penalty": 3, "platform_credibility": 0.8},
  "data_updated_at": TODAY,
  "notes": "与五原路312弄'厨子变乐手live私房馆'为两家不同店，勿混。电话宁空。"
})

# 7. 作故私房菜
rows.append({
  "name": "作故私房菜",
  "district": "长宁区",
  "address": "上海市长宁区番禺路与番禺路222弄交叉口西南40米(湖南路商圈)",
  "price_avg": 298,
  "cuisine_paths": [["中餐", "融合菜"]],
  "form": "私宴会所",
  "signature_dishes": ["红乳牛肝菌牛骨髓拌饭", "鸡油菌菌汤饭", "紫苏桃子配自制康普茶", "解构水果蛋糕"],
  "phone_raw": None,
  "booking_method": "预约制主厨餐桌，可选wine pairing",
  "status": "open",
  "evidence_summary": "作故私房菜藏在长宁番禺路居民楼里，是2025年走红的百元档中式omakase主厨餐桌，人均298元。菜单按月时令轮换，食客评价红乳牛肝菌与牛骨髓拌饭端上来香气炸裂、菌香与骨髓完美交融舍不得剩一粒饭；鸡油菌表面滑滑油润，菌汤吸入米饭鲜味爆炸；收尾紫苏桃子配自制康普茶，整套流程像有节奏的中餐交响乐。最后以'只有蛋糕内容没有蛋糕造型'的解构水果蛋糕结束。可选wine pairing搭配惊喜。老板立志在298价位做到顶，被许多食客当作'沪漂小食堂'，适合对私厨感兴趣又怕破费的人初体验。",
  "evidence": {
    "diner_quotes": [
      {"quote": "红乳牛肝菌与牛骨髓拌饭端上来香气炸裂，菌香和骨髓完美交融，完全舍不得剩下任何一粒饭。吃到最后再来一份紫苏桃子加自制康普茶，整个流程下来舒服又满足，像是吃了一顿有节奏的中餐交响乐。整套吃完只要298元，这价格在魔都性价比直接拉满。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7527503292918680842", "date": "2025-07-16"},
      {"quote": "菌汤吸入米饭当中，鲜味爆炸，鸡油菌表面滑滑的油润润的，带动了这碗米饭的香气，太好吃了。298的价格体验私厨漂亮饭，在上海这么卷的餐饮市场，用高性价比的价格回馈食客。", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=184582560", "date": "2025-08-14"},
      {"quote": "最后吃上一口只有蛋糕内容、没有蛋糕造型的解构水果蛋糕结束这场演出。对于普通人来说如此的风味和仪式已经不仅仅是一顿饭，它是一场围绕食物的沉浸式表演。作故私房菜，上海长宁区番禺路，一人份298。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7619226577645096201", "date": "2026-03-20"}
    ],
    "platform_scores": [
      {"platform": "携程(标签)", "score": None, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=184582560"}
    ],
    "negative_signals": ["人均298价位被部分老饕认为'表演大于菜品'", "居民楼内位置隐蔽", "主厨轮换(番禺路为主厨中转站)出品稳定性波动"],
    "soft_ad_flags": ["抖音/博主集中推荐'百元档无对手'，注意自卖自夸"],
    "traffic_signals": ["被称为沪漂小食堂每月复购", "298高性价比自带传播", "wine pairing选项受关注"]
  },
  "sources": [
    {"title": "抖音-居民楼里中式omakase作故", "url": "https://www.iesdouyin.com/share/video/7527503292918680842", "type": "ugc"},
    {"title": "携程笔记-作故私房菜", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=184582560", "type": "ugc"},
    {"title": "B站-百元档私厨作故", "url": "https://www.bilibili.com/video/BV1s6Anz4ExE/", "type": "ugc"},
    {"title": "百度地图-作故私房菜番禺路POI(待真人核门牌)", "url": "https://map.baidu.com/search/%E4%BD%9C%E6%95%85%E7%A7%81%E6%88%BF%E8%8F%9C", "type": "map"}
  ],
  "scores": {"objective": 65, "diner": 80, "taste": 78, "endorsement": 55, "soft_ad_penalty": 5, "platform_credibility": 0.8},
  "data_updated_at": TODAY,
  "notes": "百元档中式主厨餐桌。番禺路为主厨轮换中转站。电话宁空。"
})

# 8. 叶叶菩提
rows.append({
  "name": "叶叶菩提(太原别墅店)",
  "district": "徐汇区",
  "address": "上海市徐汇区太原路160号太原别墅6号楼一层",
  "price_avg": 1260,
  "price_range": "套餐999/1260/1580/2111元四档(含服务费)",
  "cuisine_paths": [["中餐", "素食"]],
  "form": "私宴会所",
  "signature_dishes": ["黑松露佛跳墙(菌菇版)", "一品菌汤水晶锅", "金玉满堂", "藜麦烧尼泊尔菌", "山药百合甜瓜燕"],
  "phone_raw": "02152666089",
  "booking_method": "电话预约，至少提前1天，只做套餐不零点",
  "status": "open",
  "evidence_summary": "叶叶菩提(太原别墅店)藏身太原路160号太原别墅6号楼，是上海高端禅意素宴代表。整栋别墅改造为3层不同主题空间：地下一层江南水乡船屋凉亭小桥流水，一层欧式乡村包间，二层山西窑洞式包厢，最大可容30人。全程梵音、沉香、艾草暖垫、手作棉麻菜单，进门保安核对预约、专属包间、茶服/僧袍管家式服务，落座先奉男女不同养生茶，餐前水果去皮切块可续盘。只做套餐，按价位分999/1260/1580/2111四档(含服务费)，主打山珍菌菇创意素食，黑松露佛跳墙(菌菇版)、一品菌汤水晶锅配4种蘸酱、金玉满堂、藜麦烧尼泊尔菌、山药百合甜瓜燕，菜品灵感部分来自宋代古籍《山家清供》，上桌服务员讲解典故。Trip.com 110条评论4.9分。",
  "evidence": {
    "diner_quotes": [
      {"quote": "叶叶菩提(太原别墅店)是一家藏身于太原路160号太原别墅6号楼一层的高端素食餐厅，主打禅意+仪式感的沉浸式素宴。全程梵音、沉香、艾草暖垫、手作棉麻菜单，被食客称为魔都素食氛围天花板。只做套餐按999/1260/1580/2111四档，高口碑菜黑松露佛跳墙、一品菌汤水晶锅。进门保安核对预约，落座先奉养生茶。", "source": "Trip.com", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/yeye-bodhi-78556502/", "date": "2026-06-28"},
      {"quote": "是一家炒鸡惊艳的素菜馆没错了！从入门到就餐整套体验感拉满。环境在太原别墅里布置非常古风，入门就有淡淡香气心情平静。点的心满意足单人套餐从餐前水果到前菜主菜主食和饭后甜点，整个上菜节奏很舒服，份量也刚刚好。而且惊艳的是素食原来也可以如此不一样，每一道菜都有自己的小亮点。", "source": "Trip.com", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/yeye-bodhi-78556502/", "date": "2026-05-22"}
    ],
    "platform_scores": [
      {"platform": "Trip.com", "score": 4.9, "review_count": 110, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/yeye-bodhi-78556502/"}
    ],
    "negative_signals": ["客单价跨度大(488-600大众口径 vs 1200-1600高端套餐)，性价比争议", "仪式感重、管家服务偏形式化", "纯素宴口味窄，非素食爱好者可能觉得清淡"],
    "soft_ad_flags": [],
    "traffic_signals": ["Trip.com 110条评论4.9分", "商务宴请/长辈静心宴/素食打卡热门", "太原别墅老洋房空间自带传播"]
  },
  "sources": [
    {"title": "叶叶菩提太原别墅店-Trip.com评价区", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/yeye-bodhi-78556502/", "type": "ugc"},
    {"title": "百度地图-叶叶菩提太原别墅店POI(电话02152666089)", "url": "https://map.baidu.com/search/%E5%8F%B6%E5%8F%B6%E8%8F%86%E6%8F%90%E5%A4%AA%E5%8E%9F%E5%88%AB%E5%A2%85", "type": "map"}
  ],
  "scores": {"objective": 80, "diner": 82, "taste": 78, "endorsement": 72, "soft_ad_penalty": 0, "platform_credibility": 0.9},
  "data_updated_at": TODAY,
  "notes": "高端禅意素宴，左庭上院酒店内。sources仅1类(Trip)，stage1可能warn来源类型不足，待补大众点评/公众号。"
})

# 9. 皖宴(龙柏饭店店)
rows.append({
  "name": "皖宴(龙柏饭店店)",
  "district": "长宁区",
  "address": "上海市长宁区虹桥路2419号8栋龙柏饭店内",
  "price_avg": 388,
  "cuisine_paths": [["中餐", "徽菜"]],
  "form": "私宴会所",
  "signature_dishes": ["蓝纹芝士臭鳜鱼", "黑松露米粉肉捞饭", "石耳鸡豆花", "古法甲鱼", "冬笋鸡火鳖汤"],
  "phone_raw": "02162095177",
  "booking_method": "电话预约，独立私密包厢",
  "status": "open",
  "awards": {"michelin": "推荐", "black_pearl": 1, "source_url": None},
  "evidence_summary": "皖宴(龙柏饭店店)2017年8月开业，藏在虹桥龙柏饭店8栋老别墅内，是高端徽菜代表，连续2年黑珍珠一钻、连续3年米其林推荐。门头低调，内里挑高空间如欧式城堡，悬中式女子油画、七彩琉璃吊灯、马头墙壁画，中西融合。招牌蓝纹芝士臭鳜鱼将蓝纹芝士融入传统臭鳜鱼，闻着臭吃着香、上桌撒芝士仪式感强；黑松露米粉肉捞饭、石耳鸡豆花、皖南馓汤、皖宴小黄鱼、古法甲鱼、冬笋鸡火鳖汤(炖大半天甲鱼裙边糯弹)。DiningCity评分9.0(食物9.3/服务8.8/环境9.0)，人均388。以传统徽菜烹饪为根融入创新，适合商务宴请贵宾聚餐。注意该店有苏河湾分店、属连锁高端徽菜，私宴属性偏弱、有公开门头，按TimeOut秘宴通道收录但标注。",
  "evidence": {
    "diner_quotes": [
      {"quote": "蓝纹芝士臭鳜鱼，徽菜的招牌之一，第一次吃到融合蓝纹芝士的臭鳜鱼，将蓝纹芝士融入再烹饪，虽然闻着臭上加臭但吃在嘴里香上加香，端上桌会再撒上一层芝士，仪式感满满，入口是芝士...", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=49151852", "date": "2024-05-15"},
      {"quote": "这家西区宝藏高端宴请餐厅皖宴真的太有格调，以传统徽菜古法手艺为基底，守正创新把古老徽味做出现代高级质感。店内典雅大气，随处可见名画与珍贵瓷器藏品，独立私密包厢，商务宴请贵宾聚餐都超有排面。", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=352056685", "date": "2026-08-07"}
    ],
    "platform_scores": [
      {"platform": "DiningCity", "score": 9.0, "review_count": None, "url": "https://www.diningcity.cn/zh/shanghai/wu_cai_wan_yan"}
    ],
    "negative_signals": ["有公开门头+连锁分店(苏河湾/慎余里)，私宴属性偏弱，更偏高端商务宴请", "蓝纹芝士臭鳜鱼融合做法争议，传统徽菜食客可能觉得'不够本'", "包厢宴请人均偏高"],
    "soft_ad_flags": ["携程探店'宝藏高端宴请'文案偏营销"],
    "traffic_signals": ["黑珍珠一钻连续2年", "米其林推荐连续3年", "商务宴请包厢常年满"]
  },
  "sources": [
    {"title": "携程笔记-皖宴蓝纹芝士臭鳜鱼", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=49151852", "type": "ugc"},
    {"title": "DiningCity-皖宴龙柏饭店", "url": "https://www.diningcity.cn/zh/shanghai/wu_cai_wan_yan", "type": "platform"},
    {"title": "电话邦-皖宴龙柏饭店店", "url": "https://www.dianhua.cn/dt/a22302ff0988433ba459e4b04e0824b4/43930ad3a11a931813d015e21ac20d60", "type": "map"},
    {"title": "TimeOut上海-皖宴秘宴", "url": "https://www.timeoutshanghai.cn/features/6238.html", "type": "media"}
  ],
  "scores": {"objective": 82, "diner": 78, "taste": 80, "endorsement": 85, "soft_ad_penalty": 3, "platform_credibility": 0.9},
  "data_updated_at": TODAY,
  "notes": "边界店：龙柏饭店别墅内高端徽菜宴请，有公开门头与连锁分店，私宴属性偏弱，按TimeOut秘宴通道收录并标注。"
})

# 10. 澄园
rows.append({
  "name": "澄园",
  "district": "长宁区",
  "address": "上海市长宁区武夷路277弄(三层小楼，预约告知)",
  "price_avg": None,
  "price_range": "包厢套餐约498元/八人桌；无菜单按时令配菜",
  "cuisine_paths": [["中餐", "本帮菜"]],
  "form": "私宴会所",
  "signature_dishes": ["蟹粉狮子头", "珍蕈面(六种菌菇汤底)", "黑胡椒罗氏虾"],
  "phone_raw": "02132181092",
  "booking_method": "电话预约，不设菜单，老板Leo按当日时令食材配菜",
  "status": "open",
  "evidence_summary": "澄园藏在武夷路277弄一栋三层小楼，按老上海人家考究布置，餐具茶碟温润精致，不像餐厅倒像去讲究的朋友家做客，只接待独享家庭料理的有缘人。这里没有菜单，由主理人Leo根据时令食材随心搭配，菜偏清淡以本帮为主随季更换、保留经典菜。招牌蟹粉狮子头讲究刀工，肉丁一刀一刀切出、与五小时慢炖鸡汤熬煮两小时、入口即化；珍蕈面以六种菌菇慢火熬汤底、配黄油轻煎松茸与炒过的松蕈牛肝菌，下了大功夫。食客聚餐点498元八人餐，黑胡椒罗氏虾等现点现做，整体不重盐重糖重糖、清爽适口。",
  "evidence": {
    "diner_quotes": [
      {"quote": "我今天聚餐点的就是498的八人餐，这一桌菜品看起来非常精致，现点现做，黑胡椒罗氏虾。整个吃下来，他们家菜品不会是重盐重油重糖的感觉，吃起来非常清爽，每一个菜的味道真的都很赞。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7668485717056227763", "date": "2026-07-31"},
      {"quote": "澄园的三层小楼按老上海人家进行考究布置，只接待独享家庭料理的有缘人。这里没有菜单，皆是Leo根据时令食材进行的随心搭配。一道珍蕈面以六种不同菌菇慢火熬制成汤底，配以黄油轻煎的松茸、炒过的松蕈和牛肝菌。", "source": "TimeOut上海", "url": "https://www.timeoutshanghai.cn/features/6229.html", "date": "2026-08-22"}
    ],
    "platform_scores": [
      {"platform": "TimeOut/界面推荐", "score": None, "review_count": None, "url": "https://m.jiemian.com/article/1026598_yidian.html"}
    ],
    "negative_signals": ["UGC评论样本少，平台分缺失", "无菜单按主理人配菜，众口难调", "三层小楼位置隐蔽"],
    "soft_ad_flags": [],
    "traffic_signals": ["TimeOut/界面新闻多年推荐", "只接有缘人熟客"]
  },
  "sources": [
    {"title": "TimeOut上海-澄园家庭住址", "url": "https://www.timeoutshanghai.cn/features/6229.html", "type": "media"},
    {"title": "界面新闻-上海三家私房菜澄园", "url": "https://m.jiemian.com/article/1026598_yidian.html", "type": "media"},
    {"title": "抖音-澄园私房菜498八人餐", "url": "https://www.iesdouyin.com/share/video/7668485717056227763", "type": "ugc"}
  ],
  "scores": {"objective": 60, "diner": 70, "taste": 78, "endorsement": 70, "soft_ad_penalty": 3, "platform_credibility": 0.75},
  "data_updated_at": TODAY,
  "notes": "Leo主理无菜单本帮时令私宴。UGC偏薄(仅1条抖音+媒体)，待真人补大众点评评论。"
})

# 11. 耘粹坊
rows.append({
  "name": "耘粹坊",
  "district": "长宁区",
  "address": "上海市长宁区江苏路225号",
  "price_avg": 100,
  "cuisine_paths": [["中餐", "本帮菜"]],
  "form": "私宴会所",
  "signature_dishes": ["响油鳝丝茭白丝", "酒渍溏心蛋", "红烧大排骨", "猪油拌饭", "糟蛏子", "油爆虾"],
  "phone_raw": "02162675888",
  "booking_method": "电话/到店，复古本帮小馆",
  "status": "open",
  "evidence_summary": "耘粹坊位于江苏路225号，是上海较有名气的复古本帮私房小馆，门口毫不起眼、进门却别有洞天，满室淘来的民国老家具、藤编座椅、暖色复古台灯、白色百叶窗，海派风情浓郁，老板戏称自己家是包子铺。人均约100元，招牌浓油赤酱的响油鳝丝加入清爽茭白丝好味不腻，酒渍溏心蛋无腥味、蛋黄溏心有凝头，红烧大排骨配猪油拌饭是天生一对，另有肥美鲜甜的糟蛏子、正宗油爆虾。食客称经济实惠、适合闺蜜聚餐，餐具也是老上海味道，靠窗位坐下来有种旧时光老洋房里吃饭的错觉。",
  "evidence": {
    "diner_quotes": [
      {"quote": "今天这家店别看外面毫不起眼，但是进了门就会跟我一样摇身一变，里面别有洞天。那么多古老的家具都是从哪里淘来的？合伙人之一对美学的见解是我们特别佩服的，他淘了一些民国时期的家具，连椅子都特别好看。", "source": "抖音", "url": "https://www.iesdouyin.com/share/video/7317931363615689999", "date": "2023-12-29"},
      {"quote": "浓油赤酱的响油鳝丝加入清爽的茭白丝，好味不腻；酒渍过的溏心蛋无半点腥味，蛋黄溏心很有凝头；红烧大排和猪油拌饭的绝佳配搭，以及肥美鲜甜的糟蛏子、正宗入味的油爆虾，皆叫人心生欢喜，餐具也是老上海的味道。", "source": "TimeOut上海", "url": "https://www.timeoutshanghai.cn/features/6229.html", "date": "2026-08-22"}
    ],
    "platform_scores": [
      {"platform": "上观/头条(人均100)", "score": None, "review_count": None, "url": "http://m.toutiao.com/group/6904550139432698375/"}
    ],
    "negative_signals": ["菜量不大", "民国家具空间有限高峰需等位", "UGC评论样本偏老"],
    "soft_ad_flags": [],
    "traffic_signals": ["本地与外地食客慕名", "民国家具空间成为打卡点"]
  },
  "sources": [
    {"title": "TimeOut上海-耘粹坊", "url": "https://www.timeoutshanghai.cn/features/6229.html", "type": "media"},
    {"title": "上观新闻-耘粹坊猪油拌饭", "url": "http://m.toutiao.com/group/6904550139432698375/", "type": "media"},
    {"title": "抖音-耘粹坊民国家具", "url": "https://www.iesdouyin.com/share/video/7317931363615689999", "type": "ugc"}
  ],
  "scores": {"objective": 65, "diner": 72, "taste": 78, "endorsement": 60, "soft_ad_penalty": 0, "platform_credibility": 0.8},
  "data_updated_at": TODAY,
  "notes": "复古本帮小馆，人均100。UGC偏薄待补。"
})

# 12. 弄堂大叔
rows.append({
  "name": "弄堂大叔",
  "district": "徐汇区",
  "address": "上海市徐汇区湖南路311弄(阁楼内，需爬狭窄木楼梯)",
  "price_avg": None,
  "price_range": "私房本帮家常菜(未公开标价)",
  "cuisine_paths": [["中餐", "本帮菜"]],
  "form": "私宴会所",
  "signature_dishes": ["四喜烤麸", "红烧肉", "蛤蜊蒸蛋", "炸猪排", "红烧青鱼"],
  "phone_raw": "13262286890",
  "booking_method": "电话预约，阁楼仅一张圆桌一张方桌，无菜单无点菜，落座后告知口味偏好由爷叔配菜",
  "status": "open",
  "evidence_summary": "弄堂大叔藏在徐汇湖南路311弄一栋弄堂阁楼里，沿狭窄木楼梯爬上阁楼才到，是无菜单、无点菜的隐秘私房本帮菜。阁楼保留老上海家庭风格，一台老式电视机一边吃饭一边看新闻，有'回家吃饭'的错觉。餐厅只有一张小圆桌和一张小方桌，旁边一书柜做菜的书。落座后小小提示偏爱口味，有典型上海爷叔气质的弄堂大叔便做出合心意的小菜：四喜烤麸、红烧肉、蛤蜊蒸蛋、炸猪排、红烧青鱼，有荤有素家常地道本味。能容纳食客有限，需提前电话预约。",
  "evidence": {
    "diner_quotes": [
      {"quote": "一家藏在湖南路弄堂阁楼里的无菜单、无点菜的隐秘餐厅，做的是私房本帮菜。沿狭窄木楼梯爬上阁楼，环境保留老上海家庭风格，一台老式电视机一边吃饭一边看新闻，有回家吃饭的错觉。餐厅只有一张小圆桌和一张小方桌。落座后告知口味，上海爷叔气质的弄堂大叔便做出合心意的小菜。", "source": "TimeOut上海", "url": "https://www.timeoutshanghai.cn/features/6229.html", "date": "2026-08-22"},
      {"quote": "落座后小小提示自己偏爱的口味，有着典型上海爷叔气质的弄堂大叔便会做出合食客心意的菜式。四喜烤麸、红烧肉、蛤蜊蒸蛋、炸猪排、红烧青鱼，有荤有素家常地道本味。能容纳的食客有限，记得提前预约。", "source": "TimeOut上海", "url": "https://www.timeoutshanghai.cn/features/6160.html", "date": "2026-07-19"}
    ],
    "platform_scores": [
      {"platform": "TimeOut(推荐)", "score": None, "review_count": None, "url": "https://www.timeoutshanghai.cn/features/6160.html"}
    ],
    "negative_signals": ["UGC严重不足，仅TimeOut两篇媒体稿", "阁楼位置隐秘需爬木楼梯，行动不便者不宜", "仅两桌容量，预约紧张"],
    "soft_ad_flags": [],
    "traffic_signals": ["爷叔主理家常味，街坊熟客"]
  },
  "sources": [
    {"title": "TimeOut上海-弄堂大叔阁楼", "url": "https://www.timeoutshanghai.cn/features/6229.html", "type": "media"},
    {"title": "TimeOut上海-魔都阁楼弄堂大叔", "url": "https://www.timeoutshanghai.cn/features/6160.html", "type": "media"}
  ],
  "scores": {"objective": 50, "diner": 60, "taste": 75, "endorsement": 60, "soft_ad_penalty": 0, "platform_credibility": 0.7},
  "data_updated_at": TODAY,
  "notes": "存疑待补证：sources仅TimeOut媒体、无UGC堂食原话，stage1预计打回'无UGC来源'。需真人登录小红书/点评补2条食客原话。"
})

# 13. 华光花园小料理
rows.append({
  "name": "华光花园小料理",
  "district": "闵行区",
  "address": "上海市闵行区虹梅路3297弄华光花园78号",
  "price_avg": None,
  "price_range": "家常菜当天现做(未公开标价)",
  "cuisine_paths": [["中餐", "本帮菜"]],
  "form": "私宴会所",
  "signature_dishes": ["当日现做蒸煮炸家常菜"],
  "phone_raw": "02154133101",
  "booking_method": "街坊熟客电话预约，无菜单",
  "status": "open",
  "evidence_summary": "华光花园小料理是一家开了九年却依然只有百余条点评的隐秘小餐厅，藏在闵行虹梅路3297弄华光花园78号居民小区内，在充斥美食信息的社交平台上很难找到词条，进门的几乎都是街坊熟客。因都是家常菜所以自称'小料理'，吧台上各种蒸煮炸式料理都是当天现做。无菜单无点菜，靠熟客口碑口口相传。",
  "evidence": {
    "diner_quotes": [
      {"quote": "一家开了九年却依然只有百余条点评的隐秘小餐厅，在充斥着各式美食信息的社交平台上也很难找到关于它的词条，进门的几乎都是街坊熟客。因都是家常菜所以自称小料理，吧台上各种蒸、煮、炸式的料理都是当天现做的。", "source": "TimeOut上海", "url": "https://www.timeoutshanghai.cn/features/6229.html", "date": "2026-08-22"}
    ],
    "platform_scores": [
      {"platform": "大众点评(百余条)", "score": None, "review_count": 100, "url": None}
    ],
    "negative_signals": ["UGC严重不足，仅TimeOut一篇", "招牌菜具体菜名缺失", "居民小区内导航难找"],
    "soft_ad_flags": [],
    "traffic_signals": ["9年仅百余条点评，纯街坊熟客口口相传"]
  },
  "sources": [
    {"title": "TimeOut上海-华光花园小料理", "url": "https://www.timeoutshanghai.cn/features/6229.html", "type": "media"}
  ],
  "scores": {"objective": 45, "diner": 50, "taste": 70, "endorsement": 50, "soft_ad_penalty": 0, "platform_credibility": 0.7},
  "data_updated_at": TODAY,
  "notes": "存疑待补证：sources仅TimeOut一篇、无UGC、具体菜名缺失，stage1预计打回。需真人到店/点评补菜名与食客原话。"
})

with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"写入 {len(rows)} 家 -> {OUT}")
