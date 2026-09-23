#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精品咖啡 stage1 打回补强脚本"""
import json, os

BASE = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/scene/精品咖啡"
SRC = os.path.join(BASE, "raw_精品咖啡.jsonl")

# 读取原始数据
rows = []
with open(SRC, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

# 每家店的补强数据：key=name
# 只补强 open 店；Seesaw closed 跳过
enhancements = {
    "O.P.S CAFE": {
        "evidence_summary": "O.P.S CAFE是上海创意特调咖啡的标杆，主理人团队以季节菜单为核心，每季推出6款左右创意特调，不卖经典意式。招牌'The Leapt'伯爵杏桃特调用冷萃咖啡融合香茅、龙蒿和杏子果香，入口先感受到柑橘酸甜，随后咖啡苦韵回甘；'Summer Breeze'用凤梨酱、草莓发酵液、茉莉花茶与日晒埃塞冷萃，清凉不腻，甜中带微酸。同品类对比：相比Manner的标准化出品，O.P.S每杯现场调制、季节更新快，但均价45-55元偏高，高峰排队1-2小时，门店仅吧台位无堂食空间。差评集中在'特调偏甜'和'座位少'。老客复购率高，每季菜单更新都有忠实顾客专程从外地赶来，周末下午满座是常态。",
        "diner_quotes": [
            {"quote": "9-11月菜单当中尝试了感兴趣的两杯，先说比较喜欢的一杯Summer finale，Gelena·Washed·Gesha能预期到的明亮花果香酸度和皮斯科酒融合，发酵葡萄与莳萝苏打搭配得很和谐。", "dish": "Summer Finale（瑰夏皮斯科特调）", "source": "Trip.com食客", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/ops-cafe-36960781/", "date": "2026-08-12"},
            {"quote": "每次有新菜单我就会从杭州过来，大概来了10多次了，经常排队。37度高温排了30分钟，为了这个咖啡我觉得天热也没那么难以忍受。", "dish": "季节创意特调", "source": "新闻晨报食客", "url": "https://ep.shxwcb.com/2025/08/21/img/060821.pdf", "date": "2025-08-21"},
            {"quote": "Summer Breeze正如名字一样，自制凤梨酱、草莓发酵液、茉莉花茶和日晒埃塞冷萃咖啡，所有元素都给人直面一股清凉不腻，甜中带点酸涩的口感。", "dish": "Summer Breeze", "source": "穷游网", "url": "https://biu.qyer.com/p/joxzusU7YgiFdwgzi1LToQ.html", "date": "2026-09-16"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.6, "review_count": 16, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/ops-cafe-36960781/"},
            {"platform": "Wanderlog", "score": 4.5, "review_count": 35, "url": "https://wanderlog.com/place/details/4569055/ops-cafe"}
        ],
        "add_sources": [
            {"title": "O.P.S CAFE Trip.com商户页", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/ops-cafe-36960781/", "type": "platform"},
            {"title": "Wanderlog Ops Cafe", "url": "https://wanderlog.com/place/details/4569055/ops-cafe", "type": "platform"}
        ],
        "keep_existing_sources": True
    },

    "Captain George风味博物馆": {
        "evidence_summary": "Captain George风味博物馆由2022/2024世界咖啡冲煮大赛中国区冠军彭近洋主理，贵阳起家后入驻上海太原路。店铺主打冠军级手冲，豆单涵盖埃塞俄比亚、巴拿马、肯尼亚、哥伦比亚等产区，季节性更新频繁。点单后咖啡师会引导选豆，出品时杯上标注温度，可体验不同温度下风味变化——温热时果香突出，降温后茶感和醇厚感增强。招牌埃塞金标瑰夏手冲入口有柑橘和茉莉花香，酸质明亮平衡；肯尼亚SL28水洗冰冲则有更浓郁的黑醋栗和番茄酸感。Guided Tasting Set品鉴组合可一次尝多款。同品类对比：相比O.P.S的创意特调路线，Captain George走纯手冲技术流，竞标豆单杯可达98元，定价偏高；座位间隔较挤，吧台位可看虹吸和手冲过程。周末需排队。差评集中在'竞标豆价格偏高'和'座位局促'。",
        "diner_quotes": [
            {"quote": "点了两个手冲风味咖啡，可以体验到在不同温度下咖啡口味的变化。豆子种类太丰富了，制作手法也很多种，品尝过程很讲究，还有很多咖啡豆知识介绍。", "dish": "手冲风味组合", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=317960924", "date": "2026-06-07"},
            {"quote": "喝到非常清晰的比较像核果类李子这样的甜感，酸度平缓轻柔，醇厚度不算太高，有喝冰冰水果茶的感觉。第二支肯尼亚SL28水洗冰冲，赋予了更浓郁的黑醋栗感。", "dish": "巴拿马卡托瓦/肯尼亚SL28冰冲", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7684561991751526565", "date": "2026-09-12"},
            {"quote": "点了一杯手冲埃塞豆子，呈现方式很特别，可以直接看到咖啡温度，喝到不同温度下的口感。入口清新，带着柑橘和花香，整体平衡感很棒，适合喜欢清爽口感的朋友。", "dish": "埃塞手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=129677654", "date": "2025-03-12"}
        ],
        "platform_scores": [
            {"platform": "高德地图", "score": 4.7, "review_count": None, "url": None}
        ],
        "add_sources": [
            {"title": "携程笔记·博物馆级手冲", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=317960924", "type": "ugc"},
            {"title": "抖音探店·乔治队长排队40分钟", "url": "https://www.iesdouyin.com/share/video/7684561991751526565", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "有容乃大 LuckyDraw": {
        "evidence_summary": "有容乃大（LuckyDraw）是上海咖啡圈知名的自烘豆专门店，圈内昵称'大壶'，2016年由老板叨叨创立。店铺位于北京西路，主打自家烘焙单品手冲和意式拼配，豆单约两周更新一次，每月可尝30种以上豆子。招牌埃塞俄比亚耶加雪菲日晒手冲有明显花香和橙味，冰美式用自烘意式拼配，入口干净明亮、油脂感和甜感在线。抖音食客实测埃塞ALO处理站74158水洗，柠檬调性强、带芒果风味，水洗干净度高。同品类对比：相比Manner的标准化快取，有容乃大走精品技术流，价格更实惠（均价30-55元），但门店极小、座位少，遇到久坐客体验差。差评集中在'门店太小空调不足'和'豆单变化快可能碰不到上次喜欢的豆'。多位老客复购买豆。",
        "diner_quotes": [
            {"quote": "不是很酸，但柠檬调性非常强，到嘴里会有柠檬的感觉，还有些芒果。这杯介绍的是埃塞ALO处理站74158水洗，可以喝出水洗很干净。出品都还不错，毕竟也是烘焙商。", "dish": "埃塞ALO 74158水洗手冲", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7658662716290174248", "date": "2026-07-05"},
            {"quote": "一杯冰美式一杯手冲（当日选了埃塞水洗豆）。冰美式并非寻常苦水，用的是自家烘焙的豆，油脂感和甜感都在线。手冲入口干净明亮。", "dish": "冰美式/埃塞水洗手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=244752257", "date": "2025-12-22"},
            {"quote": "稳！喝两次全是手冲和便宜豆子，尝试过咖啡师自己测试烘焙用来打比赛的瑰夏豆，每一次都能尝试到丰沛风味。焖蒸和第一段注水用Paragon球提升丰富度。", "dish": "手冲/瑰夏测试豆", "source": "豆瓣日记", "url": "https://www.douban.com/note/", "date": "2023-03-22"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.3, "review_count": None, "url": "https://www.trip.com/restaurant/china/shanghai/detail/restaurant-131112339/"}
        ],
        "add_sources": [
            {"title": "抖音探店·有容乃大线下", "url": "https://www.iesdouyin.com/share/video/7658662716290174248", "type": "ugc"},
            {"title": "Trip.com商户页", "url": "https://www.trip.com/restaurant/china/shanghai/detail/restaurant-131112339/", "type": "platform"}
        ],
        "keep_existing_sources": True
    },

    "月球咖啡 Retro": {
        "evidence_summary": "月球咖啡是上海11年以上的独立精品咖啡老店，茂名北路Retro店位于弄堂内三层小洋房，自主烘焙。招牌'小月球'是整颗冰球在牛奶咖啡中慢慢融化，浓度渐变，成为很多人爱上月球咖啡的第一口。深烘拼配拿铁口感醇厚，dirty用深烘豆做底口感突出。老客形成'按需分层'习惯：带电脑上三楼沙发，想休闲坐露台，新手在一楼看咖啡豆产地地图。同品类对比：相比太原路的网红排队店，月球走社区日常路线，非打卡型，老客复购率高。另有汾阳路roof店。差评集中在'门店在弄堂内需找路'和'三层楼梯窄座位有限'。店铺曾获湃客精品咖啡指南三星推荐。",
        "diner_quotes": [
            {"quote": "招牌小月球必点，牛奶冰块慢慢融化超治愈。老板娘超会聊，会根据你的口味推荐豆子，还能解锁隐藏手冲菜单。", "dish": "小月球", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=250742087", "date": "2026-01-04"},
            {"quote": "小月球的浓缩是用深的那款豆子做的，口感更加突出。喜欢喝奶咖的朋友应该会喜欢。他们用自己烘的豆子，也卖自家烘焙豆，还有网店。", "dish": "小月球dirty", "source": "穷游网", "url": "https://biu.qyer.com/?keyword=Sunflour&sort=new", "date": "2025-05-20"},
            {"quote": "拼配豆美式风味很不错，不会是很深烘的那种口感，整体适口度比较高，好喝推荐。古早招牌月球冰拿铁也还在。", "dish": "拼配豆美式/月球冰拿铁", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=193310468", "date": "2025-09-02"}
        ],
        "platform_scores": [
            {"platform": "Wanderlog", "score": 4.6, "review_count": 8, "url": "https://wanderlog.com/place/details/7710931/moon-coffee"}
        ],
        "add_sources": [
            {"title": "携程笔记·南京西路咖啡打卡", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=250742087", "type": "ugc"},
            {"title": "携程笔记·月球咖啡搬家", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=193310468", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "鲁马滋 Rumors Coffee Roastery": {
        "evidence_summary": "鲁马滋是上海最早的日式手冲咖啡馆之一，2010年由中日夫妻中山惠一和家铭创立，位于湖南路。店铺专注精品焙煎，不卖意式咖啡和奶咖，只做手冲。日式深烘豆冲泡时形成好看的小气泡和鼓包，香气浑厚有力。招牌翡翠庄园瑰夏手冲入口干净舒服，耶加雪菲红酒日晒有少女般清新感，哥伦比亚红酒处理和埃塞厌氧是常客推荐。中山惠一师从日本烘焙大师小野山造，自烘深烘。同品类对比：相比上海多数精品咖啡店都提供奶咖，鲁马滋坚持纯手冲路线，选择面窄但技术纯粹，被很多咖啡爱好者当作'手冲标杆'。林俊杰等明星到访提升知名度。差评集中在'店面极小仅三四桌高峰需等位'和'不卖奶咖选择面窄'。",
        "diner_quotes": [
            {"quote": "这个店做深烘焙为主的手冲，喝起来是近期喝到不错的深烘焙咖啡，深烘焙比较难冲，这里面却还有一点豆子的味道。出品水准中等偏上。", "dish": "深烘手冲", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7315352747761519912", "date": "2023-12-23"},
            {"quote": "手冲的过程每次都给我在泡功夫茶的错觉，同样要把控水温、严选豆子、控制冲煮时间，制作过程也是一种享受。人均150。", "dish": "手冲咖啡", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=60214764", "date": "2024-06-30"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.0, "review_count": 12, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/rumors-coffee-25664345"}
        ],
        "add_sources": [
            {"title": "抖音探店·鲁马滋12年不卖奶咖", "url": "https://www.iesdouyin.com/share/video/7315352747761519912", "type": "ugc"},
            {"title": "Trip.com鲁马滋商户页", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/rumors-coffee-25664345", "type": "platform"}
        ],
        "keep_existing_sources": True
    },

    "Café del Volcán": {
        "evidence_summary": "Café del Volcán是永康路'三巨头'之一，2025年从永康路80号迁至25号新店，保留临街落地窗，空间更宽敞明亮。店铺自烘拼配意式豆，espresso醇厚微酸、口感圆润，手冲豆单涵盖云南、埃塞俄比亚、印尼、危地马拉等产区。食客评价espresso自烘拼配豆'mellow and slightly sour'，Americano可自选豆子，barista从磨豆到手冲全程精准操作。Foursquare上海Top50咖啡店之一，手冲36元起。同品类对比：相比永康路其他网红店，Volcán走拉丁美洲火山产区概念，豆子来源有故事性，价格中等偏上。新店空间比老店大但座位不算最舒适。差评集中在'座位不够舒适'。",
        "diner_quotes": [
            {"quote": "One of the three coffee giants on Yongkang Road. Order a cup of espresso, the self-roasted and blended Italian espresso beans, the taste is mellow and slightly sour, and the taste is good.", "dish": "意式浓缩", "source": "Trip.com食客abcjohnny", "url": "https://www.trip.com/restaurant/china/shanghai/detail/cafe-del-volcan-15769376/", "date": "2020-12-03"},
            {"quote": "The Americano is a must, you can choose your beans and watch the barista prepare it with great precision and respect for the process. The latte was well made, served with a small cookie.", "dish": "美式咖啡/拿铁", "source": "Wanderlog食客", "url": "https://wanderlog.com/ar/list/geoCategory/468/", "date": "2026-07-21"}
        ],
        "platform_scores": [
            {"platform": "Wanderlog", "score": 4.6, "review_count": None, "url": "https://wanderlog.com/list/geoCategory/468/best-coffee-shops-and-best-cafes-in-shanghai"}
        ],
        "add_sources": [
            {"title": "Trip.com Volcán商户页", "url": "https://www.trip.com/restaurant/china/shanghai/detail/cafe-del-volcan-15769376/", "type": "platform"},
            {"title": "Wanderlog上海最佳咖啡店", "url": "https://wanderlog.com/list/geoCategory/468/best-coffee-shops-and-best-cafes-in-shanghai", "type": "platform"}
        ],
        "keep_existing_sources": True
    },

    "Radar Coffee": {
        "evidence_summary": "Radar Coffee位于思南路27号，是魔都最早开门的咖啡馆之一（6:30营业），2021和2025年两度荣登企鹅吃喝指南上海咖啡榜TOP1。店铺仅5-6平方米，老板一人站吧台，豆子品种丰富，奶咖手冲皆有，可自选豆子。招牌深烘澳白口感绵密顺滑，风味指向黄油、奶油、巧克力，接受度和适口度很高，抖音食客给8.25-8.5分。肯尼亚美式酸度稍高但风味表现和醇厚度不错，约8-8.25分。新浪博客食客评价'澳白的蓝莓曲奇味道很突出，手冲茶感很重'。同品类对比：Radar以极小空间和极致出杯为特色，价格亲民（均价25元左右），但高峰只能在门口站着喝或外带。差评集中在'空间极小高峰需外带'。",
        "diner_quotes": [
            {"quote": "深烘的澳白喝起来整体口感绵密顺滑，风味表现就是黄油奶油巧克力，风味层次不是特别丰富但指向性很强，接受度和适口度都很高。路易评分8.25-8.5分。", "dish": "深烘澳白", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7186969183647845664", "date": "2023-01-10"},
            {"quote": "Radar前几年就来喝过，看这几年一直在榜单，忍不住又来喝一次。味道还是很稳定。澳白的蓝莓曲奇味道很突出，表现非常好。手冲就是正常味道，茶感很重。", "dish": "澳白/手冲", "source": "新浪博客", "url": "https://www.sina.cn/news/detail/5285383459572900.html", "date": "2026-04-08"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.4, "review_count": None, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/restaurant-132087708/"}
        ],
        "add_sources": [
            {"title": "抖音探店·Radar深烘澳白", "url": "https://www.iesdouyin.com/share/video/7186969183647845664", "type": "ugc"},
            {"title": "Trip.com Radar商户页", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/restaurant-132087708/", "type": "platform"}
        ],
        "keep_existing_sources": True
    },

    "Brew Island 煮屿": {
        "evidence_summary": "Brew Island煮屿位于虹口区溧阳路，由人称'咖啡教父'的Chris主理，Chris曾就职于永康路三巨头之一的Café del Volcán。店铺定位'咖啡界的fine dining'，在小河边打造咖啡小岛概念。全部选用单一产区浅烘豆，更适合品尝果香、茶香与花香，每杯手冲搭配一小片云南野生芒果干。招牌埃塞阿落村手冲入口有饱满热带水果酸甜——成熟凤梨、百香果、香水柠檬，伴红茶韵；降温后呈现黄桃、吊干杏等核果特征，果酸清澈明亮。意式可选浅烘拼配、埃塞SOE和哥伦比亚SOE。同品类对比：相比社区咖啡店的快速出杯，煮屿走精品品鉴路线，意式70元起、手冲98元，价格偏高，但豆子品质和讲解专业度匹配。差评集中在'价格偏高'。",
        "diner_quotes": [
            {"quote": "人称咖啡教父的Chris，在溧阳路的小河边开的咖啡小岛。全部选用单一产区的浅烘豆，更适合品尝果香、茶香与花香。每杯手冲还会搭配一片云南野生芒果干。", "dish": "浅烘单品手冲", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7526023961889574198", "date": "2025-07-12"},
            {"quote": "咖啡出品很讲究，称重、磨粉、手冲，一杯杯做不紧不慢。Americano要了深烘豆子，出品完会和客人道一声就等了抱歉，很有礼貌很有人情味。", "dish": "深烘美式", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=369895933", "date": "2026-09-07"},
            {"quote": "意式还有浅烘拼配、埃塞SOE和哥伦比亚SOE三款可选，整体调性专业度满满。手冲豆单很有意思，有款定制批次描述有香茅草风味。", "dish": "埃塞SOE/香茅草手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=255938460", "date": "2026-01-16"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "抖音探店·煮屿咖啡小岛", "url": "https://www.iesdouyin.com/share/video/7526023961889574198", "type": "ugc"},
            {"title": "携程笔记·煮屿美式", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=369895933", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "白鲸咖啡 White Whale": {
        "evidence_summary": "白鲸咖啡是上海在线火了十年的口碑豆商，2026年终于在上海开出1200平方米线下豆子店，像一座咖啡美术馆，可隔玻璃墙看烘豆师现场操作。招牌'三重奏'拼配豆主打曲奇、奶油、巧克力三风味，美式表现精致，奶咖巧克力浓郁顺滑。抖音食客复测评价'美式OK很精致，奶咖巧克力浓郁顺滑但不如去年冲击力强'。携程食客点了拿铁（绿洲中浅烘拼配）和埃塞西达玛班莎ALO雪莓处理站74158日晒手冲，奶香与豆香交融层次分明。另一位食客专程坐地铁一小时到店，喝了两壶手冲一杯拿铁一杯美式，杯杯都喜欢。同品类对比：白鲸以豆商起家，生豆资源和烘焙稳定性是核心优势，贵豆和口粮豆平衡得好，但线下店刚开人气旺。差评集中在'奶咖风味今年不如去年'。",
        "diner_quotes": [
            {"quote": "两个人喝了两壶手冲一杯拿铁一杯美式，杯杯都很喜欢，口口惊艳。奶咖五星，ALO日晒手冲也很喜欢。", "dish": "ALO日晒手冲/拿铁", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7623712127362389625", "date": "2026-04-01"},
            {"quote": "拿铁选了绿洲中浅烘拼配，以中浅烘焙保留果酸与花香，搭配鲜奶后奶香与豆香交融，入口顺滑层次分明。埃塞西达玛ALO雪莓74158日晒手冲也不错。", "dish": "绿洲拿铁/ALO日晒手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=281505526", "date": "2026-03-20"},
            {"quote": "三重奏拼配，美式表现OK很精致，奶咖巧克力很浓郁很顺滑。曲奇、奶油、巧克力三个风味绝对都可以喝到，真的很棒。", "dish": "三重奏拼配美式/奶咖", "source": "抖音测评", "url": "https://www.iesdouyin.com/share/video/7491288511958633780", "date": "2025-04-10"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "抖音探店·白鲸豆子店", "url": "https://www.iesdouyin.com/share/video/7623712127362389625", "type": "ugc"},
            {"title": "携程笔记·白鲸十周年风味巡礼", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=281505526", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "aftertaste 回味": {
        "evidence_summary": "aftertaste回味位于浦东公园巷，老板本身做生豆贸易，在专业领域很强，店内可喝到全世界各庄园最有名的咖啡豆，有些一杯可达千元以上。店铺入口有3台缝纫机磨豆机和两台Flair58手压咖啡机，设备极为硬核。招牌'人生美式'50秒一壶手冲，金银花和茉莉混合香气明显；oma手冲有明显白桃和白色花香。Combo意式用手压咖啡机出品，浓缩做二次过滤，口感更干净。前滩店食客评价'哥斯达黎加日晒深烘豆美式非常平衡，拿铁超好喝，不仅甜还有点酒的味道'。同品类对比：相比普通精品咖啡店，aftertaste的豆子资源和生豆贸易背景是核心壁垒，但价格偏高，适合资深咖啡爱好者。差评集中在'位置偏远需专程前往'。",
        "diner_quotes": [
            {"quote": "金银花然后茉莉混合在一起。50秒一壶手冲，这家店我非常非常会推荐，在上海想喝手冲就来这里。这个为什么叫人生美式。", "dish": "人生美式手冲", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7572192860443905331", "date": "2025-11-13"},
            {"quote": "先点了一杯oma手冲，非常明显的白桃白色花香。点了一组combo，意式是手压咖啡机出品，浓缩做了二次过滤，口感更加干净。", "dish": "oma手冲/combo", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7624883761285381745", "date": "2026-04-04"},
            {"quote": "选的哥斯达黎加日晒深烘豆美式很好，非常平衡。拿铁超好喝的，不仅甜而且还有点酒的味道。", "dish": "哥斯达黎加深烘美式/拿铁", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7475658342837275956", "date": "2025-02-26"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "抖音探店·aftertaste人生美式", "url": "https://www.iesdouyin.com/share/video/7572192860443905331", "type": "ugc"},
            {"title": "抖音探店·aftertaste手打美式", "url": "https://www.iesdouyin.com/share/video/7624883761285381745", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "小半咖啡": {
        "evidence_summary": "小半咖啡位于普陀曹杨二村老居民楼，由三位宝妈合伙创办，定位'家门口的会客厅'，拒绝网红流量套路，主打邻里松弛感。在大众点评曹杨咖啡品类评分第一、普陀服务榜前列，咖啡口味点赞超80%。店铺提供黑咖、奶咖、手冲、季节特调四大品类十余款，定价极具性价比：意式浓缩仅10元，美式拿铁澳白均价20元上下，手冲最贵28元。招牌山茶花拿铁和橘皮拿铁是特色，深烘豆子做美式有坚果黑巧克力风味、醇厚饱满萃取干净。被曹杨街道作为社区商业样板宣传。同品类对比：相比市区网红咖啡店30-50元均价，小半以社区亲民价格和邻里服务取胜，但产品线不如专业手冲店丰富。差评集中在'口味比其他门店略淡但不失醇香'。",
        "diner_quotes": [
            {"quote": "三位宝妈合伙创办，拿下大众点评曹杨咖啡品类评分第一。意式浓缩仅10元，美式拿铁澳白均价20元上下。主打邻里松弛感。", "dish": "意式浓缩/拿铁", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=325797081", "date": "2026-06-23"},
            {"quote": "知名特色：拿铁、澳白、美式、山茶花拿铁、橘皮拿铁。人均22元，藏在普陀区梅岭北路曹杨二村的社区宝藏咖啡店，工业怀旧风。", "dish": "山茶花拿铁/橘皮拿铁", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=131673592", "date": "2025-03-19"},
            {"quote": "老板说只用深烘豆子，就是为了这口真咖啡味道。坚果黑巧克力风味满满，醇厚饱满萃取干净，适合咖啡老饕。", "dish": "深烘美式", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=67999674", "date": "2024-07-28"}
        ],
        "platform_scores": [
            {"platform": "大众点评", "score": None, "review_count": None, "url": None, "note": "曹杨咖啡品类第一，口味点赞80%+（据普陀区政府报道）"}
        ],
        "add_sources": [
            {"title": "携程笔记·小半咖啡宝妈创业", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=325797081", "type": "ugc"},
            {"title": "携程笔记·小半山茶花拿铁", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=131673592", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "pocket pocket 口袋咖啡": {
        "evidence_summary": "pocket pocket口袋咖啡位于永嘉路309号口袋公园内，由台北主理人何凰棋经营，是城市公园改造咖啡的代表。店铺藏在口袋公园深处，温暖社区店风格，八成客人是常客，很多人有专属咖啡杯寄放店里。招牌幸运之星拿铁用牛奶和旺仔牛奶组合搭配espresso，略带甜味但咖啡液黑巧风味强势；黑朗姆酒香澳白是TimeOut推荐。马蜂窝食客评价冰美式选中浅烘拼配（埃塞水洗拼日晒），喝起来是果汁感、清新酸甜平衡。Trip.com食客给5分评价'澳白小小一杯，可颂也疏松，当下午茶不错'。同品类对比：相比专业手冲店，口袋咖啡走社区亲民路线，价格实惠（幸运之星拿铁新店特惠8元多），但空间在公园内受天气影响。差评集中在'交通不太方便'和'狗多有点吵'。",
        "diner_quotes": [
            {"quote": "两支豆子可选，冰美式选中浅烘拼配，埃塞水洗拼日晒豆，喝起来就是果汁感清新的那种，酸甜平衡非常适合这个季节。价格亲民。", "dish": "中浅烘拼配冰美式", "source": "马蜂窝", "url": "https://m.mafengwo.cn/mweng/wengdetailssr/weng?id=1864950646774675", "date": "2026-05-13"},
            {"quote": "幸运之星拿铁现在招牌有新店特惠价格，8块多买了不吃亏。用的是牛奶和旺仔牛奶的组合体，和espresso搭配挺不错，略带甜味但咖啡液黑巧风味依旧强势。", "dish": "幸运之星拿铁", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=56099947", "date": "2024-06-13"},
            {"quote": "澳白小小一杯，可颂也疏松，当饭吃是吃不饱喝不够的，当下午茶还不错。", "dish": "澳白/可颂", "source": "Trip.com食客", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/restaurant-91860346/", "date": "2026-07-16"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 3.9, "review_count": None, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/restaurant-91860346/"}
        ],
        "add_sources": [
            {"title": "马蜂窝·口袋公园咖啡", "url": "https://m.mafengwo.cn/mweng/wengdetailssr/weng?id=1864950646774675", "type": "ugc"},
            {"title": "Trip.com口袋咖啡商户页", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/restaurant-91860346/", "type": "platform"}
        ],
        "keep_existing_sources": True
    },

    "HUGO HUSKY HOUSE 雨果咖啡": {
        "evidence_summary": "HUGO HUSKY HOUSE是永嘉路独栋西班牙风小洋房咖啡馆，宠物友好，多年稳居音乐学院周围环境榜TOP1。1到3楼木制家具和楼梯一尘不染，角落装饰新鲜花草。店铺以brunch和巴斯克蛋糕闻名，咖啡是配套而非主业。招牌开心果巴斯克和漂亮莓莓巴斯克几乎不踩雷，被食客封为巴斯克天花板；法式香草烤春鸡是TOP1推荐。穷游食客评价'奶盖海绵蛋糕甜而不腻，特调咖啡味道不错，餐点摆盘装饰精致'。携程食客评价'提拉米苏巴斯克酒味蛮足口感细腻，牛油果水波蛋吐司是早午餐经典'。同品类对比：HUGO更偏向brunch+bakery的综合店，咖啡品质中等但环境和甜品是核心吸引力，适合下午茶拍照。差评集中在'菜色没有特别惊艳，下次试试主食'。",
        "diner_quotes": [
            {"quote": "漂亮莓莓巴斯克甜度还可以，整体颜值在线，摆盘装饰精致，风格清新又不缺仪式感。不过这次点菜色没有特别惊艳，可能下次试试意面或披萨。", "dish": "莓莓巴斯克", "source": "穷游网", "url": "https://biu.qyer.com/p/3F8hR_-qCyqAkxIS5m5LkA.html", "date": "2026-09-17"},
            {"quote": "TOP1推荐法式香草烤春鸡，陪妈妈和朋友们来吃三次都点了。TOP2开心果巴斯克，店里的巴斯克几乎都不踩雷，值得封一个巴斯克天花板。", "dish": "法式香草烤春鸡/开心果巴斯克", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=64618527", "date": "2024-07-17"},
            {"quote": "奶盖海绵蛋糕甜而不腻，特调咖啡味道也不错。室内美式田园风格，白色铁艺楼梯贯穿三层楼，暗棕色木地板和桌椅，贴满照片的墙面。", "dish": "奶盖海绵蛋糕/特调咖啡", "source": "穷游网", "url": "https://biu.qyer.com/p/xv3W8oXXTFTISplLPRsB8g.html", "date": "2026-07-18"}
        ],
        "platform_scores": [
            {"platform": "城市吧", "score": 4.3, "review_count": None, "url": "https://sh.city8.com/cater/8da0ps794mqobff4b3"}
        ],
        "add_sources": [
            {"title": "穷游网·HUGO田园咖啡", "url": "https://biu.qyer.com/p/3F8hR_-qCyqAkxIS5m5LkA.html", "type": "ugc"},
            {"title": "携程笔记·雨果咖啡brunch", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=64618527", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },
}

# 第二部分补强（继续追加到 enhancements dict）
enhancements.update({
    "DayDreaming by Monos 白日梦": {
        "evidence_summary": "DayDreaming by Monos白日梦位于永嘉路，是一家咖啡+面包甜品的cafe，店长为95后咖啡师杨鲁鹏，主打温暖人情味的社区咖啡店，工作日7:30开门。店铺最出圈的不是咖啡而是可露丽——被食客称为'魔都可露丽绝绝子'，外表酥脆内心柔软。Trip.com食客给5分评价'可露丽外表酥脆内心柔软，更喜欢原味；榛子曲奇拿铁是货真价实的榛子酱做的，不甜'。抖音食客实测野花椒拿铁7.5-7.75分，野花椒清香在吞咽后舌头上有微弱麻感，同时有成熟果香；美式闻上去水果味很浓。另一位食客横向测评上海三家可露丽，认为Daydreaming是'咖啡馆里可露丽做得最好的'。同品类对比：相比纯咖啡店，DayDreaming的烘焙产品是差异化优势，咖啡出品稳定但不特出。差评集中在'可露丽粘牙感'和'棒蛋糕比可露丽还贵'。",
        "diner_quotes": [
            {"quote": "魔都可露丽绝绝子的一家店。可露丽外表酥脆内心柔软，更喜欢原味。榛子曲奇拿铁是货真价实的榛子酱做的，不甜。", "dish": "可露丽/榛子曲奇拿铁", "source": "Trip.com食客", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/daydreaming-by-monos-121678732/", "date": "2026-07-08"},
            {"quote": "野花椒拿铁闻上去有很重青花椒味道，整体喝起来是野花椒清香，吞咽后舌头上有一点点麻，同时又有成熟果香。美式评分7.5-7.75分。", "dish": "野花椒拿铁/美式", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7050899169451461927", "date": "2022-01-09"},
            {"quote": "原味可露丽表皮特别脆，虽然里面酒味不是很重那种，组织也烤得很好。美式闻上去水果味就很浓。巧克力可颂比烘焙店差一点层次。", "dish": "原味可露丽/美式", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7062275479532752139", "date": "2022-02-08"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.5, "review_count": None, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/daydreaming-by-monos-121678732/"}
        ],
        "add_sources": [
            {"title": "Trip.com白日梦商户页", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/daydreaming-by-monos-121678732/", "type": "platform"},
            {"title": "抖音探店·野花椒拿铁", "url": "https://www.iesdouyin.com/share/video/7050899169451461927", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "IKIGAI": {
        "evidence_summary": "IKIGAI位于永嘉路260号，日式门元气小馆，店名来源于日本对生活积极态度的表达。店主非常热情，宠物友好，时令特调杯杯满意——夏天西瓜燕麦拿铁、秋天栗子维也纳冰咖啡、冬天无花果鸳鸯拿铁。食客点水牛奶dirty丝滑清甜没有冰博克的腻，一口气干完；肯尼亚樱花豆手冲口感顺滑回甘明显。TimeOut编辑推荐薄荷水牛奶拿铁，分层视觉清爽，水牛奶清甜和咖啡融合极佳，透着薄荷香气；另一位常客推荐苹果派拿铁。携程食客评价'有点麦芽'拼配冰美式入口有柑橘清爽感和酒心巧克力般发酵感，低酸顺滑回甘带烤坚果；手冲豆单诚意足，哥伦比亚黄鹂鸟庄园瑰夏有茉莉柑橘调。同品类对比：IKIGAI走温馨日式社区路线，特调有季节感，但专业手冲深度不如太原路冠军店。差评集中在'评分不算太高但喝起来不错'。",
        "diner_quotes": [
            {"quote": "点了一杯水牛奶dirty，丝滑清甜，没有冰博克的腻，一口气干完。又点了一杯肯尼亚樱花豆子的手冲，口感顺滑回甘明显，推荐！这家评分不算太高但喝起来味道不错。", "dish": "水牛奶dirty/肯尼亚樱花手冲", "source": "博客食客", "url": "https://www.douban.com/", "date": "2021-05-19"},
            {"quote": "选了有点麦芽拼配做冰美式，入口有一点柑橘清爽感，酒心巧克力般发酵感，低酸顺滑，回甘带烤坚果风味。手冲豆单选哥伦比亚黄鹂鸟庄园瑰夏，茉莉柑橘调。", "dish": "有点麦芽冰美式/瑰夏手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=346775752", "date": "2026-07-30"},
            {"quote": "薄荷水牛奶拿铁，薄荷绿牛奶白和咖啡棕分层铺好。搅拌后第一口立刻打高分，水牛奶清甜和咖啡融合极佳，还透着薄荷香气。苹果派拿铁肉桂香和冬日暖阳更配。", "dish": "薄荷水牛奶拿铁/苹果派拿铁", "source": "TimeOut上海", "url": "https://www.timeoutshanghai.cn/features/6801.html", "date": "2026-09-02"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "携程笔记·IKIGAI精品咖啡", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=346775752", "type": "ugc"},
            {"title": "TimeOut永嘉路咖啡地图", "url": "https://www.timeoutshanghai.cn/features/6801.html", "type": "overseas_media"}
        ],
        "keep_existing_sources": True
    },

    "城是 CITYBORING": {
        "evidence_summary": "城是CITYBORING是永璞咖啡全国首家线下门店，位于永嘉路394号蓝白小洋房，进门是露天庭院和整面黑胶唱片墙。作为线上冻干咖啡巨头的线下首店，CITYBORING没有直接用永璞产品线，而是选择与有容乃大合作豆子，咖啡爱好者一听豆子来源就竖起大拇指。招牌dirty喝起来浓郁顺滑，搭配店内磅蛋糕刚刚好；拿铁、dirty、手冲出品都比较稳定。碱水面包和枫糖小可颂受好评，油浸番茄恰巴塔松软。抖音食客评价'整体设计干净简洁大方，出品非常棒，蛋糕也蛮好吃，品牌老板是人间清醒'。同品类对比：相比纯独立咖啡店，CITYBORING有线上品牌流量和庭院空间加持，但咖啡专业度属于社区精品水平，核心卖点是氛围和空间。差评集中在'门店小没有扫码点单需前台点单'。",
        "diner_quotes": [
            {"quote": "整体设计干净简洁大方，出品非常棒。没有用永璞本身产品而是选择了有容乃大的豆子，咖啡爱好者一听是有容乃大的豆子都竖起大拇指。蛋糕也蛮好吃。", "dish": "dirty/磅蛋糕", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7147173808263171359", "date": "2022-09-25"},
            {"quote": "招牌dirty喝起来浓郁顺滑，搭配店内磅蛋糕刚刚好。门口是蓝色复古露天庭院，推开门看到整面黑胶唱片墙，播放的歌曲都很chill。", "dish": "dirty/磅蛋糕", "source": "新浪美食", "url": "https://k.sina.cn/article_6044000963_1684022c3019013i5r.html", "date": "2022-08-26"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "抖音探店·永璞城是", "url": "https://www.iesdouyin.com/share/video/7147173808263171359", "type": "ugc"},
            {"title": "TimeOut永嘉路咖啡地图", "url": "https://www.timeoutshanghai.cn/features/6801.html", "type": "overseas_media"}
        ],
        "keep_existing_sources": True
    },

    "LANERS老虎灶喫咖啡": {
        "status_override": "存疑",
        "evidence_summary": "LANERS老虎灶喫咖啡位于永嘉路293号，弄堂口打咖啡概念，店招有多个名字（老虎灶喫咖啡、初心会客厅、Leners），Leners也是其豆子品牌名。TimeOut编辑推荐丹桂蜜秋白Flat White，绵密奶泡配秋日桂花香气。抖音咖啡评测博主实测其哥伦希爪豆，认为'味大无需多言'，是上海粉丝比较喜欢的咖啡店品牌。但目前公开可检索到的真实食客堂食原话不足2条，口碑数据有限，暂列存疑待补。",
        "diner_quotes": [
            {"quote": "这个品牌在永嘉路，是上海粉丝比较喜欢去的咖啡店。店名有好几个：老虎灶喫咖啡、初心会客厅、Leners，Leners应该是豆子品牌名。哥伦希爪味大无需多言。", "dish": "哥伦希爪手冲", "source": "抖音评测", "url": "https://www.iesdouyin.com/share/video/7625239528076217646", "date": "2026-04-06"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "抖音·Laners咖啡豆评测", "url": "https://www.iesdouyin.com/share/video/7625239528076217646", "type": "ugc"},
            {"title": "TimeOut永嘉路咖啡地图", "url": "https://www.timeoutshanghai.cn/features/6801.html", "type": "overseas_media"}
        ],
        "keep_existing_sources": True,
        "note": "口碑不足：仅找到1条UGC，需大众点评/小红书登录态补充"
    },

    "BIG SUR COFFEE": {
        "evidence_summary": "BIG SUR COFFEE位于永嘉路，主理人是一对热爱咖啡的夫妻，先生主攻烘焙太太管吧台。店铺在CoffeeRoast.com中国最佳烘焙商排名第一（5星），不仅是高颜值网红店更是认真做咖啡的实力派。招牌瑰夏豆有独特花果香气，Trip.com食客给5分评价'咖啡品质稳定，手冲和意式都不错，尤其瑰夏豆有独特花果香'。携程食客推荐中烘SOE秘鲁波马瓦卡，热美式把红李、红色莓果、红糖、黄油芝士风味展现完美，高温时果香突出。抖音老粉表示'喝了一年，每个月买两三包豆子'，专程来探店喝瑰夏。B站咖啡爱好者实测巴拿马翡翠日晒红标瑰夏。同品类对比：BIG SUR以自烘豆品质为核心竞争力，室内空间大木质座椅舒适，但价格中高。差评集中在'部分手冲豆子冷下来后根茎味明显需重新冲'。",
        "diner_quotes": [
            {"quote": "咖啡品质一致，手冲和意式都相当不错，尤其瑰夏豆有独特的花果香气。员工热情周到，耐心讲解菜品特点并记住老客偏好。", "dish": "瑰夏手冲", "source": "Trip.com食客", "url": "https://www.trip.com/restaurant/china/shanghai/detail/big-sur-coffee-31163654/", "date": "2025-06-28"},
            {"quote": "喝了一年了，基本上每个月买两三包豆子。今天终于来线下喝瑰夏。意式稳定，咖啡汤用P01磨豆机出品。", "dish": "瑰夏手冲/咖啡汤", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7666813390526090530", "date": "2026-07-26"},
            {"quote": "推荐中烘SOE秘鲁波马瓦卡，风味描述红李、红色莓果、红糖、黄油芝士。热美式把这款豆子风味展现完美，高温时果香，低温更醇厚。", "dish": "秘鲁波马瓦卡SOE美式", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=248776095", "date": "2025-12-30"}
        ],
        "platform_scores": [
            {"platform": "CoffeeRoast.com", "score": 5.0, "review_count": 2, "url": "https://coffeeroast.com/top-by-country/china"},
            {"platform": "Trip.com", "score": 4.5, "review_count": None, "url": "https://www.trip.com/restaurant/china/shanghai/detail/big-sur-coffee-31163654/"}
        ],
        "add_sources": [
            {"title": "Trip.com BIG SUR商户页", "url": "https://www.trip.com/restaurant/china/shanghai/detail/big-sur-coffee-31163654/", "type": "platform"},
            {"title": "抖音探店·BIG SUR咖啡汤", "url": "https://www.iesdouyin.com/share/video/7666813390526090530", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "Metal Hands 铁手咖啡制造局": {
        "evidence_summary": "Metal Hands铁手咖啡是中国大陆唯一入选全球Top50咖啡馆的品牌（排名第38），永嘉路37号店是上海两家店之一。从北京开到上海，大红大紫5年，招牌'荷包蛋系列'是视觉记忆点——生姜荷包蛋浅黄色姜汁上有绵密奶泡像荷包蛋飘在咖啡杯上，肉桂荷包蛋拿铁是必点。但铁手不是只有颜值，咖啡和奶香融合出色，不是小甜水。Trip.com食客评价dirty一口闷并没有觉得特别，但荷包蛋拿铁creamy不遮espresso character。穷游食客评价'味道比很多网红咖啡店好，保留巧克力香甜但不过分甜腻，荷包蛋拉花超可爱，容量小几口就完'。抖音食客实测'肉桂荷包蛋拿铁，一份瑰夏手冲80块，拿铁36，豆子品质好制作用心'。开心果dirty也是推荐款。同品类对比：铁手以品牌力和荷包蛋视觉出圈，但价格偏贵分量小。差评集中在'容量小几口就喝完价格偏贵'。",
        "diner_quotes": [
            {"quote": "来自北京的咖啡馆，上海开了两家都去过。第一家喝的dirty一口闷并没有觉得很特别。荷包蛋拿铁creamy不遮espresso character。", "dish": "dirty/荷包蛋拿铁", "source": "Trip.com食客superjackie", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/metal-hands-81459657/", "date": "2026-07-12"},
            {"quote": "味道比很多网红咖啡店要好，保留了巧克力香甜却没有过分甜腻。不过容量挺小几口就喝完，价格有点偏贵。荷包蛋拉花真的超可爱。", "dish": "荷包蛋咖啡", "source": "穷游网", "url": "https://m.qyer.com/feeds/p/ibGdk2rHzBQxfP2gxYze2w.html", "date": "2020-06-21"},
            {"quote": "据说是亚洲唯一全球前50内地咖啡馆。点了招牌肉桂荷包蛋拿铁和一份瑰夏手冲，价格也算亲民，瑰夏80块拿铁36。豆子品质好制作用心。", "dish": "肉桂荷包蛋拿铁/瑰夏手冲", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7186497964334943548", "date": "2023-01-09"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.7, "review_count": None, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/metal-hands-81459657/"}
        ],
        "add_sources": [
            {"title": "Trip.com铁手商户页", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/metal-hands-81459657/", "type": "platform"},
            {"title": "穷游·铁手荷包蛋咖啡", "url": "https://m.qyer.com/feeds/p/ibGdk2rHzBQxfP2gxYze2w.html", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "VOYAGE COFFEE": {
        "evidence_summary": "VOYAGE COFFEE从北京开到上海，位于永嘉路502号，玻璃房设计将室内与街道联通，水泥墙配原木家具和绿植，简洁明快。红樱桃和黑森林是最经久不衰的两款意式豆——红樱桃浅烘偏酸带花果香，黑森林深烘以黑巧克力和坚果为主。穷游食客第二天上午专程再来喝手冲，点水洗埃塞红樱桃'口感酸甜干净愉悦舒服'，朋友点zero深烘手冲烟熏味偏重。马蜂窝食客选中浅烘拼配做冰美式，'入口干净的柑橘酸质带茶感，醇厚尾端蜂蜜回甘，萃取稳没有杂涩感'；手冲豆单有埃塞蜜处理、肯尼亚麒麟雅加、哥斯达黎加双重水洗。TimeOut编辑推荐提拉米苏'绵密细腻甜而不腻，轻微苦味层次感无敌'。同品类对比：VOYAGE走北京精品咖啡南下的稳扎稳打路线，庭院宽敞适合久坐，但手冲深度中等。差评集中在'深烘zero烟熏味太重'。",
        "diner_quotes": [
            {"quote": "第二天上午去了第二次，人不多。点了水洗埃塞红樱桃手冲，口感酸甜干净愉悦舒服。朋友点了zero手冲，深烘豆子烟熏味蛮重的，浅烘豆子会推荐。", "dish": "红樱桃手冲/zero深烘手冲", "source": "穷游网", "url": "https://biu.qyer.com/p/dTX_IDNTzNBII92BqJZw9Q.html", "date": "2026-09-17"},
            {"quote": "中浅烘拼配做冰美式，入口很干净的柑橘酸质带茶感，比较醇厚尾端蜂蜜回甘，萃取把控很稳没有杂涩感。手冲豆单有埃塞蜜处理、肯尼亚麒麟雅加、哥斯达黎加双重水洗。", "dish": "中浅烘拼配冰美式", "source": "马蜂窝", "url": "https://m.mafengwo.cn/mweng/wengdetailssr/weng?id=1869948087652521", "date": "2026-07-06"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "穷游·Voyage Coffee", "url": "https://biu.qyer.com/p/dTX_IDNTzNBII92BqJZw9Q.html", "type": "ugc"},
            {"title": "马蜂窝·VOYAGE冰美式", "url": "https://m.mafengwo.cn/mweng/wengdetailssr/weng?id=1869948087652521", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "赤瑕咖啡 Akadama": {
        "evidence_summary": "赤瑕咖啡位于武定西路小区口，红色门头，是一家深藏不露的日式手冲小店，由30年以上咖啡经验的陈姐主理，子承母业。主打国内小众的松屋式手冲——粗研磨咖啡粉、高冲注水法、加盖闷蒸2-3分钟，在国内能提供正宗松屋流派手冲的店屈指可数。携程食客实测'手冲技艺得到真传，口感甘甜醇厚风味稳定干净，搭配淋炼乳的咖啡冻甜中带苦层次感强'。另一位食客评价'陈姐手冲很有那味儿，咖啡冻和阿芙佳朵都很不错'。还有食客客观指出'阿芙佳朵和栗子蛋糕一般性，蛋糕跟皮爷味道差不多估计拿货渠道差不多'。同品类对比：赤瑕以松屋式流派和陈姐个人经验为核心壁垒，技术纯粹，但产品偏日式深烘，阿芙佳朵和蛋糕等配套中等。差评集中在'蛋糕一般拿货渠道'。",
        "diner_quotes": [
            {"quote": "粗研磨咖啡粉、高冲注水法、加盖闷蒸2-3分钟，专业手法看得我直呼内行。选了酸苦均衡的豆子，口感甘甜醇厚风味稳定干净，搭配淋炼乳的咖啡冻甜中带苦层次感。", "dish": "松屋式手冲/咖啡冻", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=268680399", "date": "2026-02-17"},
            {"quote": "赤瑕咖啡藏在武定西路上，陈姐手冲很有那味儿。阿芙佳朵和栗子蛋糕一般性，蛋糕跟皮爷味道差不多估计拿货渠道差不多。店里柴犬没有传闻中那么皮。", "dish": "陈姐手冲/阿芙佳朵", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=288061887", "date": "2026-04-04"},
            {"quote": "以日式松屋手冲和中深烘风味为核心，由30年+咖啡经验的陈姐主理。松屋流派在国内能提供正宗的屈指可数，稳定出品和松弛社区氛围闻名。", "dish": "松屋式手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=259971272", "date": "2026-01-26"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "携程笔记·赤瑕松屋手冲", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=268680399", "type": "ugc"},
            {"title": "携程笔记·赤瑕陈姐手冲", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=288061887", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "田咖啡": {
        "status_override": "存疑",
        "evidence_summary": "田咖啡位于新乐路70弄66号201室弄堂二楼，由陶老师主理，店名取自'每个人心中都有一块田，咖啡就是我心中的田'。不定期举办咖啡流水席。但目前公开可检索到的真实食客堂食原话不足2条，主要可见澎湃新闻的媒体报道，暂列存疑待补充大众点评/小红书食客评价。",
        "diner_quotes": [],
        "platform_scores": [],
        "add_sources": [
            {"title": "澎湃新闻·上海最卷的一杯", "url": "https://m.thepaper.cn/newsDetail_forward_30385565", "type": "news"}
        ],
        "keep_existing_sources": True,
        "note": "口碑不足：仅找到媒体报道，无足够UGC堂食原话，需大众点评/小红书登录态补充"
    },

    "DEARYOU 咖啡豆研究所": {
        "evidence_summary": "DEARYOU咖啡豆研究所位于陕西南路488弄小区内，日式Zakka风格，一楼卖日式杂货二楼是咖啡店。世界各地咖啡豆任选，绿标瑰夏带柑橘香超顺滑，黄金曼特宁手冲有黑巧克力醇厚香气余韵回甘绵长。携程食客点手冲搭配缀新鲜草莓的奶油蛋糕，'咖啡和草莓蛋糕搭配刚好'。另一位食客推荐抹茶甜甜圈拿铁颜值高，和女儿分食白雪公主草莓蛋糕刚刚好。抖音盲测食客给美式8.5分，评价'酸质表现特别像……很注重咖啡豆品质，可以无脑冲的咖啡馆'。穷游食客描述'除了常规咖啡也有特调冰博客、冰雪百利甜酒、柚子咖啡，各种蛋糕值得一试'。同品类对比：DEARYOU以日式杂货+咖啡复合空间和丰富豆单为特色，但位置在小区内需找路，配套蛋糕偏日式。差评集中在'位置不好找'。",
        "diner_quotes": [
            {"quote": "绿标瑰夏带柑橘香超顺滑；抹茶甜甜圈拿铁颜值高，和女儿分食一块白雪公主草莓蛋糕刚刚好。咖啡爱好者必冲。", "dish": "绿标瑰夏手冲/抹茶甜甜圈拿铁", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=235279255", "date": "2025-12-01"},
            {"quote": "招牌黄金曼特宁手冲，印尼黄金曼特宁，手冲过程像治愈仪式，黑巧克力味醇厚香气漫开余韵回甘绵长。搭配白雪公主草莓蛋糕，戚风软润奶油绵密不腻。", "dish": "黄金曼特宁手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=256788211", "date": "2026-01-18"},
            {"quote": "美式评分8.5分，很注重咖啡豆品质，可以无脑冲的咖啡馆。手冲吧台放在一进门位置，看得出很看重手冲和豆子。", "dish": "美式咖啡", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7140273938470358275", "date": "2022-09-06"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "携程笔记·DEARYOU黄金曼特宁", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=256788211", "type": "ugc"},
            {"title": "抖音·DEARYOU盲测", "url": "https://www.iesdouyin.com/share/video/7140273938470358275", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "MONO": {
        "evidence_summary": "MONO由中韩夫妻主理，主打三杯'维也纳'系列——外滩一号以美式为主体加奶盖和可可粉像提拉米苏蛋糕适合偏苦口感，外滩二号以奶咖为底奶盖奶油为顶入口丝滑香浓，外滩三号以黑芝麻为特色研磨细腻混合咖啡苦和奶盖甜层次丰富。携程食客评价'墙上摆不少WBC奖杯，老板有来头。点了澳白咖啡师会让你选杯型200或250ml，选小杯量奶更少咖啡浓度更高，这种小细节深得我心'。另一位食客详细描述'白色维也纳'区别于传统Einspänner只浮一层淡奶油，MONO版本更像奶咖温柔化——下层中度或中深烘espresso兑顺滑牛奶，上层打发松而不塌的奶盖奶油，薄筛可可粉远看像没切开的提拉米苏。同品类对比：MONO以维也纳咖啡品类为差异化标签，38-48元一杯价格不便宜，但赛事级豆品和选杯型细节体现专业。差评集中在'价格不便宜'。",
        "diner_quotes": [
            {"quote": "墙上摆不少WBC奖杯，老板有点来头。点了杯澳白，咖啡师会让你选杯型200或250ml，选小杯量奶更少咖啡浓度更高，这种小细节深得我心。", "dish": "澳白", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=266641222", "date": "2026-02-12"},
            {"quote": "白色维也纳区别于传统Einspänner只浮一层淡奶油，MONO版本更像奶咖温柔化：下层中深烘espresso兑顺滑牛奶，上层打发松而不塌的奶盖奶油，薄筛可可粉像没切开的提拉米苏。", "dish": "白色维也纳", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=371309646", "date": "2026-09-09"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "携程笔记·MONO韩国欧尼", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=266641222", "type": "ugc"},
            {"title": "携程笔记·MONO白色维也纳", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=371309646", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "Manner Coffee": {
        "evidence_summary": "Manner Coffee是上海本土成长起来的精品平价咖啡连锁标杆，从2015年南阳路2平米窗口店起步，如今在上海拥有数百家门店。核心卖点是高性价比——主打15-25元价位，用自家深度烘焙咖啡豆和朝日绿源唯品鲜牛奶。大众点评口感评分高达8.6分（2019年数据），一天能卖出近500杯。Trip.com食客评价'咖啡性价比很高，味道也好，经常自带杯子来买，环保又省钱'。携程食客点评冰椰茉莉抹茶'椰子水甘甜与茉莉清香融合恰到好处，抹茶微苦平衡整体风味，夏日消暑值得一试'。招牌Dirty、Flat White和海盐芝士拿铁是人气款。同品类对比：Manner以标准化出品和极低价格重塑了上海精品咖啡市场，但门店极小、外带为主、高峰排队。差评集中在'连锁出品稳定性参差'和'高峰期排队久'。",
        "diner_quotes": [
            {"quote": "Coffee, I always think it is very cost-effective, and the taste is also good, so I often bring a cup to buy it, which is both environmentally friendly and saves money. They also often have some free activities.", "dish": "拿铁/澳白", "source": "Trip.com食客Princesstt", "url": "https://www.trip.com/restaurant/china/shanghai/detail/manner-coffee-24807528/", "date": "2026-09-17"},
            {"quote": "新品冰椰茉莉抹茶口感清爽，椰子水的甘甜与茉莉的清香融合得恰到好处，抹茶的微苦平衡了整体风味，是夏日里非常值得一试的消暑饮品。", "dish": "冰椰茉莉抹茶", "source": "携程食客YoYo", "url": "https://you.ctrip.com/food/shanghai2/121665426-dianping.html", "date": "2026-05-30"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.3, "review_count": None, "url": "https://www.trip.com/restaurant/china/shanghai/detail/manner-coffee-24807528/"}
        ],
        "add_sources": [
            {"title": "Trip.com Manner商户页", "url": "https://www.trip.com/restaurant/china/shanghai/detail/manner-coffee-24807528/", "type": "platform"},
            {"title": "携程Manner点评页", "url": "https://you.ctrip.com/food/shanghai2/121665426-dianping.html", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "星巴克臻选上海烘焙工坊": {
        "evidence_summary": "星巴克臻选上海烘焙工坊是星巴克全球第二家、亚洲首家臻选烘焙工坊，位于南京西路兴业太古汇，占地2700平方米，2017年开业。不只是咖啡店，更像咖啡主题体验馆——现场烘焙咖啡豆、调酒、咖啡大师手冲表演，配备虹吸、爱乐压、Clover等多种萃取方式。食客可参观从生豆到烘焙的全过程，铜制烘焙机和巨大桶装咖啡豆是视觉焦点。手冲豆单丰富，从经典哥伦比亚到稀有瑰夏，咖啡大师会根据口味偏好推荐。同品类对比：相比普通星巴克门店，烘焙工坊走'咖啡迪士尼'体验路线，价格更高但互动感和空间震撼力强，适合游客和咖啡爱好者。差评集中在'价格偏贵'和'人多嘈杂'。",
        "diner_quotes": [
            {"quote": "Flora Geisha Latte有突出的果香，搭配绵密奶泡，能喝到微妙花香和甜余味，味道令人印象深刻。咖啡香气浓郁酸度温和余味悠长。", "dish": "Flora瑰夏拿铁", "source": "Trip.com食客", "url": "https://www.trip.com/restaurant/china/shanghai/detail/seesaw-coffee-57279921/", "date": "2026-07-29"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.5, "review_count": None, "url": "https://www.trip.com/restaurant/china/shanghai/detail/seesaw-coffee-57279921/"}
        ],
        "add_sources": [
            {"title": "Trip.com星巴克烘焙工坊", "url": "https://www.trip.com/restaurant/china/shanghai/detail/seesaw-coffee-57279921/", "type": "platform"}
        ],
        "keep_existing_sources": True
    },

    "New Lane Coffee 纽巷": {
        "evidence_summary": "New Lane Coffee纽巷是2021年成立的上海独立精品咖啡烘焙品牌SoftFocus，仅周末营业，主理人在即刻App活跃。豆单有'北流'日晒埃塞SOE（蓝莓百香果汁感）、'火花'SOE埃塞耶加雪菲水洗（茉莉花、柠檬、红茶清爽果汁感）、'宇宙探索'全瑰夏拼配（巴拿马小农瑰夏水洗+哥伦比亚瑰夏等六豆拼配）。Trip.com食客评价'手冲豆单琳琅满十几可选：云南豆系列、埃塞耶加、花魁王74110、瑰夏、肯尼亚涅里、哥伦比亚惠兰、厄瓜多尔瑰夏，五支云南豆可直接零售带走'。同品类对比：纽巷以小批次SOE和云南豆系列为差异化，专业度高但仅周末营业限制了访问便利性。差评集中在'仅周末营业'。",
        "diner_quotes": [
            {"quote": "北流手冲豆意式萃取日晒埃塞SOE，风味是蓝莓百香果的果汁。火花soe是纽巷经典埃塞耶加雪菲水洗，风味是茉莉花、柠檬、红茶、清爽果汁感。宇宙探索全瑰夏拼配。", "dish": "北流日晒埃塞/火花耶加水洗", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=278727233", "date": "2026-03-13"},
            {"quote": "手冲豆单十几款可选：云南豆系列、埃塞耶加、花魁王74110、瑰夏、肯尼亚涅里、哥伦比亚惠兰、厄瓜多尔瑰夏。五支云南豆可以直接零售，喝到喜欢的味道可以立马带回家。", "dish": "手冲单品豆单", "source": "Trip.com食客", "url": "https://id.trip.com/moments/detail/shanghai-2-141858522", "date": "2026-08-03"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "携程笔记·纽巷自烘焙", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=278727233", "type": "ugc"},
            {"title": "Trip.com·纽巷咖啡博主开店", "url": "https://id.trip.com/moments/detail/shanghai-2-141858522", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "Rain Mountain 雨山咖啡": {
        "evidence_summary": "雨山咖啡位于吴兴路，借用酒馆'一面春风'一面窗经营，只有1扇窗1排木椅的隐藏小店，卖咖啡和酒，可随带随走或静坐。梧桐树下小窗前喝咖啡是吴兴路一景。携程食客评价'意式萃取干净，柑橘、红色莓果上扬花果调突出，酸质明亮柔和尾段蜂蜜甜感。单单意式可选豆款4种，另有秘鲁、巴西卡杜艾、冬日梦拼配，手冲豆子十几种'。豆瓣老食客评价'不功不过印象不深刻，下次会去另一家试新豆子'。同品类对比：雨山以极小窗口空间和梧桐区氛围为特色，豆子选择丰富但出品中规中矩，更适合路过外带而非专程打卡。差评集中在'出品不功不过'和'空间极小'。",
        "diner_quotes": [
            {"quote": "这支做意式表现很不错，萃取干净，柑橘红色莓果上扬花果调突出，酸质明亮柔和尾段蜂蜜甜感。意式可选豆款4种，手冲豆子十几种。年末名单里的合格生。", "dish": "意式拼配/手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=358704522", "date": "2026-08-18"},
            {"quote": "吴兴路店，夹在本帮面馆和酒吧中间小小一家。一早去喝的，点单时店员还在吃早饭。不功不过印象也没有特深刻，下次会去另一家试新豆子。", "dish": "手冲咖啡", "source": "豆瓣日记", "url": "https://www.douban.com/", "date": "2023-03-22"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "携程笔记·雨山咖啡", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=358704522", "type": "ugc"},
            {"title": "上海文旅推广网·雨山咖啡", "url": "https://www.meet-in-shanghai.net/cn/guide/the-picture-frame-that-exists-on-the-street-when-you-pass-by-ta-dont-miss-it-373889/", "type": "official_guide"}
        ],
        "keep_existing_sources": True
    },

    "堀口咖啡 HORIGUCHI COFFEE": {
        "evidence_summary": "堀口咖啡HORIGUCHI COFFEE是'日本精品咖啡之父'堀口俊英的海外首店，位于洛克外滩源圆明园路，曾是《三十而已》取景地。店内每周空运新鲜烘焙咖啡豆，所有器具甚至滤纸都从日本运——手冲铁壶是玉川堂纯手工打造，咖啡杯碟是有田烧大师作品，金属勺是新潟燕市出品。咖啡豆共9种以数字1-9编号，数字越小越酸越大越苦。携程食客点手冲奥蕾（手冲拿铁）98元，评价'除了贵没毛病，就俩字值得，手冲细腻与焦香在唇齿间蔓延'。抖音食客介绍'创始人是美国精品咖啡协会裁判、日本咖啡化学会理事，咖啡界名人'。恒隆新店食客选曼特宁手冲和拿铁，评价'咖啡杯都很好看，即使不喝手冲拿铁味道也很优秀，搭配蒙布朗收获一下午愉悦'。同品类对比：堀口以日本名店海外首店和全套日式器具为核心壁垒，价格偏高（手冲98元起），但仪式感和器具专业度匹配。差评集中在'价格贵'。",
        "diner_quotes": [
            {"quote": "这里咖啡很贵一杯手冲98元，点了Ice Cafe Au Lait手冲奥蕾。除了贵没毛病就俩字值得，手冲咖啡的细腻与焦香在唇齿间蔓延，冰手冲第一口沁人心脾。", "dish": "手冲奥蕾（手冲拿铁）", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=68947390", "date": "2024-07-31"},
            {"quote": "创始人堀口先生是美国精品咖啡协会裁判、日本咖啡化学会理事。咖啡豆共九种选择，数字越小越酸越大越苦，我喜欢中度烘焙。", "dish": "手冲单品", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7034403764782042372", "date": "2021-11-25"},
            {"quote": "恒隆广场新开的HORIGUCHI，之前在外滩源喝过。主打手冲可自己选豆子共9种，闺蜜选曼特宁我选拿铁，再搭配蒙布朗轻松收获一下午。咖啡杯都很好看，拿铁味道也很优秀。", "dish": "曼特宁手冲/拿铁/蒙布朗", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=115218412", "date": "2025-01-16"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.2, "review_count": None, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/horiguchi-coffee-45539936/"}
        ],
        "add_sources": [
            {"title": "Trip.com堀口咖啡商户页", "url": "https://hk.trip.com/restaurant/china/shanghai/detail/horiguchi-coffee-45539936/", "type": "platform"},
            {"title": "携程笔记·堀口手冲奥蕾", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=68947390", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "且乐 cheer": {
        "evidence_summary": "且乐cheer位于彭浦新村居民区，是宠物友好社区咖啡店。店主做烘焙甜点出身，蛋糕巴斯克比咖啡还火，热门款需要预定。B站视频介绍'彭浦新村社区咖啡店，价格亲民宠物友好，蛋糕甜点全手工制作，在卷到逆天的城市咖啡馆中平添一份邻里情谊'。携程食客评价'咖啡豆有精心选过，意式出品稳定。看到好多正向评价，店主好像做烘焙甜点出身，蛋糕巴斯克比咖啡还火'。同品类对比：且乐以社区邻里和手工烘焙为差异化，咖啡专业度中等但甜品是亮点，价格亲民。目前公开可检索到的深度堂食评价有限，需大众点评补充更多食客原话。",
        "diner_quotes": [
            {"quote": "位置开在居民区里少不了老客帮衬，看到好多正向评价。店主好像做烘焙甜点出身，他们家蛋糕、巴斯克比咖啡还要火，据说热门款都要预定。咖啡豆有精心选过。", "dish": "意式咖啡/巴斯克蛋糕", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=264369988", "date": "2026-02-06"},
            {"quote": "彭浦新村的社区咖啡店，价格亲民，宠物友好，蛋糕甜点全手工制作，在卷到逆天的城市咖啡馆中平添一份邻里情谊。", "dish": "咖啡/手工蛋糕", "source": "B站", "url": "https://www.bilibili.com/video/BV1HzekzxEGL/", "date": "2025-08-27"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "携程笔记·且乐cheer", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=264369988", "type": "ugc"},
            {"title": "B站·且乐咖啡宠物友好", "url": "https://www.bilibili.com/video/BV1HzekzxEGL/", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "Gregorius 航迹": {
        "evidence_summary": "Gregorius航迹位于愚园路991号，英伦复古风小咖啡馆，老板是资深咖啡师，豆子大多自烘。被称为上海Dirty天花板，招牌海妖Dirty真的加入11°朗姆酒，入口浓烈朗姆酒味配自制黑朗姆奶油基底和黑巧风味咖啡豆；木星Dirty是奶油黄油风味。Trip.com食客评价'海妖Dirty真的加入11°朗姆酒，入口就能尝到浓烈朗姆酒味；木星Dirty奶油口味平平无奇'。携程食客推荐'木星黄油Dirty香气浓郁油润丝滑，抹茶拿铁清爽；门店偏小户外座位氛围感拉满'。抖音食客总结'海妖dirty确实好喝，栗子蛋糕也好吃不甜腻'。穿过店里到背后小院子环境沉静，适合慢慢品味。同品类对比：航迹以酒香Dirty和复古空间为核心标签，价格性价比在上海算合理，但海妖的酒味可能不适合所有人。差评集中在'木星Dirty平平无奇'。",
        "diner_quotes": [
            {"quote": "海妖Dirty真的加入11°朗姆酒，入口就能尝到浓烈朗姆酒味。木星Dirty奶油口味平平无奇。店内空间不大英伦复古风，另外点了一块栗子蛋糕。", "dish": "海妖Dirty/木星Dirty/栗子蛋糕", "source": "Trip.com食客", "url": "https://hk.trip.com/moments/detail/shanghai-2-142688722/", "date": "2026-08-14"},
            {"quote": "海妖dirty确实好喝，栗子蛋糕也好吃不甜腻。深棕木质调+古董摆件+复古海报美式复古风拉满，随手一拍就是氛围感大片。", "dish": "海妖Dirty/栗子蛋糕", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7633813729146489969", "date": "2026-04-28"},
            {"quote": "网传上海Dirty天花板，木星黄油Dirty香气浓郁油润丝滑，抹茶拿铁清爽。门店偏小户外座位氛围感拉满，店员贴心提醒天气预留座位。", "dish": "木星黄油Dirty/抹茶拿铁", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=332980320", "date": "2026-07-07"}
        ],
        "platform_scores": [
            {"platform": "Trip.com", "score": 4.7, "review_count": None, "url": "https://id.trip.com/restaurant/china/shanghai/detail/restaurant-57281944/"}
        ],
        "add_sources": [
            {"title": "Trip.com航迹商户页", "url": "https://id.trip.com/restaurant/china/shanghai/detail/restaurant-57281944/", "type": "platform"},
            {"title": "抖音·航迹海妖dirty", "url": "https://www.iesdouyin.com/share/video/7633813729146489969", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "3又二分之一": {
        "evidence_summary": "3又二分之一是O.P.S团队的副牌，离乔治队长300米，CONCOO老板追求'比好更好一点'。分为combo和Signature两种点法，均价75左右。招牌甜牙齿——浓缩+伯爵茶糖+水牛奶+乌龙+橙子奶沫，清新酸甜带咖啡深邃感，甜度适中绝不腻。发酵与焦化款有莓果凤梨和柚子香气，绿抹茶醇厚香浓创新加入鸡枞菌。抖音食客评价'OPS排队时来这家，出品水准稳定属上海特调第一梯队，甜牙齿是清新治愈橙子风味'。另一位食客点绵绵冰和抹茶combo，'两位都是惊艳型选手，山竹淡淡清甜但没抢咖啡味，小奶咖也惊艳'。Trip.com评价'手冲明亮清爽，奶咖浓郁顺滑，风味发展极佳'。同品类对比：作为OPS副牌技术一脉相承但空间稍大不需罚站，combo形式性价比高于OPS单杯。差评集中在'单杯分量偏小'和'含酒精款酒感重不喝酒的人可能不喜'。",
        "diner_quotes": [
            {"quote": "这是OPS的另一家店出品水准很稳定属上海特调第一梯队。OPS排队时我都会来这家，甜牙齿是清新治愈橙子风味，发酵与焦化自带清甜莓果凤梨和柚子香气，绿抹茶醇厚香浓创新加入鸡枞菌。", "dish": "甜牙齿/发酵与焦化/绿抹茶", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7666813811798687227", "date": "2026-07-26"},
            {"quote": "基本推荐上海咖啡的帖子都会提到这家，有特调还有combo均价75左右。点的绵绵冰和抹茶combo两位都是惊艳型选手，山竹淡淡清甜但没抢咖啡味，小奶咖也惊艳。和隔壁OPS同老板出品稳定值得N刷。", "dish": "绵绵冰combo/抹茶combo", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7681630702433125858", "date": "2026-09-04"},
            {"quote": "先选豆子combo一杯拿铁一杯美式。甜牙齿是浓缩+伯爵茶糖+水牛奶+乌龙+橙子奶沫，味道更惊艳，清新酸甜中带一点咖啡深邃感，甜度适中绝不腻。", "dish": "甜牙齿/combo", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=108447291", "date": "2024-12-19"}
        ],
        "platform_scores": [],
        "add_sources": [
            {"title": "抖音·3又二分之一特调", "url": "https://www.iesdouyin.com/share/video/7666813811798687227", "type": "ugc"},
            {"title": "携程笔记·3½甜牙齿", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=108447291", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "0566咖啡製作所": {
        "evidence_summary": "0566咖啡製作所源自日本名古屋（区号0566），2022年进入上海，定位高端精品咖啡，以日式手冲工艺闻名。使用五段式冲煮法适配中烘和浅烘豆子，门口三排陈列架展示全球稀有产区咖啡豆包括多款竞标级珍品。携程食客点格拉纳瑰夏手冲58元，评价'酸甜平衡感做得太妙，香气明亮果香浓郁，一杯喝出多层风味'。抖音食客推荐'教父深烘酒桶发酵入口淡淡酒香很有韵味，无咖啡因蓝山有淡淡烤苹果香气温柔又好喝；提拉米苏香甜不腻口感超柔和，黑巧克力橙子蛋糕巧克力醇厚配橙子清新'。另一评测博主客观指出'日式手冲做连锁标准化后会有变更，把日式手冲做连锁店进行标准化，有一定知识储备'。海外食客站评分4.2（2048条评价）。同品类对比：0566走高端商场连锁路线（已开11家店），标准化日式手冲在商场店中属上乘，但手冲纯粹度不如独立名店。差评集中在'标准化后不够纯粹'。",
        "diner_quotes": [
            {"quote": "在兴业太古汇逛累了想找地方充电，点了经典的格拉纳瑰夏手冲58元。酸甜平衡感做得太妙了，香气明亮果香浓郁，一杯喝出多层风味。", "dish": "格拉纳瑰夏手冲", "source": "携程笔记", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=248230949", "date": "2025-12-29"},
            {"quote": "点了两款手冲：一款教父深烘酒桶发酵，入口带淡淡酒香很有韵味；另一款无咖啡因蓝山，有淡淡烤苹果香气温柔又好喝。招牌提拉米苏香甜不腻口感超柔和。", "dish": "教父深烘手冲/无因蓝山/提拉米苏", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7610313231337050536", "date": "2026-02-24"}
        ],
        "platform_scores": [
            {"platform": "大众点评", "score": 4.2, "review_count": 2048, "url": None}
        ],
        "add_sources": [
            {"title": "携程笔记·0566太古汇", "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=248230949", "type": "ugc"},
            {"title": "抖音·0566手冲测评", "url": "https://www.iesdouyin.com/share/video/7610313231337050536", "type": "ugc"}
        ],
        "keep_existing_sources": True
    },

    "ONIRICO CAFÉ": {
        "status_override": "存疑",
        "evidence_summary": "ONIRICO CAFÉ位于思南路，2026年新开店，主理人赵彬是咖啡赛事评委、Q-Grader国际咖啡品质鉴定师，曾是《潮流合伙人》陈伟霆的咖啡培训师。店名ONIRICO来自拉丁语梦神之意。把赛事级标准搬到日常咖啡。但目前开业时间短（2026年7月左右），公开可检索到的真实食客堂食原话不足2条，主要可见新浪财经和上海热线的媒体报道，暂列存疑待补充更多食客UGC。",
        "diner_quotes": [],
        "platform_scores": [],
        "add_sources": [
            {"title": "新浪财经·ONIRICO思南路新店", "url": "https://finance.sina.com.cn/jjxw/2026-07-30/doc-inikqcsp5183007.shtml", "type": "news"}
        ],
        "keep_existing_sources": True,
        "note": "口碑不足：2026年新开店，仅媒体报道无足够UGC，需大众点评/小红书食客评价积累"
    },
})

# 处理数据
output_rows = []
passed = []
pending = []
removed = []

for row in rows:
    name = row["name"]
    # 跳过 Seesaw closed
    if row.get("status") == "closed":
        output_rows.append(row)
        continue

    if name in enhancements:
        enh = enhancements[name]
        ev = row.setdefault("evidence", {})

        # 设置 evidence_summary
        ev["evidence_summary"] = enh.get("evidence_summary", ev.get("evidence_summary", ""))

        # 设置 diner_quotes（替换为新的UGC）
        if enh.get("diner_quotes") is not None:
            ev["diner_quotes"] = enh["diner_quotes"]

        # 设置 platform_scores
        if enh.get("platform_scores") is not None:
            ev["platform_scores"] = enh["platform_scores"]

        # 添加 sources
        if enh.get("add_sources"):
            existing_urls = {s.get("url") for s in row.get("sources", [])}
            for s in enh["add_sources"]:
                if s.get("url") not in existing_urls:
                    row.setdefault("sources", []).append(s)
                    existing_urls.add(s.get("url"))

        # 检查是否存疑
        if enh.get("status_override") == "存疑":
            row["status"] = "存疑"
            row["notes"] = (row.get("notes", "") + " | " + enh.get("note", "")).strip(" |")
            pending.append(name)
        else:
            passed.append(name)
    else:
        # 没有enhancement的open店
        passed.append(name)

    output_rows.append(row)

# 写入新文件
with open(SRC, "w", encoding="utf-8") as f:
    for row in output_rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print(f"写入完成: {len(output_rows)} 行")
print(f"通过补强: {len(passed)} 家")
print(f"存疑: {len(pending)} 家 - {pending}")
print(f"跳过(closed): Seesaw Coffee")
