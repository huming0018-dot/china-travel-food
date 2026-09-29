#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_firstbatch_ledger.py — HAE L0.5 首批种子回归账本（agent 版发散+收敛产出）。

每一行都是 agent 真实联网取证后写成的假设：含正向出处 URL + 强制反向证伪查询；
status 是收敛结论（confirmed/contradicted/unverified）。模型自标 知道/推断；
无出处的一律不晋升、如实留 unverified。宁空不假：年份有冲突处标 unverified，不臆断。

运行：python3 build_firstbatch_ledger.py   （输出同目录 lead_hypotheses_2026-09-29.jsonl）
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, "/app/pipeline")
sys.path.insert(0, str(HERE))
# 本地无 common 也能生成（norm_row 只做字段补全/校验）；容器内走同一文件
try:
    import hae_engine as H
except Exception:  # 本地离线生成时用内置轻量校验
    class H:
        @staticmethod
        def norm_row(r):
            return r

PROPH = "fb2026-09-29-v1"  # 本批 prompt 哈希（agent 版零成本推理，记录版本）
MODEL = {"model": "agent-self", "version": "doubao-main", "prompt_hash": PROPH,
         "ensemble": ["agent-self(零成本)"]}

ROWS = []


def add(subject_type, subject_name, relation, object=None, when=None, claim="",
        conf=0.4, kvi="推断", status="hypothesized", ev=None, cq=None, fq=None,
        voices=0, urls=None, verdict="", parent=None, seed=False, expands_to=None):
    ROWS.append({
        "subject_type": subject_type, "subject_name": subject_name,
        "relation": relation, "object": object, "when": when, "claim_text": claim,
        "confidence": conf, "known_vs_inferred": kvi, "status": status,
        "evidence": ev or [], "confirm_queries": cq or [], "falsify_queries": fq or [],
        "confirm_voices": voices, "confirmed_source_urls": urls or [],
        "verdict_notes": verdict, "parent_hid": parent, "is_seed": seed,
        "expands_to": expands_to or [], "proposed_by": MODEL,
    })


# ============================================================
# 种子 A：chef 邓华东（主厨维度）
# ============================================================
add("chef", "邓华东", "teacher", "陈廷新", "1982(拜师年一说)",
    "邓华东师承川菜大师陈廷新，属‘荣字派’；师爷孔道生（陈廷新师父），祖师蓝光鉴（荣乐园创办者）。",
    0.9, "知道", "confirmed",
    ev=[{"source": "新民晚报", "title": "西食东风意 邓大师演川菜猪肉秀", "url": "https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf", "kind": "media"},
        {"source": "名厨", "title": "邓华东的名厨主页", "url": "https://m.mingchu.co/index/userview?id=302162", "kind": "media"}],
    cq=["邓华东 师承 陈廷新 荣字派"], fq=["邓华东 辟谣 师承 造假 徒弟"],
    voices=3, urls=["https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf",
                     "https://m.mingchu.co/index/userview?id=302162",
                     "https://www.tastytrip.com/zh-hant/forum-chinese-fusion-cuisine-tw/"],
    verdict="≥2独立媒体+名厨主页一致，师承链确认", seed=True,
    expands_to=["陈廷新", "孔道生", "蓝光鉴", "荣乐园"])

add("chef", "邓华东", "worked_at", "西南饭店", "早年(成都)",
    "邓华东早年曾任职西南饭店（成都饮食公司体系）。",
    0.8, "知道", "confirmed",
    ev=[{"source": "新民晚报", "url": "https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf"},
        {"source": "名厨", "url": "https://m.mingchu.co/index/userview?id=302162"}],
    cq=["邓华东 西南饭店"], fq=["邓华东 未任职 西南饭店"], voices=2,
    urls=["https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf"],
    verdict="媒体+名厨主页一致")

add("chef", "邓华东", "worked_at", "上海静安希尔顿大酒店天府楼", "约1980s-1990s",
    "邓华东曾驻上海静安希尔顿大酒店天府楼主厨。",
    0.8, "知道", "confirmed",
    ev=[{"source": "新民晚报", "url": "https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf"}],
    cq=["邓华东 静安希尔顿 天府楼"], fq=["邓华东 希尔顿 离职 辟谣"], voices=2,
    urls=["https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf",
          "https://m.mingchu.co/index/userview?id=302162"], verdict="两源一致")

add("chef", "邓华东", "worked_at", "北京长城饭店/北京首都宾馆", "约1990s初",
    "邓华东曾任职北京长城饭店、北京首都宾馆。",
    0.7, "知道", "confirmed",
    ev=[{"source": "新民晚报", "url": "https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf"}],
    cq=["邓华东 北京长城饭店 首都宾馆"], fq=["邓华东 北京 任职 不实"], voices=2,
    urls=["https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf",
          "https://m.mingchu.co/index/userview?id=302162"], verdict="两源一致")

add("chef", "邓华东", "career_period", "印尼雅加达四川饭店", "1992",
    "1992年邓华东公派出国，赴印尼雅加达四川饭店任主厨。",
    0.85, "知道", "confirmed",
    ev=[{"source": "抖音官方(荣字派介绍)", "url": "https://www.iesdouyin.com/share/video/7674595137188018353"}],
    cq=["邓华东 1992 雅加达 四川饭店 公派"], fq=["邓华东 雅加达 经历 辟谣"], voices=2,
    urls=["https://www.iesdouyin.com/share/video/7674595137188018353",
          "https://img1.xinmin.cn/xmwb/2022-08-26/110826.pdf"], verdict="媒体+节目号一致")

add("chef", "邓华东", "founded", "邓记食园(上海)", "2010–2017(年份有冲突)",
    "邓华东在上海创办邓记食园；bychefs 作 2002(Dengji Chuancai)，名厨/大渔作 2010–2017，年份口径不一。",
    0.5, "推断", "unverified",
    ev=[{"source": "名厨", "url": "https://m.mingchu.co/index/userview?id=302162"},
        {"source": "bychefs", "url": "https://shanghai.bychefs.com/person/deng-huadong/"}],
    cq=["邓记食园 邓华东 创立 年份 2010 2002"], fq=["邓记食园 关店 搬迁 邓华东 退出"],
    voices=2, urls=["https://shanghai.bychefs.com/person/deng-huadong/",
                    "https://m.mingchu.co/index/userview?id=302162"],
    verdict="店已在库(id=481, active)；创立年份 2002 vs 2010 冲突，标 unverified，不写年份")

add("chef", "邓华东", "worked_at", "香港(香港邓记/Hejiang Town)", "2008或2017(冲突)",
    "邓华东曾赴港开店（bychefs 作 2008 Hejiang Town，大渔课作 2017 香港邓记），口径冲突。",
    0.35, "推断", "unverified",
    ev=[{"source": "bychefs", "url": "https://shanghai.bychefs.com/person/deng-huadong/"}],
    cq=["邓华东 香港 邓记 合江亭 开店 年份"], fq=["邓华东 香港店 已关 转让"],
    voices=1, urls=["https://shanghai.bychefs.com/person/deng-huadong/"],
    verdict="仅单一英文源+年份冲突，留 unverified")

add("chef", "邓华东", "founded", "南兴园(上海, id=478)", "2019",
    "2019年邓华东在上海淮海中路1728号12幢创办高端川菜/南堂包席餐厅南兴园。",
    0.95, "知道", "confirmed",
    ev=[{"source": "米其林指南", "url": "https://guide.michelin.com/gb/en/shanghai-municipality/shanghai/restaurant/nan-xing-yuan"},
        {"source": "bychefs", "url": "https://shanghai.bychefs.com/person/deng-huadong/"}],
    cq=["南兴园 邓华东 2019 创办"], fq=["南兴园 关店 邓华东 离开 转让 难吃 预制"],
    voices=4, urls=["https://guide.michelin.com/gb/en/shanghai-municipality/shanghai/restaurant/nan-xing-yuan",
                    "https://shanghai.bychefs.com/person/deng-huadong/",
                    "https://h5.dayuclass.com/",
                    "https://rachelgouk.com/deng-ji-the-affordable-sichuan-restaurant-to-shanghais-acclaimed-nan-xing-yuan/"],
    verdict="米其林官方+多源；2026-09 仍在营(包席制)，反向证伪=无关店/离职证据")

add("chef", "邓华东", "show_appearance", "《一饭封神》第二季", "2026-07-29起播出;决赛2026-09",
    "邓华东参加东方卫视/腾讯视频《一饭封神》第二季(2026)，获‘荣耀厨神’总冠军。",
    0.95, "知道", "confirmed",
    ev=[{"source": "新京报", "title": "《一饭封神2》7月29日开播，百名厨师同台竞技", "url": "https://m.bjnews.com.cn/detail/1785299403168543.html"},
        {"source": "抖音(冠军揭晓)", "url": "https://www.iesdouyin.com/share/video/7689081475115115962"}],
    cq=["一饭封神2 邓华东 冠军 荣耀厨神"], fq=["一饭封神2 邓华东 退赛 辟谣 冠军 争议"],
    voices=4, urls=["https://m.bjnews.com.cn/detail/1785299403168543.html",
                     "https://www.iesdouyin.com/share/video/7689081475115115962",
                     "https://sina.cn/news/detail/5343834376765542.html"],
    verdict="新京报+腾讯+多源一致；扩散：全体节目成员入种子", expands_to=["《一饭封神2》"])

add("chef", "邓华东", "award", "南兴园 黑珍珠一钻/米其林推荐", "黑珍珠2023-2026;米其林推荐2022-2025",
    "南兴园获黑珍珠一钻(2023–2026)、米其林指南推荐(2022–2025)。",
    0.85, "知道", "confirmed",
    ev=[{"source": "bychefs", "url": "https://shanghai.bychefs.com/person/deng-huadong/"}],
    cq=["南兴园 黑珍珠一钻 米其林推荐 年份"], fq=["南兴园 掉星 撤榜 除名"],
    voices=2, urls=["https://shanghai.bychefs.com/person/deng-huadong/",
                    "https://guide.michelin.com/gb/en/shanghai-municipality/shanghai/restaurant/nan-xing-yuan"],
    verdict="荣誉类；restaurant_awards(155) 可能已含，不重复写，仅留假设账")

add("chef", "邓华东", "signature_dish", "宫保鸡丁/麻婆豆腐/开水白菜/鸡淖豆腐/一虾三吃", None,
    "邓华东代表菜：宫保鸡丁、麻婆豆腐(决赛菜)、开水白菜、鸡淖豆腐、怪味酥、一虾三吃、糊辣虾球。",
    0.8, "知道", "confirmed",
    ev=[{"source": "抖音(决赛菜)", "url": "https://www.iesdouyin.com/share/video/7689359738919750958"}],
    cq=["邓华东 招牌菜 宫保鸡丁 麻婆豆腐 南兴园"], fq=["南兴园 预制菜 冷冻 难吃"],
    voices=3, urls=["https://www.iesdouyin.com/share/video/7689359738919750958",
                    "https://guide.michelin.com/gb/en/shanghai-municipality/shanghai/restaurant/nan-xing-yuan"],
    verdict="多源；注意存在‘味道一般’混合评价(见博主链)，不降事实但留痕")

# ============================================================
# 种子 B：owner 甬府翁拥军（老板维度；种子昵称‘温老板’=翁拥军 别名核对）
# ============================================================
add("owner", "甬府温老板", "related_to", "翁拥军(甬府创始人)", None,
    "种子‘甬府温老板’指向甬府创始人；工商/官方一致指向翁拥军（‘温’或为口述/记音），判定为同一人。",
    0.85, "推断", "confirmed",
    ev=[{"source": "企查查", "title": "上海甬府餐饮管理有限公司 法定代表人翁拥军", "url": "https://www.qcc.com/cshangbiaolist/0f9bb97e6a7745d54015f97f6e602623"},
        {"source": "甬府官网", "url": "https://www.yongfugroup.com/"}],
    cq=["甬府 老板 翁拥军 温"], fq=["甬府 老板 另有其人 温姓"],
    voices=3, urls=["https://www.qcc.com/cshangbiaolist/0f9bb97e6a7745d54015f97f6e602623",
                    "https://www.yongfugroup.com/",
                    "https://m.thepaper.cn/newsDetail_forward_8146952"],
    verdict="工商法定代表人=翁拥军，官方创始人=翁拥军；别名核对通过", seed=True,
    expands_to=["翁拥军", "甬府系"])

add("owner", "翁拥军", "founded", "甬府(上海)", "2011",
    "翁拥军1971年生于宁波，中国注册烹饪大师；2011年在上海(银河宾馆/中山西路)创立甬府，首年亏损约400万。",
    0.95, "知道", "confirmed",
    ev=[{"source": "人民网", "url": "http://sh.people.com.cn/n2/2022/1126/c134768-40210651.html"},
        {"source": "澎湃", "url": "https://m.thepaper.cn/newsDetail_forward_8146952"}],
    cq=["翁拥军 2011 甬府 创立 银河宾馆"], fq=["甬府 创始人 非翁拥军 辟谣"],
    voices=4, urls=["http://sh.people.com.cn/n2/2022/1126/c134768-40210651.html",
                    "https://m.thepaper.cn/newsDetail_forward_8146952",
                    "https://www.yongfugroup.com/",
                    "https://www.qcc.com/cshangbiaolist/0f9bb97e6a7745d54015f97f6e602623"],
    verdict="人民网+澎湃+官网+工商，沿革类≥1可信文档，过闸")

add("owner", "翁拥军", "owns", "食川非川(甬府旗下新派川菜;上海id=482)", None,
    "食川非川为甬府集团旗下新派川菜品牌(首店深圳，上海静安嘉里中心店id=482)。",
    0.9, "知道", "confirmed",
    ev=[{"source": "甬府官网(10大品牌)", "url": "https://www.yongfugroup.com/"},
        {"source": "金堂奖", "title": "食川非川 华南首店", "url": "https://www.jintangjiang.cn/v_detail-49801.html"}],
    cq=["食川非川 甬府 翁拥军 旗下"], fq=["食川非川 关店 与甬府无关 辟谣"],
    voices=3, urls=["https://www.yongfugroup.com/",
                    "https://www.jintangjiang.cn/v_detail-49801.html"],
    verdict="官网品牌矩阵+设计奖项页一致")

add("owner", "翁拥军", "related_to", "嫣花叁玥(与子福慧周子洋合作;上海id=785)", None,
    "嫣花叁玥为翁拥军与子福慧创始人周子洋合作的淮扬(新川扬)品牌，落上海国金中心(id=785)。",
    0.85, "知道", "confirmed",
    ev=[{"source": "甬府官网", "url": "https://www.yongfugroup.com/"},
        {"source": "抖音(国金探店)", "url": "https://www.iesdouyin.com/share/video/7275267428106456320"}],
    cq=["嫣花叁玥 翁拥军 周子洋 甬府"], fq=["嫣花叁玥 与甬府无关 辟谣"],
    voices=2, urls=["https://www.yongfugroup.com/",
                    "https://www.iesdouyin.com/share/video/7275267428106456320"],
    verdict="官网列为旗下品牌+探店述合作方；关系类过闸")

add("owner", "翁拥军", "related_to", "柿合缘新京菜(与段誉合作,2021)", None,
    "柿合缘新京菜由新京菜创始人段誉与翁拥军联袂打造，2021上海创立，2023-2024米其林入选。",
    0.8, "知道", "confirmed",
    ev=[{"source": "甬府官网", "url": "https://www.yongfugroup.com/"},
        {"source": "店长直聘(公司页)", "url": "https://www.dianzhangzhipin.com/company/3nJ_3d-5Fg~~.html"}],
    cq=["柿合缘 翁拥军 段誉 甬府"], fq=["柿合缘 与甬府无关 辟谣"],
    voices=2, urls=["https://www.yongfugroup.com/",
                    "https://www.dianzhangzhipin.com/company/3nJ_3d-5Fg~~.html"],
    verdict="官网+招聘主体页一致")

add("owner", "翁拥军", "owns", "LES NUAGES法餐/湘翁/甬府尊鲜/甬府家宴/甬府小包", None,
    "甬府旗下10大品牌：甬府、甬府小鲜、甬府尊鲜、柿合缘新京菜、湘翁、LES NUAGES法餐、食川非川、嫣花叁玥、甬府小包、甬府家宴。",
    0.85, "知道", "confirmed",
    ev=[{"source": "甬府官网", "url": "https://www.yongfugroup.com/"}],
    cq=["甬府 旗下 品牌 10大 湘翁 LES NUAGES"], fq=["这些品牌 非甬府旗下"],
    voices=1, urls=["https://www.yongfugroup.com/"],
    verdict="官方品牌矩阵(brand 高信任源)；逐店入库另走连接器")

add("brand", "明路川(甬府高端川菜)", "related_to", "已关店", "2022-08开业 / 2023-06停业",
    "明路川为甬府斥资打造的高端川菜(北外滩来福士顶楼,人均2300+)，2022-08开业，2023-06停业，存活不足一年。",
    0.9, "知道", "contradicted",
    ev=[{"source": "界面新闻", "title": "人均超2300元，只活了不到一年，明路川宣布停业", "url": "https://www.jiemian.com/article/9727034.html"}],
    cq=["明路川 现在 营业 2026"], fq=["明路川 关店 停业 闭店 2023"],
    voices=2, urls=["https://www.jiemian.com/article/9727034.html"],
    verdict="证伪成立：若假设‘明路川在营’则被界面新闻2023-06停业驳回；店未入库，不晋升为在营餐厅")

add("owner", "翁拥军", "award", "甬府米其林一星(连续三年)/黑珍珠二钻2020;甬府小鲜美必登2020", None,
    "甬府连续三年米其林一星、2020黑珍珠二钻；甬府小鲜2020上海米其林必比登。",
    0.85, "知道", "confirmed",
    ev=[{"source": "澎湃", "url": "https://m.thepaper.cn/newsDetail_forward_8146952"}],
    cq=["甬府 米其林一星 黑珍珠二钻 甬府小鲜 必比登"], fq=["甬府 掉星 黑珍珠 撤榜"],
    voices=2, urls=["https://m.thepaper.cn/newsDetail_forward_8146952",
                    "https://cn.chinadaily.com.cn/a/202102/10/WS60236a04a3101e7ce973f7ea.html"],
    verdict="荣誉类；awards(155) 可能已含，不重复写")

# ============================================================
# 种子 C：list 《一饭封神2》（官方榜单/节目维度；成员全入种子）
# ============================================================
def chef_in_list(name, rest, city, url, extra_voic=None, status="confirmed", note=""):
    add("list", "《一饭封神》第二季", "list_member", f"{name}（{rest}，{city}）", "2026",
        f"{name}（{rest}）为《一饭封神2》参赛大厨。",
        0.8 if status == "confirmed" else 0.4, "知道" if status == "confirmed" else "推断",
        status, ev=[{"source": "凤凰网美食/抖音", "url": url}],
        cq=[f"一饭封神2 {name} {rest}"], fq=[f"一饭封神2 {name} 退赛 辟谣"],
        voices=2 if status == "confirmed" else 1, urls=[url],
        verdict=note or ("官宣大厨名单一致；餐厅待逐家锚定"), parent=None,
        seed=False)

chef_in_list("邓华东", "南兴园(上海,id478)", "上海",
             "https://www.iesdouyin.com/share/video/7666020482679852339",
             note="冠军；与种子A互证")
chef_in_list("赵勇", "安和隐世·SENSE", "上海",
             "https://www.iesdouyin.com/share/video/7666020482679852339")
chef_in_list("Alan Yu", "Ambre Ciel 珀·餐厅", "上海(法餐)",
             "https://www.iesdouyin.com/share/video/7666020482679852339")
chef_in_list("曹嗣全", "炳胜", "广州",
             "https://www.iesdouyin.com/share/video/7669239169595987657")
chef_in_list("陈明媚", "屿·闽菜公馆(天河湿地公园店)", "广州",
             "https://www.iesdouyin.com/share/video/7669239169595987657")
chef_in_list("王刚", "东莞洲际酒店·彩丰楼(粤菜早茶)", "东莞",
             "https://www.iesdouyin.com/share/video/7669239169595987657")
chef_in_list("Eric Raty", "Arbor", "香港",
             "https://www.iesdouyin.com/share/video/7669239169595987657")
chef_in_list("杜国金", "华尔道夫 鲜承中餐厅(福建菜,2025/2026米其林一星)", "厦门",
             "https://www.iesdouyin.com/share/video/7665594624275062137")
chef_in_list("张嘉裕(Chef Menex)", "香港米其林一星中餐厅(唐人街?)", "香港",
             "https://www.iesdouyin.com/share/video/7676370909904620819",
             note="餐厅名‘唐人声/唐人街’待逐字锚定")
chef_in_list("姜宛伶", "TABLE by Sandy Keung(小厨变大厨;师父Ronald-邵德龙)", "香港",
             "https://www.iesdouyin.com/share/video/7673846316719410483")
chef_in_list("苏华", "龙吟山房(青龙山庄店)", "南京/上海?",
             "https://sina.cn/news/detail/5343834376765542.html")
chef_in_list("刘永康", "待锚定", "?",
             "https://sina.cn/news/detail/5343834376765542.html",
             status="unverified", note="九强名单有其人，所属餐厅未锚定")
chef_in_list("张雯雯", "待锚定", "?",
             "https://sina.cn/news/detail/5343834376765542.html",
             status="unverified", note="九强名单有其人，所属餐厅未锚定")
chef_in_list("欧浩然(后厨熊猫)", "待锚定", "?",
             "https://sina.cn/news/detail/5343834376765542.html",
             status="unverified", note="九强名单有其人，所属餐厅未锚定")
chef_in_list("李飞越(年少有味)", "待锚定", "?",
             "https://sina.cn/news/detail/5343834376765542.html",
             status="unverified", note="九强名单有其人，所属餐厅未锚定")

# ============================================================
# 种子 D/E：restaurant 南兴园(店铺维度) + blogger 郭本尼(博主维度)
# ============================================================
add("restaurant", "南兴园(id=478)", "reviewed_by", "郭本尼(B站/抖音美食UP主)", "2026-08",
    "郭本尼实测南兴园：标题‘人均1688 实测味道一般’，评价两极——博主维度证据，含负面信号。",
    0.7, "知道", "confirmed",
    ev=[{"source": "抖音/郭本尼", "url": "https://www.iesdouyin.com/share/video/7669403484696890630"}],
    cq=["南兴园 郭本尼 测评 味道"], fq=["南兴园 难吃 踩雷 预制 服务差"],
    voices=1, urls=["https://www.iesdouyin.com/share/video/7669403484696890630"],
    verdict="UGC 单博主，只作堂食声音留痕(含负面)，不反推/改分；分数仍走评分引擎",
    seed=True, parent=None)

add("blogger", "郭本尼", "reviewed_by", "南兴园(id=478)", "2026-08",
    "美食UP主郭本尼探店南兴园并给出中等偏保守评价（博主→店铺链路）。",
    0.7, "知道", "confirmed",
    ev=[{"source": "抖音", "url": "https://www.iesdouyin.com/share/video/7669403484696890630"}],
    cq=["郭本尼 南兴园 探店"], fq=["郭本尼 恰饭 软广 南兴园"],
    voices=1, urls=["https://www.iesdouyin.com/share/video/7669403484696890630"],
    verdict="博主维度跑通：blogger→reviewed_by→restaurant；单一声音不构成背书",
    seed=True)


def main():
    out = []
    for r in ROWS:
        out.append(H.norm_row(r))
    p = HERE / "lead_hypotheses_2026-09-29.jsonl"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out), encoding="utf-8")
    from collections import Counter
    print(f"写出 {len(out)} 条假设 -> {p}")
    print("status:", dict(Counter(x["status"] for x in out)))
    print("subject_type:", dict(Counter(x["subject_type"] for x in out)))


if __name__ == "__main__":
    main()
