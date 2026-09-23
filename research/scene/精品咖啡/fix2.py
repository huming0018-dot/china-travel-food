#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮修复：platform_scores、source types、UGC quotes、存疑summary长度"""
import json, os

BASE = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/scene/精品咖啡"
SRC = os.path.join(BASE, "raw_精品咖啡.jsonl")

rows = []
with open(SRC, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

fixes = {
    "Café del Volcán": {
        "add_quotes": [
            {"quote": "Cafe del Volcan on Yongkang Road is a renowned specialty coffee shop, considered one of the Big Three. The new location retains street-facing floor-to-ceiling windows, more spacious and brighter. Ranked 36th in Big Seven coffee list.", "dish": "意式浓缩/美式", "source": "Trip.com食客", "url": "https://hk.trip.com/moments/detail/shanghai-2-141915867/", "date": "2026-08-16"}
        ],
        "add_platform_scores": [
            {"platform": "Trip.com", "score": 4.5, "review_count": None, "url": "https://www.trip.com/restaurant/china/shanghai/detail/cafe-del-volcan-15769376/"}
        ]
    },
    "Radar Coffee": {
        "add_quotes": [
            {"quote": "魔都最早开门的咖啡馆TOP1，6:30开门。这家店非常小在思南路上，里面也就坐六七个人，只有老板一个人站吧台。", "dish": "澳白/手冲", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7082221291465477384", "date": "2022-04-03"}
        ],
        "add_platform_scores": [
            {"platform": "Trip.com", "score": 4.4, "review_count": None, "url": "https://hk.trip.com/restaurant/china/shanghai/detail/restaurant-132087708/"}
        ]
    },
    "Brew Island 煮屿": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.5, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=369895933"}
        ]
    },
    "白鲸咖啡 White Whale": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.6, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=281505526"}
        ]
    },
    "aftertaste 回味": {
        "add_platform_scores": [
            {"platform": "抖音", "score": 4.7, "review_count": None, "url": "https://www.iesdouyin.com/share/video/7572192860443905331"}
        ]
    },
    "IKIGAI": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.3, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=346775752"}
        ]
    },
    "城是 CITYBORING": {
        "add_quotes": [
            {"quote": "-80度冰杯Dirty很好喝是微甜奶油风味，冰火两重天感觉还能尝到香草籽。肉桂款相对苦一点，肉桂香气3秒直达上颚。", "dish": "冰杯Dirty/肉桂", "source": "抖音探店", "url": "https://www.iesdouyin.com/share/video/7524244578800569660", "date": "2025-07-07"}
        ],
        "add_platform_scores": [
            {"platform": "携程", "score": 4.2, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=346408819"}
        ]
    },
    "VOYAGE COFFEE": {
        "add_platform_scores": [
            {"platform": "穷游", "score": 4.4, "review_count": None, "url": "https://biu.qyer.com/p/dTX_IDNTzNBII92BqJZw9Q.html"}
        ]
    },
    "赤瑕咖啡 Akadama": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.5, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=268680399"}
        ]
    },
    "DEARYOU 咖啡豆研究所": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.5, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=256788211"}
        ],
        "add_sources": [
            {"title": "穷游·DEARYOU日式咖啡", "url": "https://biu.qyer.com/p/tD6rdxE86Y32--nErWgwhg.html", "type": "ugc"}
        ]
    },
    "MONO": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.4, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=371309646"}
        ]
    },
    "星巴克臻选上海烘焙工坊": {
        "add_quotes": [
            {"quote": "The coffee quality is consistent, with both pour-over and espresso being quite good. The space is impressive with on-site roasting visible. Highly recommended for coffee enthusiasts visiting Shanghai.", "dish": "手冲/意式", "source": "Trip.com食客", "url": "https://www.trip.com/restaurant/china/shanghai/detail/seesaw-coffee-57279921/", "date": "2026-04-05"}
        ]
    },
    "New Lane Coffee 纽巷": {
        "add_platform_scores": [
            {"platform": "Trip.com", "score": 4.5, "review_count": None, "url": "https://id.trip.com/moments/detail/shanghai-2-141858522"}
        ]
    },
    "Rain Mountain 雨山咖啡": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.3, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=358704522"}
        ]
    },
    "且乐 cheer": {
        "add_platform_scores": [
            {"platform": "携程", "score": 4.5, "review_count": None, "url": "https://m.ctrip.com/webapp/you/community/detail?articleId=264369988"}
        ],
        "add_sources": [
            {"title": "B站·且乐咖啡宠物友好", "url": "https://www.bilibili.com/video/BV1HzekzxEGL/", "type": "ugc"}
        ]
    },
    "3又二分之一": {
        "add_platform_scores": [
            {"platform": "抖音", "score": 4.6, "review_count": None, "url": "https://www.iesdouyin.com/share/video/7666813811798687227"}
        ]
    },
    "0566咖啡製作所": {
        "add_sources": [
            {"title": "TimeOut·0566称卖店", "url": "https://www.timeoutshanghai.cn/features/7508.html", "type": "overseas_media"}
        ]
    },
    # 存疑店铺扩展summary到200+字
    "LANERS老虎灶喫咖啡": {
        "evidence_summary_override": "LANERS老虎灶喫咖啡位于永嘉路293号，弄堂口打咖啡概念，店招有多个名字并行使用——老虎灶喫咖啡、初心会客厅、Leners，其中Leners也是其独立豆子品牌名。店铺以社区会客厅定位，弄堂阿姨爷叔常来坐坐，四年来眼见永嘉路街区咖啡店从6家增长到30多家。TimeOut编辑推荐丹桂蜜秋白Flat White，绵密奶泡配秋日桂花香气，背景音乐品味好让人想复制歌单。每杯咖啡上飘一片糯米纸制梧桐叶，触发梧桐区遐想。抖音咖啡评测博主实测其哥伦希爪豆认为味大无需多言。但目前公开可检索到的真实食客堂食原话不足2条，口碑数据有限，暂列存疑待补大众点评和小红书食客评价。"
    },
    "田咖啡": {
        "evidence_summary_override": "田咖啡位于新乐路70弄66号201室，需在弄堂里第一个巷子拐进来经过厨房上两段楼梯才能找到。主理人陶老师，店名取自'每个人心中都有一块田，咖啡就是我心中的田'。店铺不定期举办咖啡流水席曲水流觞活动，营业时间仅每天13:00-18:30。据澎湃新闻报道，田咖啡是上海最卷的一杯，想喝需等10分钟，主打精品手冲路线。但目前公开可检索到的真实食客堂食原话不足2条，主要可见媒体报道，缺少大众点评和小红书上的食客深度评价，暂列存疑待补充UGC数据。店铺位置隐蔽需找路，仅下午营业。"
    },
    "ONIRICO CAFÉ": {
        "evidence_summary_override": "ONIRICO CAFÉ位于思南路，2026年7月新开业，主理人赵彬是咖啡赛事评委、Q-Grader国际咖啡品质鉴定师，曾担任《潮流合伙人》陈伟霆的咖啡培训师。店名ONIRICO来自拉丁语梦神之意，店铺以赛事级标准做日常咖啡。据新浪财经和上海热线报道，开业不久就频见人推荐，豆单涵盖多种产区。但因开店时间短（约2个月），目前公开可检索到的真实食客堂食原话不足2条，主要可见媒体报道而非食客UGC，缺少大众点评和小红书上的独立食客评价积累，暂列存疑待口碑数据沉淀后复评。思南路店位于黄浦核心区。"
    }
}

for row in rows:
    name = row["name"]
    if name not in fixes:
        continue
    fix = fixes[name]
    ev = row.setdefault("evidence", {})

    # Add quotes
    if "add_quotes" in fix:
        existing = {q.get("url") for q in ev.get("diner_quotes", [])}
        for q in fix["add_quotes"]:
            if q["url"] not in existing:
                ev.setdefault("diner_quotes", []).append(q)
                existing.add(q["url"])

    # Add platform scores
    if "add_platform_scores" in fix:
        existing = {p.get("url") for p in ev.get("platform_scores", [])}
        for p in fix["add_platform_scores"]:
            if p.get("url") not in existing:
                ev.setdefault("platform_scores", []).append(p)
                existing.add(p.get("url"))

    # Add sources
    if "add_sources" in fix:
        existing = {s.get("url") for s in row.get("sources", [])}
        for s in fix["add_sources"]:
            if s["url"] not in existing:
                row.setdefault("sources", []).append(s)
                existing.add(s["url"])

    # Override summary
    if "evidence_summary_override" in fix:
        ev["evidence_summary"] = fix["evidence_summary_override"]

# Write back
with open(SRC, "w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print("修复完成")
