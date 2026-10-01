#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Source Coverage Registry · authority 批次行生成器
严格按 coverage_framework.md §2 冻结的 15 字段 schema 输出 JSONL。
本批次只调研，不接入/不购买/不写库；dine_in_evidence 一律 false（权威/互证类，非堂食口味证据）。
"""
import json, sys, pathlib

ALLOWED_CATEGORY = {"UGC","MAP","SHORTVIDEO","LONGFORM","GUIDE","OFFICIAL","REGISTRY",
                    "MEDIA","MEDIA_TV","OVERSEAS","DATA_MARKET","OPEN_API"}
ALLOWED_CHANNEL  = {"official_api","apify_actor","authorized_dataset","rss","public_html",
                    "search_snapshot","manual"}
ALLOWED_TOS      = {"low","medium","high"}
ALLOWED_RISK     = {"low","medium","high"}
REQUIRED = ["source_id","platform","category","url","fields_available","channel","tos_pipl",
            "risk_level","rate_limit","cost","dine_in_evidence","strong_cuisines",
            "active","covered_grid","notes"]

ROWS = [
# ============================ GUIDE 榜单/指南 ============================
{
 "source_id":"guide_michelin_main",
 "platform":"米其林指南 MICHELIN Guide",
 "category":"GUIDE",
 "url":"https://guide.michelin.com/cn/zh_CN/restaurants",
 "fields_available":["restaurant_name","star_level(0/1/2/3)","cuisine","city","price_band","address","booking_url","green_star","inspector_note"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min 手动节奏","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["法餐","意餐","中餐高端","日料","fine-dining全菜系"],
 "active":True,
 "covered_grid":["全菜系×正餐fine-dining","全菜系×会所"],
 "notes":"匿名评审榜单，2026沪苏浙版409家(上海156家)、2027成都版刚发布；仅作漏店锚定/事实互证，非堂食口味证据。"
},
{
 "source_id":"guide_bib_gourmand",
 "platform":"米其林必比登推介 Bib Gourmand",
 "category":"GUIDE",
 "url":"https://guide.michelin.com/cn/zh_CN/restaurants/bib-gourmand",
 "fields_available":["restaurant_name","city","price_band","cuisine","signature_dish_hint"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["面食","小吃","家常小炒","点心","快餐"],
 "active":True,
 "covered_grid":["全菜系×快餐小吃","全菜系×早餐","全菜系×夜宵"],
 "notes":"米其林旗下平价子榜，专补星级榜覆盖不到的市井小馆/面店；沪苏浙2026含164家；互证非堂食证据。"
},
{
 "source_id":"guide_blackpearl",
 "platform":"黑珍珠餐厅指南",
 "category":"GUIDE",
 "url":"https://blackpearl.meituan.com",
 "fields_available":["restaurant_name","diamond(1/2/3)","cuisine","city","district","address","edition_year","annual_award(主厨/菜品)"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=5/min 美团反爬","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["本帮江浙","粤菜","川菜","闽菜","潮州菜","中餐精致正餐"],
 "active":True,
 "covered_grid":["全菜系×正餐fine-dining","全菜系×私房"],
 "notes":"美团/大众点评出品，2026版32城263家/45菜系；与米其林互证；非堂食口味证据。"
},
{
 "source_id":"guide_ctrip_gourmet",
 "platform":"携程美食林 Trip.Gourmet",
 "category":"GUIDE",
 "url":"https://m.ctrip.com/html5/you/foods/",
 "fields_available":["restaurant_name","tier(黑钻/钻石/铂金)","theme(高端/当地风味/美景体验)","city","price_band","review_count"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["旅行目的地餐厅","全菜系","当地风味"],
 "active":True,
 "covered_grid":["全菜系×正餐","全菜系×休闲bistro"],
 "notes":"专家评审+旅行者验榜，2027高端榜744家/40国105城；旅行场景补点；互证非堂食证据。"
},
{
 "source_id":"guide_asia_50best",
 "platform":"Asia's 50 Best Restaurants",
 "category":"GUIDE",
 "url":"https://www.theworlds50best.com/asia/en/list/1-50",
 "fields_available":["rank","restaurant_name","city","country","special_award","chef_name"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["亚洲fine-dining","融合菜","日料","东南亚菜","当代中餐"],
 "active":True,
 "covered_grid":["全菜系×正餐fine-dining"],
 "notes":"2026榜2026-03香港颁，大班楼第一、上海Meet the Bund在榜；主厨/餐厅知名度互证，非堂食证据。"
},
{
 "source_id":"guide_gault_millau",
 "platform":"Gault&Millau 高勒米罗美食指南",
 "category":"GUIDE",
 "url":"https://www.gaultmillau.com",
 "fields_available":["restaurant_name","toque(1-3)","city","country","cuisine"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["法餐","欧洲菜系"],
 "active":False,
 "covered_grid":[],
 "notes":"用户清单中'G&G'按Gault&Millau核实；全球法语区指南，截至2026-10无中国大陆/港澳独立版，仅海外格参考；active=false待提审是否启用。"
},

# ============================ OFFICIAL 官方/品牌 ============================
{
 "source_id":"off_wechat_oa",
 "platform":"微信公众号(品牌官方)",
 "category":"OFFICIAL",
 "url":"https://mp.weixin.qq.com",
 "fields_available":["article_title","publish_time","account_name(品牌)","content","cover_image","like_count"],
 "channel":"public_html","tos_pipl":"high","risk_level":"high","rate_limit":"极慢/人工，反爬严","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["全菜系品牌官方动态","新店","菜单","活动"],
 "active":True,
 "covered_grid":["全菜系×全场景"],
 "notes":"品牌第一方口径：菜单/新店/停业/主厨更迭事实存证；文章链接可归档；绝不作品味证据。"
},
{
 "source_id":"off_weibo",
 "platform":"新浪微博(品牌官方蓝V)",
 "category":"OFFICIAL",
 "url":"https://weibo.com",
 "fields_available":["post_text","images","publish_time","repost_count","comment_count","like_count"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["全菜系品牌官宣","活动","快闪"],
 "active":True,
 "covered_grid":["全菜系×全场景"],
 "notes":"新店/联名/快闪第一方官宣；与公众号互证；营销口径，非口味证据。"
},
{
 "source_id":"off_douyin_brand",
 "platform":"抖音/视频号(品牌官方号)",
 "category":"OFFICIAL",
 "url":"https://www.douyin.com",
 "fields_available":["video_title","desc","publish_time","like_count","chef_on_camera","signature_dish_shot"],
 "channel":"public_html","tos_pipl":"high","risk_level":"high","rate_limit":"极慢/需登录","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["全菜系招牌菜制作","主厨出镜"],
 "active":True,
 "covered_grid":["全菜系×全场景"],
 "notes":"主厨出镜/招牌菜制作过程可作'存在性+招牌菜'互证；出品方自制内容，非独立堂食口味证据。"
},
{
 "source_id":"off_instagram",
 "platform":"Instagram(在华海外品牌官方)",
 "category":"OFFICIAL",
 "url":"https://www.instagram.com",
 "fields_available":["post_caption","images","publish_time","like_count"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min(需境外网络)","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["法餐","意餐","日料","fine-dining"],
 "active":True,
 "covered_grid":["法餐×正餐","意餐×正餐","日料×正餐"],
 "notes":"海外餐饮集团在华分店官方口径；与官网互证；需境外网络环境。"
},
{
 "source_id":"off_wechat_mini",
 "platform":"微信小程序(订座/点单/菜单)",
 "category":"OFFICIAL",
 "url":"https://mp.weixin.qq.com",
 "fields_available":["menu_items","price","booking_slots","branch_list"],
 "channel":"manual","tos_pipl":"high","risk_level":"high","rate_limit":"仅人工录屏/截图","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["连锁品牌","全菜系"],
 "active":True,
 "covered_grid":["全菜系×全场景"],
 "notes":"无公开web入口/无开放API；仅人工截图存证菜单与分店事实；非口味证据。"
},

# ============================ REGISTRY 企业与监管注册 ============================
{
 "source_id":"reg_qcc",
 "platform":"企查查",
 "category":"REGISTRY",
 "url":"https://www.qcc.com",
 "fields_available":["entity_name","unified_credit_code","legal_rep","registered_capital","status","shareholders","branches","investment","risk_tags"],
 "channel":"public_html","tos_pipl":"high","risk_level":"high","rate_limit":"登录后限速/批量需付费API","cost":"免费基础查询，深度付费",
 "dine_in_evidence":False,
 "strong_cuisines":["连锁主体","餐饮集团","融资事实"],
 "active":True,
 "covered_grid":[],
 "notes":"主体/连锁/融资/司法风险互证；反爬且用户协议禁止批量抓；绝不作品味证据。"
},
{
 "source_id":"reg_tianyancha",
 "platform":"天眼查",
 "category":"REGISTRY",
 "url":"https://www.tianyancha.com",
 "fields_available":["entity_name","unified_credit_code","legal_rep","status","shareholders","branches","lawsuit_count","abnormal_operation"],
 "channel":"public_html","tos_pipl":"high","risk_level":"high","rate_limit":"登录后限速","cost":"免费基础查询，深度付费",
 "dine_in_evidence":False,
 "strong_cuisines":["连锁主体","工商司法互证"],
 "active":True,
 "covered_grid":[],
 "notes":"与企查查/启信宝三源互证工商登记；非口味证据。"
},
{
 "source_id":"reg_qixin",
 "platform":"启信宝",
 "category":"REGISTRY",
 "url":"https://www.qixin.com",
 "fields_available":["entity_name","unified_credit_code","legal_rep","branches","shareholders","risk_info"],
 "channel":"public_html","tos_pipl":"high","risk_level":"high","rate_limit":"登录后限速","cost":"免费基础查询，深度付费",
 "dine_in_evidence":False,
 "strong_cuisines":["连锁主体","合合信息系数据"],
 "active":True,
 "covered_grid":[],
 "notes":"上海本地合合信息旗下，覆盖1.8亿社会实体；与另两查互证；非口味证据。"
},
{
 "source_id":"reg_gsxt",
 "platform":"国家企业信用信息公示系统",
 "category":"REGISTRY",
 "url":"https://www.gsxt.gov.cn",
 "fields_available":["entity_name","unified_credit_code","registration","annual_report","administrative_penalty","abnormal_dir","serious_violation"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"人机验证约<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["官方法定登记","行政处罚"],
 "active":True,
 "covered_grid":[],
 "notes":"官方法定权威登记源；事实层以它为准；有验证码需人工节奏。"
},
{
 "source_id":"reg_sc_prod_license",
 "platform":"食品生产许可获证企业信息查询",
 "category":"REGISTRY",
 "url":"https://spaqjg.e-cqs.cn/spscxk/",
 "fields_available":["sc_license_no","enterprise_name","food_category","valid_until","issuing_authority"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"人工节奏","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["预包装食品","预制菜","品牌工厂","烘焙/饮品供应链"],
 "active":True,
 "covered_grid":[],
 "notes":"市监总局平台收录15万+食品生产企业；用于品牌工厂/预制菜互证；非堂食。"
},
{
 "source_id":"reg_food_sampling",
 "platform":"食品安全抽检公布结果查询",
 "category":"REGISTRY",
 "url":"https://spcjsac.gsxt.gov.cn/",
 "fields_available":["nominal_producer","product_name","unqualified_item","notice_no","publish_date"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"人工节奏","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["预包装食品安全负面事实"],
 "active":True,
 "covered_grid":[],
 "notes":"市监总局抽检通报；用于风险标注/负面事实；对象多为预包装食品，少涉堂食。"
},
{
 "source_id":"reg_court_wenshu",
 "platform":"中国裁判文书网",
 "category":"REGISTRY",
 "url":"https://wenshu.court.gov.cn",
 "fields_available":["case_no","parties","cause_of_action","judgment_date","full_text"],
 "channel":"public_html","tos_pipl":"high","risk_level":"high","rate_limit":"登录+验证码，极慢","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["食安纠纷","加盟纠纷","商标侵权"],
 "active":True,
 "covered_grid":[],
 "notes":"2021后公开量骤降且需登录；仅作法律事实互证；非口味证据。"
},
{
 "source_id":"reg_shixin",
 "platform":"中国执行信息公开网(失信/被执行)",
 "category":"REGISTRY",
 "url":"http://zxgk.court.gov.cn",
 "fields_available":["被执行人","dishonest_list","consumption_restriction","execution_court","amount"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"人工节奏","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["连锁爆雷","闭店/跑路风险预警"],
 "active":True,
 "covered_grid":[],
 "notes":"用于连锁品牌闭店/债务风险预警；事实层，非口味证据。"
},
{
 "source_id":"reg_trademark",
 "platform":"中国商标网(国家知识产权局)",
 "category":"REGISTRY",
 "url":"https://sbj.cnipa.gov.cn/trademark-query",
 "fields_available":["trademark_name","reg_no","class(43类餐饮)","applicant","status"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"人工节奏","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["品牌归属","假店识别"],
 "active":True,
 "covered_grid":[],
 "notes":"43类餐饮商标归属查询；用于正名/识别傍名牌假店；非口味证据。"
},

# ============================ MEDIA 行业媒体 ============================
{
 "source_id":"media_hongcan_hongchu",
 "platform":"红餐网/红厨网",
 "category":"MEDIA",
 "url":"https://www.canyin88.com",
 "fields_available":["article_title","chef_name","restaurant_name","dish","industry_trend","event"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["全菜系后厨","主厨","连锁业态"],
 "active":True,
 "covered_grid":["全菜系×全场景(行业视角)"],
 "notes":"2007年创立，红厨网100万+厨师粉丝；主厨访谈/菜品做法；行业视角非堂食口味证据。"
},
{
 "source_id":"media_mingchu",
 "platform":"名厨 MINGCHU",
 "category":"MEDIA",
 "url":"https://www.mingchu.co",
 "fields_available":["chef_profile","signature_dish","live_event","ingredient","work_post"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min","cost":"free(社区)/活动付费",
 "dine_in_evidence":False,
 "strong_cuisines":["fine-dining","甜品","西餐","中餐主厨"],
 "active":True,
 "covered_grid":["全菜系×正餐","甜品×甜品"],
 "notes":"72万专业厨师社区；主厨背书/作品互证；非独立堂食证据。"
},
{
 "source_id":"media_canyinneican",
 "platform":"餐饮老板内参",
 "category":"MEDIA",
 "url":"https://weixin.sogou.com/weixin?type=1&query=%E9%A4%90%E9%A5%AE%E8%80%81%E6%9D%BF%E5%86%85%E5%8F%82",
 "fields_available":["article_title","publish_time","industry_data","chain_financing","closure_news"],
 "channel":"search_snapshot","tos_pipl":"high","risk_level":"medium","rate_limit":"搜狗微信检索限速","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["连锁业态","融资","闭店","加盟"],
 "active":True,
 "covered_grid":[],
 "notes":"微信原生垂媒，无独立官网；仅公众号文章快照；业态/资本事实，非口味证据。"
},
{
 "source_id":"media_foodaily",
 "platform":"Foodaily每日食品",
 "category":"MEDIA",
 "url":"https://www.foodaily.com",
 "fields_available":["new_product","brand","ingredient","exhibition(FBIC)","report"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["烘焙","咖啡","甜品","新茶饮","预包装"],
 "active":True,
 "covered_grid":["咖啡×咖啡","面包×面包","甜品×甜品"],
 "notes":"2009年创立，FBIC创博会常年在沪国家会展中心；产品创新视角；非堂食。"
},

# ============================ MEDIA_TV 影视综/纪录片/书籍 ============================
{
 "source_id":"tv_fengwei",
 "platform":"风味人间(陈晓卿团队/腾讯视频)",
 "category":"MEDIA_TV",
 "url":"https://v.qq.com",
 "fields_available":["episode","ingredient","origin","person","featured_shop_or_vendor"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min","cost":"free(会员)",
 "dine_in_evidence":False,
 "strong_cuisines":["全球食材","地域菜系","全菜系人文"],
 "active":True,
 "covered_grid":["全菜系×全场景(人文视角)"],
 "notes":"第5季2025上半年播出；拍产地与制作过程，漏店反推线索；出品方制作非独立堂食证据。"
},
{
 "source_id":"tv_shejian",
 "platform":"舌尖上的中国(CCTV)",
 "category":"MEDIA_TV",
 "url":"https://tv.cctv.com",
 "fields_available":["episode","ingredient","origin","featured_shop_or_vendor"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["全菜系人文","产地食材"],
 "active":True,
 "covered_grid":["全菜系×全场景(人文视角)"],
 "notes":"第4季2025新春播出；与风味人间同系；文化/产地事实，非堂食证据。"
},
{
 "source_id":"tv_yifan",
 "platform":"一饭封神(腾讯视频)",
 "category":"MEDIA_TV",
 "url":"https://v.qq.com",
 "fields_available":["episode","contestant_chef","dish","judge(谢霆锋/张勇/郑永麒)","season"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"medium","rate_limit":"<=10/min","cost":"会员",
 "dine_in_evidence":False,
 "strong_cuisines":["全菜系竞技","创意菜"],
 "active":True,
 "covered_grid":["全菜系×正餐"],
 "notes":"S2 2026-07-29开播共10集；主厨知名度/菜品互证；竞技内容非堂食证据。"
},
{
 "source_id":"tv_heibai",
 "platform":"黑白大厨：料理阶级大战(Netflix)",
 "category":"MEDIA_TV",
 "url":"https://www.netflix.com",
 "fields_available":["episode","contestant_chef","dish","featured_restaurant(韩国为主)"],
 "channel":"manual","tos_pipl":"high","risk_level":"medium","rate_limit":"仅人工观看/字幕整理","cost":"会员",
 "dine_in_evidence":False,
 "strong_cuisines":["韩餐","韩国fine-dining"],
 "active":True,
 "covered_grid":["韩餐×正餐(海外)"],
 "notes":"用户称'黑白厨房'实为2024 Netflix Culinary Class Wars；无开放分集API需人工；主厨背书，韩国餐厅为主。"
},
{
 "source_id":"tv_rensheng",
 "platform":"人生一串(B站)",
 "category":"MEDIA_TV",
 "url":"https://www.bilibili.com",
 "fields_available":["episode","bbq_shop","city","vendor"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["烧烤","夜宵","全国街头"],
 "active":True,
 "covered_grid":["全菜系×夜宵","全菜系×烧烤"],
 "notes":"S3 2021收官，拍具体烤串店；漏店反推线索；出品方制作非独立堂食证据。"
},
{
 "source_id":"tv_zaoguo",
 "platform":"早餐中国(腾讯/东南/海峡卫视)",
 "category":"MEDIA_TV",
 "url":"https://v.qq.com",
 "fields_available":["episode","breakfast_shop","city","signature_dish"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["早餐","全国小食"],
 "active":True,
 "covered_grid":["全菜系×早餐"],
 "notes":"S4 2024-11播出；拍具体早餐店，漏店反推；非独立堂食证据。"
},
{
 "source_id":"tv_streetfighter",
 "platform":"街头美食斗士(tvN/白钟元)",
 "category":"MEDIA_TV",
 "url":"https://www.tvnasia.net",
 "fields_available":["episode","city(成都/香港/哈尔滨/西安)","vendor","dish"],
 "channel":"public_html","tos_pipl":"medium","risk_level":"low","rate_limit":"<=10/min","cost":"部分Netflix",
 "dine_in_evidence":False,
 "strong_cuisines":["街头小吃","夜宵","川菜","东北菜","西北菜"],
 "active":True,
 "covered_grid":["全菜系×夜宵","全菜系×快餐小吃"],
 "notes":"2018-2019两季，含中国大陆城市；街头摊档漏店反推；非独立堂食证据。"
},
{
 "source_id":"tv_foodbooks",
 "platform":"美食作家/美食家著作(豆瓣读书)",
 "category":"MEDIA_TV",
 "url":"https://book.douban.com",
 "fields_available":["book_title","author","isbn","publish_year","mentioned_restaurant_or_dish"],
 "channel":"search_snapshot","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["全菜系人文","饮食历史"],
 "active":True,
 "covered_grid":["全菜系×全场景(文化层)"],
 "notes":"陈晓卿《至味在人间》/扶霞《鱼翅与花椒》/蔡澜/沈宏非等；文化与历史互证，非当下堂食证据。"
},

# ============================ 线下名录 ============================
{
 "source_id":"offline_mall_directory",
 "platform":"购物中心官网租户名录",
 "category":"OFFICIAL",
 "url":"https://www.plaza66.com",
 "fields_available":["mall_name","tenant_name","floor","category(餐饮标记)","opening_date"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["商场内正餐/餐饮层","首店"],
 "active":True,
 "covered_grid":["全菜系×正餐","全菜系×休闲bistro"],
 "notes":"渠道模式行：以上海恒隆广场Plaza66官网商户名录为代表，JAKC/兴业太古汇/IFC/环贸iapm等逐mall官网directory实例化；用于商场餐饮层/首店补点；官方口径非口味证据。"
},
{
 "source_id":"offline_night_block",
 "platform":"夜市/美食街区官方名录",
 "category":"OFFICIAL",
 "url":"https://www.shanghai.gov.cn",
 "fields_available":["block_name","district","business_hours","host_organizer","vendor_list"],
 "channel":"public_html","tos_pipl":"low","risk_level":"low","rate_limit":"<=10/min","cost":"free",
 "dine_in_evidence":False,
 "strong_cuisines":["夜宵","小吃","夜市"],
 "active":True,
 "covered_grid":["全菜系×夜宵","全菜系×快餐小吃"],
 "notes":"安义夜巷/大学路/寿宁路等由区商委/管委会发布；线下格补点；官方名录非口味证据。"
},
]

def main():
    out = pathlib.Path("/Users/deuce/Doubao/chats/2026-09-28/new-chat/china-travel-food/research/coverage/registry_rows_authority.jsonl")
    n = 0
    errs = []
    with out.open("w", encoding="utf-8") as f:
        for r in ROWS:
            # schema 校验
            missing = [k for k in REQUIRED if k not in r]
            extra   = [k for k in r if k not in REQUIRED]
            if missing: errs.append(f"{r.get('source_id','?')}: missing {missing}")
            if extra:   errs.append(f"{r.get('source_id','?')}: extra {extra}")
            if r["category"] not in ALLOWED_CATEGORY: errs.append(f"{r['source_id']}: bad category {r['category']}")
            if r["channel"]  not in ALLOWED_CHANNEL:  errs.append(f"{r['source_id']}: bad channel {r['channel']}")
            if r["tos_pipl"] not in ALLOWED_TOS:      errs.append(f"{r['source_id']}: bad tos {r['tos_pipl']}")
            if r["risk_level"] not in ALLOWED_RISK:    errs.append(f"{r['source_id']}: bad risk {r['risk_level']}")
            if not isinstance(r["dine_in_evidence"], bool): errs.append(f"{r['source_id']}: dine not bool")
            if not isinstance(r["active"], bool): errs.append(f"{r['source_id']}: active not bool")
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} rows -> {out}")
    if errs:
        print("SCHEMA ERRORS:"); [print(" -", e) for e in errs]; sys.exit(1)
    print("schema OK: 15 fields, enums valid, no errors")

if __name__ == "__main__":
    main()
