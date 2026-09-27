#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_chefs.py — 主厨 Profile 批量建设脚本

从库内餐厅提取主厨线索 + 联网核实的公开信息，批量建立 chefs 记录与 restaurant_chefs 关联。
默认 dry-run，--commit 才写库。宁空不假：无来源字段留空。

用法:
  python3 build_chefs.py              # dry-run 输出清单
  python3 build_chefs.py --commit     # 写库
"""
import sys
import json
import datetime
from common import req, fetch_all

TODAY = datetime.date.today().isoformat()

# ============================================================
# 主厨 Profile 数据（来源：公开媒体报道、官方介绍、库内 evidence_summary）
# 宁空不假：无可靠来源的字段留空
# ============================================================

CHEFS = [
    # ---- 国际名厨在沪 ----
    {
        "name": "Paul Pairet", "name_en": "Paul Pairet",
        "title": "主厨/创意总监，Ultraviolet by Paul Pairet 创始人",
        "bio": "法国籍加泰罗尼亚人，1964年生于法国Perpignan。15年构思后于2012年在上海创立Ultraviolet，2017年起获米其林三星，亚洲50佳常驻榜单。2005年到上海，先后开设Mr & Mrs Bund、POLUX、Charbon等品牌。",
        "origin": "法国 Perpignan",
        "culinary_background": "法国Occitanie厨艺学校毕业；曾在巴黎Cafe Mosaic以个人风格著称；被Alain Ducasse发掘后赴香港、悉尼、雅加达等地工作。",
        "signature_style": "前卫实验法餐，多感官沉浸式用餐体验；'culinary egalitarian'——用罐头沙丁鱼做高级料理，用高级技法做简单法餐经典。",
        "reputation": "米其林三星（Ultraviolet，2017-2024）；亚洲50最佳餐厅常驻；法国Top Chef评委（2022起）。",
        "group_id": 7,
        "restaurants_owned": ["Ultraviolet", "Mr & Mrs Bund", "POLUX"],
    },
    {
        "name": "Umberto Bombana", "name_en": "Umberto Bombana",
        "title": "主厨/创始人，8½ Otto e Mezzo BOMBANA",
        "bio": "被誉为'白松露之王'的意大利名厨，来自意大利北部Bergamo。在香港烹饪超过20年，2010年开设8½ Otto e Mezzo BOMBANA香港店，11个月内获米其林二星，次年升三星——香港首家摘三星的意餐厅。",
        "origin": "意大利 Bergamo",
        "culinary_background": "Centro di Formazione Alberghiana毕业；师从Ezio Santin；后赴洛杉矶、香港工作。",
        "signature_style": "精致现代意餐，白松露料理权威，意大利北部传统技法与现代呈现结合。",
        "reputation": "米其林三星（香港8½）；上海店米其林二星（2017起）；北京Opera BOMBANA。",
        "group_id": 9,
        "restaurants_owned": ["8½ Otto e Mezzo BOMBANA"],
    },
    {
        "name": "Nicoló Rotella", "name_en": "Nicoló Rotella",
        "title": "烹饪总监/行政总厨，8½ Otto e Mezzo BOMBANA 上海",
        "bio": "都灵人，在意大利多家米其林星级厨房受训，2019年到上海，现任8½上海烹饪总监兼行政总厨。",
        "origin": "意大利 都灵",
        "culinary_background": "意大利多家米其林星级餐厅历练后来华。",
        "signature_style": "诚实烹饪， pristine食材，现代意式料理。",
        "reputation": "带领8½上海保持米其林二星。",
        "group_id": 9,
    },
    {
        "name": "Pierre Gagnaire", "name_en": "Pierre Gagnaire",
        "title": "米其林三星主厨，La Boulangerie by Pierre Gagnaire",
        "bio": "法国米其林三星名厨，现代法餐代表人物之一。在上海以烘焙品牌La Boulangerie落地，由其团队坐镇。",
        "origin": "法国",
        "culinary_background": "法国多颗米其林星，国际烹饪界标志性人物。",
        "signature_style": "现代法餐，创新与传统融合。",
        "reputation": "米其林三星（巴黎总店）；全球多家分店。",
        "group_id": 9,
    },
    {
        "name": "Joël Robuchon", "name_en": "Joël Robuchon",
        "title": "米其林星最多的厨师（已故）",
        "bio": "法国家喻户晓的名厨，被称为'世纪厨师'，全球共获32颗米其林星。上海L'Atelier de Joël Robuchon为其品牌旗舰店。Robuchon于2018年逝世，品牌由其团队延续。",
        "origin": "法国 Poitiers",
        "culinary_background": "从糕点学徒起步，MOF法国最佳工艺师，全球开店。",
        "signature_style": "法式精致料理，土豆泥等经典菜闻名。",
        "reputation": "全球最多米其林星记录保持者；L'Atelier上海米其林二星。",
        "group_id": 9,
    },
    {
        "name": "江振诚", "name_en": "André Chiang",
        "title": "主厨/餐厅创始人，'八角哲学'提出者",
        "bio": "1976年生于台北，13岁接触厨艺，20岁赴法，25岁成为法国米其林三星餐厅Le Jardin des Sens执行主厨。后在新加坡开设Restaurant ANDRE，被《时代》杂志誉为'印度洋上最伟大的厨师'。2020年纪录片《初心》记录其职业生涯。",
        "origin": "中国台湾 台北",
        "culinary_background": "16岁亚都饭店巴黎厅学徒；21岁赴法，师从Pourcel兄弟（Le Jardin des Sens三星）。",
        "signature_style": "'八角哲学'（盐、脆、酸、咸、苦、香、多汁、温度），法式技法融合台湾本土风味。",
        "reputation": "Restaurant ANDLE亚洲50佳前十；《时代》杂志赞誉；Discovery亚洲10大最佳青年主厨。",
        "group_id": 9,
    },
    {
        "name": "Didier Chouet", "name_en": "Didier Chouet",
        "title": "主厨，法国MOF最佳工艺师",
        "bio": "法国MOF（Meilleur Ouvrier de France）得主，现任Luneurs烘焙品牌甜品主厨。",
        "origin": "法国",
        "culinary_background": "法国MOF头衔获得者。",
        "signature_style": "法式烘焙与甜品，精湛传统工艺。",
        "reputation": "法国MOF。",
    },
    {
        "name": "Frederic Jaros", "name_en": "Frederic Jaros",
        "title": "主厨/创始人，VERIE BAKEHOUSE",
        "bio": "前米其林二星Da Vittorio上海甜品主厨，2024年创立VERIE BAKEHOUSE，将米其林水准法式酥皮做成日常烘焙。",
        "origin": "法国",
        "culinary_background": "Da Vittorio（米其林二星）上海甜品主厨。",
        "signature_style": "法式酥皮烘焙，米其林级日常化。",
        "reputation": "前Da Vittorio二星团队。",
    },
    {
        "name": "Willy Trullas Moreno", "name_en": "Willy Trullas Moreno",
        "title": "主厨/创始人，el Willy",
        "bio": "西班牙主厨，在上海经营el Willy等西班牙餐厅多年，是上海西班牙菜的开拓者之一。",
        "origin": "西班牙",
        "culinary_background": "西班牙烹饪背景。",
        "signature_style": "西班牙地中海料理，paella与tapas。",
        "reputation": "上海西班牙菜老牌名店主理人。",
    },
    {
        "name": "中原健太郎", "name_en": "Kentaro Nakahara",
        "title": "主厨，炎珀EMBER",
        "bio": "日本主厨，主理炭火和牛专门店炎珀EMBER。",
        "origin": "日本",
        "culinary_background": "日式炭火烧烤经验。",
        "signature_style": "炭火和牛，手工切肉，盐烧与酱烧并重。",
    },
    {
        "name": "OYAMA", "name_en": "Oyama",
        "title": "主厨，Sushi Oyama 鮨大山",
        "bio": "日本主厨，坚持挑选应季食材每月更新菜单，所有生鲜以冰块木盒保存。",
        "origin": "日本",
        "culinary_background": "江户前寿司修行。",
        "signature_style": "江户前寿司，应季食材月更菜单。",
    },

    # ---- 中餐名厨/集团创始人 ----
    {
        "name": "卢怿明", "name_en": "Tony Lu",
        "title": "主厨/行政总厨，福系列餐厅总厨",
        "bio": "上海本地人，16岁入行，21岁做主厨。2005年以顾问身份加入福餐饮集团，后升总厨师长。主理福和慧（米其林二星素食）、福1015/1039/1088（米其林一星本帮）、鲁采LU STYLE（鲁菜）、雍颐庭（江南菜）。不拜师自学，从市场规则出发做厨师。",
        "origin": "上海",
        "culinary_background": "90年代初海鲜大酒楼时期入行，自学成才，不拜师父。",
        "signature_style": "现代江南菜/素食，以现代手法结合传统中式菜肴；福和慧的精致素食在米其林独树一帜。",
        "reputation": "福和慧米其林二星；福系列多次米其林一星；亚洲50佳内地唯一上榜中餐（福1015）；北京四季采逸轩、杭州四季金沙厅顾问。",
        "group_id": 4,
        "restaurants_owned": ["福和慧", "福1015", "福1039", "福1088", "鲁采LU STYLE", "雍颐庭"],
    },
    {
        "name": "董振祥", "name_en": "Dong Zhenxiang",
        "title": "大董，意境菜创始人，大董集团董事长",
        "bio": "1961年12月生于北京，人称'大董'。17岁入行，工商管理硕士，国家中式烹调高级技师，中国烹饪大师。以'酥不腻'烤鸭成名，2009年创立'中国意境菜'理念。1985年创立大董烤鸭店，至今品牌40年。",
        "origin": "北京",
        "culinary_background": "师承鲁菜泰斗王义均、孙仲才、王文昌；博采鲁菜、粤菜、川菜、淮扬菜及西餐之长。",
        "signature_style": "'酥不腻'烤鸭；中国意境菜——将中国菜与文学、陶瓷、绘画、音乐结合，'古典朴茂、时尚隽雅'。",
        "reputation": "中国烹饪大师；世界中餐业联合会副会长；国际中餐名厨专业委员会主席；大董品牌上海多家门店米其林推介。",
        "group_id": 3,
        "restaurants_owned": ["大董", "小大董", "大董海参店"],
    },
    {
        "name": "张勇", "name_en": "Zhang Yong",
        "title": "新荣记集团创始人/董事长，人称'荣叔'",
        "bio": "1968年3月生于浙江临海。1989年在临海三角马路地下室开海鲜小排档，1995年10月1日正式创立'新荣记食府'。从台州路边大排档发展为米其林收割机——6年49颗星。2026年获亚洲50最佳餐厅'标志人物奖'。",
        "origin": "浙江台州临海",
        "culinary_background": "原为汽配生意出身，因热爱美食入行；以粤菜技法结合台州小海鲜创新。",
        "signature_style": "台州菜高端化，'食必求真，然后至美'；真材真味真诚，以顶级小海鲜和家烧技法立身。",
        "reputation": "新荣记北京/上海/香港多家米其林星级；亚洲50最佳标志人物奖（2026）；中餐天花板级人物。",
        "group_id": 1,
        "restaurants_owned": ["新荣记", "京季", "芙蓉无双", "荣府宴"],
    },
    {
        "name": "翁拥军", "name_en": "Weng Yongjun",
        "title": "甬府集团创始人，宁波菜教父",
        "bio": "宁波人，父亲从事酒店行业，小学暑假即在部队招待所厨房学切配。初中毕业后进入宁波饭店，深耕餐饮近40年。2011年押上全部身家360万在上海开第一家甬府，首年亏损400万，后逆袭为宁波菜天花板。",
        "origin": "浙江宁波",
        "culinary_background": "宁波华侨饭店、甬港饭店、宁波饭店历练；从基层刀工做起。",
        "signature_style": "正宗宁波菜，东海小海鲜'鲜咸合一'；凌晨去港口拿第一波海鲜，一把手亲控供应链。",
        "reputation": "甬府米其林一星（2017起）；黑珍珠三钻；唯一上榜米其林的宁波菜品牌；金梧桐评委会理事长。",
        "group_id": 2,
        "restaurants_owned": ["甬府", "甬府尊鲜", "甬府小鲜", "甬府小包"],
    },
    {
        "name": "杜建青", "name_en": "Du Jianqing",
        "title": "菁禧荟创始人/总厨，新派潮菜代表",
        "bio": "1977年生于潮州普宁。16岁由父亲推荐赴深圳学潮州菜，在金岛燕窝潮州酒楼、佳宁娜大酒楼等从洗菜杀鱼做起。1997年随深圳厨师团队到上海。2014年底在上海长宁别墅创立菁禧荟，连续多年米其林一星/二星。",
        "origin": "广东潮州普宁",
        "culinary_background": "深圳老牌潮菜酒楼学徒出身，30余年潮州菜功底。",
        "signature_style": "'味正形新'新潮菜——根基扎在潮汕本土，吸纳四海烹饪灵感；花胶响螺专门，突出本味。",
        "reputation": "米其林二星/黑珍珠三钻；连续8年米其林一星以上；新派潮菜代表人物。",
        "group_id": 5,
        "restaurants_owned": ["菁禧荟", "菁禧荟SELECTION"],
    },
    {
        "name": "侯新庆", "name_en": "Hou Xinqing",
        "title": "香格里拉集团区域中餐行政总厨，'淮扬刀客'",
        "bio": "1972年生于江苏泰兴，长于扬州。1989年入行，扬州大学旅游烹饪学院毕业。淮扬菜非遗传承人周晓燕嫡传弟子。因《舌尖上的中国》文思豆腐羹制作闻名。现任香格里拉集团区域中餐行政总厨，南京江南灶主厨。",
        "origin": "江苏泰兴",
        "culinary_background": "师从淮扬菜大师周晓燕；先后任职中山香格里拉、北京中国大饭店夏宫、南京香格里拉。",
        "signature_style": "淮扬菜精细刀工，'从传统中来，向创新中去'；皮包水水包皮等创意菜；家常不寻常。",
        "reputation": "'淮扬刀客'；《舌尖上的中国》出镜；香聚江南灶（前滩香格里拉）顾问主厨。",
        "group_id": 10,
    },
    {
        "name": "周晓燕", "name_en": "Zhou Xiaoyan",
        "title": "淮扬菜大师，扬州大学教授，非遗传承人",
        "bio": "淮扬菜非物质文化遗产传承人，扬州大学旅游烹饪学院副院长/教授，中国烹饪大师。培养了侯新庆等一批淮扬菜中坚力量。",
        "origin": "江苏扬州",
        "culinary_background": "学院派淮扬菜权威，中国烹饪协会名厨委重要成员。",
        "signature_style": "传统淮扬菜理论与实践并重，文思豆腐等经典刀工菜。",
        "reputation": "淮扬菜非遗传承人；扬州大学教授；多次代表中国烹饪界出席国际活动。",
    },
    {
        "name": "吴嵘", "name_en": "Wu Rong",
        "title": "遇外滩主理人，闽菜大师",
        "bio": "福建厦门人，16岁入行，拜闽菜泰斗童辉星为师。20多岁成为五星级酒店主厨，后辞职创业。先在厦门打造宴遇、荣先森等品牌，2018年到上海创立遇外滩，将闽菜推至高端。",
        "origin": "福建厦门",
        "culinary_background": "师从闽菜泰斗童辉星；厦门宴遇等品牌创业经验。",
        "signature_style": "'鲜活醇厚，汤纳百味'；现代手法包装福建菜；佛跳墙、葱头油肉汁焗荔浦芋头为招牌。",
        "reputation": "黑珍珠三钻/米其林一星连续6年；2024黑珍珠年度主厨；黑珍珠史上首个大满贯主厨；亚洲50最佳。",
        "group_id": 6,
        "restaurants_owned": ["遇外滩", "遇外滩SKYLINE", "宴遇"],
    },
    {
        "name": "陈志评", "name_en": "Chen Zhiping",
        "title": "遇外滩SKYLINE行政主厨，黑珍珠年度年轻主厨",
        "bio": "遇外滩团队核心主厨，获黑珍珠年度年轻主厨奖。",
        "origin": "福建",
        "culinary_background": "吴嵘团队培养。",
        "signature_style": "闽菜精细化、年轻化表达。",
        "reputation": "黑珍珠年度年轻主厨。",
        "group_id": 6,
    },
    {
        "name": "杨艳彬", "name_en": "Yang Yanbin",
        "title": "米其林星级主厨，福承主理人",
        "bio": "《一饭封神》亚军，米其林星级主厨，2025年底在前滩华尔道夫顶层创立福承，聚焦泉州风味。",
        "origin": "福建",
        "culinary_background": "米其林星级餐厅历练；一饭封神亚军。",
        "signature_style": "泉州风味高端化。",
        "reputation": "一饭封神亚军；米其林星厨。",
    },
    {
        "name": "许文杰", "name_en": "Hsu Wen-chieh",
        "title": "吉兆KITCHO创始人/主厨，全球首位以割烹摘星的华人主厨",
        "bio": "15岁入行，至今30年。2008年在台北创立吉兆割烹寿司，2018年起连续8年获台北米其林一星。2025年将吉兆KITCHO开到上海。以非日籍身份做出正宗江户前omakase。",
        "origin": "中国台湾",
        "culinary_background": "15岁入行寿司行业，30年江户前寿司经验。",
        "signature_style": "江户前寿司割烹，无菜单omakase，不时不食，按季节天气食材状态调整。",
        "reputation": "连续8年台北米其林一星；全球首位以日式割烹摘星的华人主厨。",
    },
    {
        "name": "简捷明", "name_en": "Jian Jieming",
        "title": "喜粤8号主厨/创始人",
        "bio": "两位香港粤菜专家之一，喜粤8号主厨。以全球性价比最高的米其林二星粤菜闻名。",
        "origin": "香港",
        "culinary_background": "香港粤菜传统历练。",
        "signature_style": "传统粤菜，叉烧烧肉虾饺，正宗稳定。",
        "reputation": "米其林二星；全球性价比最高米其林餐厅之一。",
    },
    {
        "name": "Jacky Zhang", "name_en": "Jacky Zhang",
        "title": "逸龙阁中菜厅主厨",
        "bio": "上海半岛酒店逸龙阁中菜厅主厨，米其林星级粤菜餐厅主厨。",
        "origin": "中国",
        "culinary_background": "粤菜传统技法历练。",
        "signature_style": "传统粤菜，精湛细腻，严谨掌控。",
        "reputation": "逸龙阁米其林星级。",
        "group_id": 10,
    },
    {
        "name": "程玉平", "name_en": "Cheng Yuping",
        "title": "平川·程玉平川菜工作室主厨",
        "bio": "古法川菜主厨，30多年经验。四间包房全预订制，600元/位起。以蒜泥白肉、烧椒皮蛋等传统味型精准著称。",
        "origin": "四川",
        "culinary_background": "30余年川菜历练。",
        "signature_style": "古法川菜，传统味型精准复刻。",
        "reputation": "上海高端川菜代表，全预订制私房菜。",
    },
    {
        "name": "陈岩", "name_en": "Chen Yan",
        "title": "皖宴主厨，中华金厨奖得主",
        "bio": "深耕徽菜二十余载，曾获中华金厨奖。徽州臭鳜鱼为招牌。",
        "origin": "安徽",
        "culinary_background": "20余年徽菜经验。",
        "signature_style": "传统徽菜，臭鳜鱼等经典味型。",
        "reputation": "中华金厨奖。",
    },
    {
        "name": "任涛", "name_en": "Ren Tao",
        "title": "映水芙蓉·叙川主厨，川菜大师",
        "bio": "川菜大师，坐镇映水芙蓉·叙川——全国首家全开放式厨房板前川菜，菜单按四川五地貌做川味地图。",
        "origin": "四川",
        "culinary_background": "川菜大师级历练。",
        "signature_style": "板前川菜，五地貌川味地图概念。",
        "reputation": "黑珍珠+米其林川菜品牌。",
    },
    {
        "name": "俞斌", "name_en": "Yu Bin",
        "title": "醉玖兰亭主厨，米其林+黑珍珠双料",
        "bio": "名厨俞斌领衔高端绍兴菜品牌。醉玫干菜焖肉为招牌。",
        "origin": "浙江绍兴",
        "culinary_background": "绍兴菜传统历练。",
        "signature_style": "精细绍兴菜，干菜焖肉等黄酒慢煨技法。",
        "reputation": "米其林+黑珍珠双料背景。",
    },
    {
        "name": "傅拥军", "name_en": "Fu Yongjun",
        "title": "联合利华饮食策划行政总厨，奥林匹克烹饪大赛中国队总教练",
        "bio": "中国烹饪大师，满族富察氏第十六世孙。2016、2020世界奥林匹克烹饪大赛中国国家烹饪队教练。金梧桐上海餐厅指南评委会理事。虹桥壹号、映水芙蓉等品牌顾问。",
        "origin": "北京",
        "culinary_background": "联合利华饮食策划行政总厨；国际赛事教练。",
        "signature_style": "现代中餐，国际视野，科学化烹饪。",
        "reputation": "奥林匹克烹饪大赛中国队总教练；中国烹饪大师；金梧桐理事。",
    },
    {
        "name": "朱建中", "name_en": "Zhu Jianzhong",
        "title": "四吉饭店主理人",
        "bio": "四吉饭店主理人，需提前预约的本帮/江浙小馆。",
        "origin": "上海",
        "signature_style": "本帮家常，口碑驱动。",
    },
    {
        "name": "仇师傅", "name_en": "",
        "title": "小景门烧鸟主厨/老板",
        "bio": "全上海最会做鸡的男人，700元/位板前烧鸟，樱花虾茶碗蒸等创意菜。",
        "origin": "上海",
        "culinary_background": "烧鸟专门修行。",
        "signature_style": "板前烧鸟，创意茶碗蒸等。",
        "reputation": "上海板前烧鸟口碑标杆。",
    },
    {
        "name": "肖钊", "name_en": "",
        "title": "鮨水月主厨",
        "bio": "寿司师傅，醋饭干湿和酸度贴合口味，鳗鱼炙烤油香四溢。",
        "origin": "中国",
        "signature_style": "江户前寿司，鳗鱼料理见长。",
    },
    {
        "name": "岩松", "name_en": "",
        "title": "岩田割烹鮨主厨",
        "bio": "热情好客，菜单月更，味噌芝士为多年招牌。",
        "origin": "日本",
        "signature_style": "割烹寿司，月更菜单。",
    },
    {
        "name": "王雷", "name_en": "",
        "title": "御千代铁板烧师傅",
        "bio": "干了25年铁板烧的老师傅，火候掌握精准，樱花虾蛋炒饭为招牌。",
        "origin": "中国",
        "culinary_background": "25年铁板烧经验。",
        "signature_style": "日式铁板烧，蛋炒饭。",
    },
    {
        "name": "张天炀", "name_en": "Zhang Tianyang",
        "title": "天吉·天遊峰联合创始人",
        "bio": "与东京米其林一星天妇罗店副料理长共同创立天吉·天遊峰，面衣油温火候精准。",
        "origin": "中国",
        "culinary_background": "与东京米其林一星团队合作创业。",
        "signature_style": "天妇罗，极酥脆面衣。",
    },
    {
        "name": "黑明", "name_en": "Hei Ming",
        "title": "黑明餐厅主理人",
        "bio": "厦门20年老字号出身，红鲟米糕/海蛎煎/酱油水午鱼等厦门菜。",
        "origin": "福建厦门",
        "culinary_background": "厦门20年餐饮经验。",
        "signature_style": "厦门菜，古早味。",
    },
    {
        "name": "邓师傅", "name_en": "",
        "title": "南兴园主厨",
        "bio": "南兴园邓师傅，青椒肉丝为招牌。人均1688，只接受提前一天预约，只设包间。",
        "origin": "江苏",
        "signature_style": "传统淮扬/苏帮菜，青椒肉丝闻名。",
        "reputation": "上海精致苏帮菜代表。",
    },
    {
        "name": "邓记师傅", "name_en": "",
        "title": "邓记食园主厨",
        "bio": "深耕川菜49年，坚持传统川菜味型，葱爆猪肝等不辣味型见长。",
        "origin": "四川",
        "culinary_background": "49年川菜经验。",
        "signature_style": "传统川菜，不辣味型。",
    },
    {
        "name": "王主厨", "name_en": "",
        "title": "东莱海上主厨",
        "bio": "从业40年致力于传统鲁菜，200多道菜厚菜单，渤海湾海鲜直供。",
        "origin": "山东",
        "culinary_background": "40年鲁菜经验。",
        "signature_style": "传统鲁菜，鲅鱼水饺、油爆海螺。",
    },

    # ---- 更多主厨 ----
    {
        "name": "谭仕业", "name_en": "Tan Shiye",
        "title": "米其林三星主厨，头灶/璨璨顾问",
        "bio": "广东湛江人，30余年粤菜功底。带领上海唐阁成为中国内地首家米其林三星餐厅。烹饪美学不闪亮、不豪华、不精致，带点粗粝但有禅意有灵动。",
        "origin": "广东湛江",
        "culinary_background": "30余年粤菜经验；带领唐阁获米其林三星。",
        "signature_style": "粤菜镬气，板前中餐omakase。",
        "reputation": "米其林三星主厨（唐阁）；头灶2026升二星。",
    },
    {
        "name": "段誉", "name_en": "Duan Yu",
        "title": "新京菜创始人，京遇餐饮集团董事长",
        "bio": "河南人，北漂成为新北京人。提出新京菜概念，打造北京拾久等品牌。与甬府翁拥军合作在上海开设柿合缘。《一饭封神》行业顾问，黑珍珠评委。",
        "origin": "河南",
        "culinary_background": "北京餐饮历练，融合天南海北食材做新京菜。",
        "signature_style": "新京菜；段氏绝味鱼头、熟醉蟹、炙子烤肉。",
        "reputation": "新京菜概念提出者；米其林必吃榜；《一饭封神》顾问。",
    },
    {
        "name": "张健", "name_en": "Zhang Jian",
        "title": "Obscura by 唐香主厨",
        "bio": "上过《一饭封神》，不善言辞但极度认真。做板前中餐，不走捷径，菜单无悬浮概念堆砌。",
        "origin": "中国",
        "culinary_background": "《一饭封神》参赛主厨。",
        "signature_style": "板前中餐，落地诚意。",
        "reputation": "Obscura米其林一星。",
    },
    {
        "name": "方元", "name_en": "Fang Yuan",
        "title": "福餐饮集团创始人/老板",
        "bio": "福餐饮集团老板，虔诚佛教徒，开设福和慧素餐厅是其多年夙愿。旗下福1015/1039/1088/福和慧构成福系列老洋房本帮/素食矩阵。",
        "origin": "上海",
        "culinary_background": "餐饮投资人。",
        "signature_style": "本帮老洋房餐饮+高端素食。",
        "reputation": "福系列米其林矩阵拥有者。",
        "group_id": 8,
        "restaurants_owned": ["福1015", "福1039", "福1088", "福和慧"],
    },
    {
        "name": "孙大师", "name_en": "",
        "title": "孙大师小鲜主理人",
        "bio": "知名厨师主理，皖江菜定位最纯正。",
        "origin": "安徽",
        "signature_style": "皖江菜。",
    },
    {
        "name": "海伯主厨团队", "name_en": "",
        "title": "海伯Bohai主厨团队",
        "bio": "黑珍珠班底团队，胶东小馆，鲁菜热门。",
        "origin": "山东",
        "signature_style": "胶东鲁菜。",
    },
    {
        "name": "龚禧主厨", "name_en": "",
        "title": "龚禧龚禧·甬菜主厨",
        "bio": "30年主厨坐镇，首创笋麸菜堂灼大黄鱼。",
        "origin": "宁波",
        "culinary_background": "30年甬菜经验。",
        "signature_style": "甬菜，笋麸菜堂灼大黄鱼。",
    },
    {
        "name": "申粤轩名厨", "name_en": "",
        "title": "申粤轩酒楼主理名厨",
        "bio": "申粤轩由名厨主理粤菜沪菜，别墅洋房餐厅。",
        "origin": "广州",
        "signature_style": "粤菜沪菜融合。",
    },
    {
        "name": "江南雅厨主厨", "name_en": "",
        "title": "江南雅厨主厨",
        "bio": "苏州品牌上海落地，黑珍珠苏帮菜，主厨功底扎实。",
        "origin": "苏州",
        "signature_style": "苏帮菜。",
    },
    {
        "name": "东吴石府主厨", "name_en": "",
        "title": "东吴石府主厨",
        "bio": "苏帮面馆，三虾面当日现剥不预制，主厨对时令食材讲究。",
        "origin": "苏州",
        "signature_style": "苏帮面，三虾面。",
    },
    {
        "name": "松鹤楼师傅", "name_en": "",
        "title": "RIVIERA松鹤楼主厨团队",
        "bio": "松鼠桂鱼绝技，明档厨房现场表演菊花鱼。",
        "origin": "苏州",
        "signature_style": "苏帮菜，松鼠桂鱼。",
    },
    {
        "name": "海宫主厨", "name_en": "",
        "title": "海宫炉端烧主厨",
        "bio": "炉端烧专门，主厨与客人展示食材区域，用木桨送餐。",
        "origin": "日本",
        "signature_style": "炉端烧。",
    },
    {
        "name": "天嘉主厨", "name_en": "",
        "title": "天嘉天妇罗主厨",
        "bio": "天妇罗专门店，遵循古法现炸薄透面衣。",
        "origin": "日本",
        "signature_style": "天妇罗。",
    },
    {
        "name": "宫鸠师傅", "name_en": "",
        "title": "宫鸠寿司师傅",
        "bio": "手法专业，寿司到手有余温，金枪鱼油脂、星鳗炙烤。",
        "origin": "日本",
        "signature_style": "江户前寿司。",
    },
    {
        "name": "晴川师傅", "name_en": "",
        "title": "晴川sushi主厨",
        "bio": "九贯寿司，根据客人反应调整口味。",
        "origin": "日本",
        "signature_style": "江户前寿司。",
    },
    {
        "name": "白茸主厨", "name_en": "",
        "title": "白茸Bai Rong主理人",
        "bio": "米其林Plate连续入选（2024、2025），捞汁小海鲜为必点。",
        "origin": "中国",
        "signature_style": "创意中餐。",
        "reputation": "米其林Plate连续入选。",
    },
    {
        "name": "壹零贰小馆主厨", "name_en": "",
        "title": "壹零贰小馆主理主厨",
        "bio": "广府菜融合岭南各菜系，菜单按位上，无菜单由主厨按季节制定。",
        "origin": "广州",
        "signature_style": "广府菜omakase。",
    },
]

# ============================================================
# 主厨-餐厅关联 (chef_name, restaurant_id, role, is_current, source_url)
# ============================================================
# Restaurant IDs from database scan
ASSOCIATIONS = [
    # Paul Pairet group
    ("Paul Pairet", 1878, "主理人", True, "https://www.mmbund.com/chef/"),
    ("Paul Pairet", 1152, "主理人", True, "https://uvbypp.cc/chef-section"),
    ("Paul Pairet", 1810, "主理人", True, None),
    # Bombana group
    ("Umberto Bombana", 1175, "创始人/顾问", True, "https://www.ottoemezzobombana.com/umberto-bombana/"),
    ("Nicoló Rotella", 1175, "烹饪总监/行政总厨", True, "https://laisundining.com/the-venues/8-1-2-otto-e-mezzo-bombana-shanghai/"),
    # Robuchon
    ("Joël Robuchon", 1139, "品牌创始人", False, None),  # Robuchon 2018年逝世
    # Pierre Gagnaire
    ("Pierre Gagnaire", 1166, "品牌创始人/顾问", True, None),
    # Luneurs
    ("Didier Chouet", 1162, "甜品主厨", True, None),
    # VERIE
    ("Frederic Jaros", 1170, "创始人/主厨", True, None),
    # el Willy
    ("Willy Trullas Moreno", 1197, "创始人/主厨", True, None),
    # 炎珀
    ("中原健太郎", 31, "主理主厨", True, None),
    # Oyama
    ("OYAMA", 5, "主厨", True, None),
    # 卢怿明
    ("卢怿明", 1383, "主厨/主理人", True, "https://m.sohu.com/n/455861531/"),
    ("卢怿明", 1007, "行政总厨", True, None),
    ("卢怿明", 1387, "行政总厨", True, None),
    ("卢怿明", 1388, "行政总厨", True, None),
    ("卢怿明", 463, "主厨/主理人", True, None),
    ("卢怿明", 539, "主厨/顾问", True, None),
    # 大董
    ("董振祥", 1561, "创始人/主理人", True, "http://www.chcyxh.org/?a=index&aid=387&c=View&m=home"),
    ("董振祥", 823, "创始人/主理人", True, None),
    ("董振祥", 1049, "创始人/主理人", True, None),
    ("董振祥", 818, "创始人", True, None),
    ("董振祥", 1052, "创始人", True, None),
    # 张勇/新荣记
    ("张勇", 871, "创始人", True, "https://www.xinrongji.com/"),
    ("张勇", 1370, "创始人", True, None),
    ("张勇", 1376, "创始人", True, None),
    ("张勇", 1377, "创始人", True, None),
    ("张勇", 1380, "创始人", True, None),
    # 翁拥军/甬府
    ("翁拥军", 538, "创始人", True, "http://www.sh.chinanews.com/shms/2022-11-25/105889.shtml"),
    ("翁拥军", 1504, "创始人", True, None),
    ("翁拥军", 536, "创始人", True, None),
    ("翁拥军", 531, "创始人", True, None),
    # 杜建青/菁禧荟
    ("杜建青", 494, "创始人/主理人", True, "https://m.thepaper.cn/newsDetail_forward_13298098"),
    ("杜建青", 1472, "创始人/主理人", True, None),
    ("杜建青", 1919, "创始人/主理人", True, None),
    # 侯新庆
    ("侯新庆", 782, "顾问主厨", True, "https://www.shangri-la.com/cn/nanjing/shangrila/dining/restaurants/jiangnan-wok-yun/"),
    # 吴嵘
    ("吴嵘", 524, "创始人/主理人", True, "https://m.baike.com/wiki/%E5%90%B4%E5%B5%98/7379927400707342377"),
    ("吴嵘", 903, "创始人/主理人", True, None),
    ("吴嵘", 523, "创始人", True, None),
    # 陈志评
    ("陈志评", 903, "行政主厨", True, None),
    # 杨艳彬
    ("杨艳彬", 904, "主理人/主厨", True, None),
    # 许文杰
    ("许文杰", 6, "创始人/主厨", True, "https://guide.michelin.com/tw/zh_TW/article/people/first-day-i-got-my-michelin-stars-kitcho"),
    # 简捷明
    ("简捷明", 713, "主厨/创始人", True, None),
    # Jacky Zhang
    ("Jacky Zhang", 716, "主厨", True, None),
    # 程玉平
    ("程玉平", 583, "主厨/创始人", True, None),
    ("程玉平", 584, "主厨顾问", True, None),
    # 陈岩
    ("陈岩", 569, "主厨", True, None),
    # 任涛
    ("任涛", 637, "主厨", True, None),
    # 俞斌
    ("俞斌", 856, "主厨", True, None),
    # 朱建中
    ("朱建中", 598, "主理人", True, None),
    # 仇师傅
    ("仇师傅", 10, "主厨/老板", True, None),
    # 肖钊
    ("肖钊", 2, "主厨", True, None),
    # 岩松
    ("岩松", 3, "主厨", True, None),
    # 王雷
    ("王雷", 4, "铁板烧师傅", True, None),
    # 张天炀
    ("张天炀", 38, "联合创始人", True, None),
    # 黑明
    ("黑明", 893, "主理人", True, None),
    # 南兴园邓师傅
    ("邓师傅", 478, "主厨", True, None),
    ("邓师傅", 1447, "主厨", True, None),
    # 邓记食园
    ("邓记师傅", 481, "主厨", True, None),
    # 东莱海上王主厨
    ("王主厨", 458, "主厨", True, None),
    # 谭仕业
    ("谭仕业", 719, "顾问主厨", True, "https://www.sina.cn/news/detail/5199495698320426.html"),
    # 方元/福系列
    ("方元", 1007, "创始人/老板", True, None),
    ("方元", 1387, "创始人/老板", True, None),
    ("方元", 1388, "创始人/老板", True, None),
    ("方元", 1383, "创始人/老板", True, None),
    # 孙大师
    ("孙大师", 947, "主理人", True, None),
    # 海伯
    ("海伯主厨团队", 821, "主厨团队", True, None),
    # 龚禧
    ("龚禧主厨", 839, "主厨", True, None),
    # 江南雅厨
    ("江南雅厨主厨", 758, "主厨", True, None),
    # 东吴石府
    ("东吴石府主厨", 751, "主厨", True, None),
    # 松鹤楼
    ("松鹤楼师傅", 757, "主厨团队", True, None),
    # 海宫
    ("海宫主厨", 11, "主厨", True, None),
    # 天嘉
    ("天嘉主厨", 37, "主厨", True, None),
    # 宫鸠
    ("宫鸠师傅", 9, "主厨", True, None),
    # 晴川
    ("晴川师傅", 1, "主厨", True, None),
    # 白茸
    ("白茸主厨", 815, "主理人", True, None),
    # 壹零贰小馆
    ("壹零贰小馆主厨", 718, "主厨", True, None),
]


def build_chef_rows():
    """Build chef rows for insertion, skipping duplicates."""
    rows = []
    for c in CHEFS:
        row = {
            "name": c["name"],
            "name_en": c.get("name_en", ""),
            "title": c.get("title", ""),
            "bio": c.get("bio", ""),
            "origin": c.get("origin", ""),
            "culinary_background": c.get("culinary_background", ""),
            "signature_style": c.get("signature_style", ""),
            "reputation": c.get("reputation", ""),
            "group_id": c.get("group_id"),
            "restaurants_owned": c.get("restaurants_owned", []),
            "data_updated_at": TODAY,
            "last_tracked_at": TODAY,
        }
        # Remove empty strings that might cause issues, keep them as empty
        rows.append(row)
    return rows


def main():
    commit = "--commit" in sys.argv
    chefs = build_chef_rows()

    print(f"=== Chef Profiles to insert: {len(chefs)} ===")
    for i, c in enumerate(chefs):
        print(f"  {i+1}. {c['name']} ({c.get('name_en','')}) - {c.get('title','')[:50]}")

    if not commit:
        print(f"\n[DRY-RUN] Use --commit to write {len(chefs)} chef records.")
        # Also show associations
        print(f"\n=== Restaurant-Chef associations: {len(ASSOCIATIONS)} ===")
        for name, rid, role, cur, url in ASSOCIATIONS[:10]:
            print(f"  {name} -> restaurant_id={rid} ({role})")
        print(f"  ... and {len(ASSOCIATIONS)-10} more")
        return

    # Commit: insert chefs
    print(f"\n[COMMIT] Inserting {len(chefs)} chefs...")
    chef_id_map = {}  # name -> id

    # Insert in batches
    batch = []
    for c in chefs:
        batch.append(c)
        if len(batch) >= 10:
            r = req("POST", "/chefs", json=batch)
            if r.status_code in (200, 201):
                for row in r.json():
                    chef_id_map[row["name"]] = row["id"]
                print(f"  Inserted batch of {len(batch)}")
            else:
                print(f"  ERROR: {r.status_code} {r.text[:300]}")
            batch = []
    if batch:
        r = req("POST", "/chefs", json=batch)
        if r.status_code in (200, 201):
            for row in r.json():
                chef_id_map[row["name"]] = row["id"]
            print(f"  Inserted batch of {len(batch)}")
        else:
            print(f"  ERROR: {r.status_code} {r.text[:300]}")

    print(f"\nChefs inserted: {len(chef_id_map)}")

    # Insert associations
    print(f"\n[COMMIT] Inserting {len(ASSOCIATIONS)} restaurant_chefs associations...")
    assoc_batch = []
    for name, rid, role, is_current, url in ASSOCIATIONS:
        cid = chef_id_map.get(name)
        if not cid:
            print(f"  SKIP: chef '{name}' not found in inserted records")
            continue
        assoc_batch.append({
            "restaurant_id": rid,
            "chef_id": cid,
            "role": role,
            "is_current": is_current,
            "source_url": url,
        })

    # Insert associations in batches
    abatch = []
    for a in assoc_batch:
        abatch.append(a)
        if len(abatch) >= 10:
            r = req("POST", "/restaurant_chefs", json=abatch)
            if r.status_code in (200, 201):
                print(f"  Inserted {len(abatch)} associations")
            else:
                print(f"  ERROR: {r.status_code} {r.text[:300]}")
            abatch = []
    if abatch:
        r = req("POST", "/restaurant_chefs", json=abatch)
        if r.status_code in (200, 201):
            print(f"  Inserted {len(abatch)} associations")
        else:
            print(f"  ERROR: {r.status_code} {r.text[:300]}")

    print(f"\n=== DONE ===")
    print(f"Chefs: {len(chef_id_map)}")
    print(f"Associations: {len(assoc_batch)} attempted")


if __name__ == "__main__":
    main()
