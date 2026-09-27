#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""social_discovery.py — 社交声音「开放式发现」采集器（区别于 xhs_collect 的"已知店取证"）。

为什么存在：旧管线只按"店名/地图关键词"抓店——平台 SEO 强的网红/连锁（sunflour、苹果花园）
一抓就进，而靠食客口碑传播、平台 SEO 弱的社区宝藏（Proustmoment、time&flour、orenda bay、
overbakery）搜不到。本模块改为搜"食客在讨论哪些店"，从语义笔记正文 + 评论区里捞候选，
评论区是二级来源（本地人常在这里报真名、推荐"真正好吃的另一家"）。

在 mac_computer_use_tool(plane="bu") cell 内调用：
    import sys; sys.path.insert(0, PIPE)
    import social_discovery as D
    D.run_discovery(bu, RAW, category="bread", batch=0, notes_per_query=4)

铁律（教训 #54）：真实坐标点击让 URL 带 xsec_token，禁 JS click；单浏览器串行、断点续跑。
本模块只做机械采集，"候选店名提取 + 是否够格收录"交给 admission_gate.py（离线、不耗浏览器）。
"""
import json
import pathlib
import sys

try:
    import xhs_collect as X
except Exception:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import xhs_collect as X

# 开放式发现词矩阵（不含城市，X.search 自动拼 city）。按"品类总览/口碑语义/子品类/合集/跨语"组织。
DISCOVERY_QUERIES = {
    "bread": [
        "面包店 私藏 回购 舍不得公开",
        "酸种面包 推荐 好吃",
        "可颂 起酥 天花板 层次",
        "贝果 好吃 推荐 口感",
        "面包 红黑榜 合集 盘点",
        "社区面包店 本地人 常买",
        "欧包 乡村面包 全麦",
        "日式面包 推荐 生吐司",
        "面包 无广 真实测评 踩雷",
        "best bakery sourdough",
    ],
    "sushi": [
        "寿司 omakase 老饕私藏",
        "鮨 江户前 排行榜",
        "板前寿司 预约难 提前多久",
        "性价比 omakase 推荐 千元以下",
        "寿司 无广 真实测评 踩雷",
        "omakase 主厨发办 菜单 揭秘",
        "江户前寿司 職人 鲔鱼大腹",
        "sushi bar counter 熟客 吧台",
        "omakase 红黑榜 合集",
        "best sushi omakase tokyo style",
    ],
    "tea_house": [
        "茶馆 老茶客 私藏 舍不得公开",
        "茶室 岩茶 普洱 推荐 老白茶",
        "喝茶 安静 宝藏 独处",
        "茶馆 预约制 无门头 老洋房",
        "老茶馆 复购 茶客 日常",
        "工夫茶 泡茶 专业茶室",
        "茶馆 商务 包间 谈事",
        "新式茶馆 围炉煮茶 避雷",
        "茶馆 红黑榜 合集 盘点",
        "老洋房茶馆 赉安 历史建筑",
    ],
    "guangxi_fish": [
        "广西鱼生 横县鱼生 推荐",
        "吊水皖鱼 现杀 鱼生 现切",
        "顺德鱼生 广式鱼生 推荐",
        "横县鱼生 配料 花生油 紫苏",
        "鱼生 现点现杀 活水 吊水",
        "脆肉鲩鱼生 鱼片 薄切",
        "广西菜 鱼生 老乡 同乡",
        "鱼生 夜宵 凌晨 营业",
        "鱼生 无广 真实测评 踩雷",
        "广西酸粥 鱼生 配菜 木瓜丝",
    ],
    "market_food": [
        "菜市场 美食 宝藏 阿姨排队",
        "菜场 熟食 熏鱼 羌饼 爆鱼",
        "社区菜场 本地人 常买 早餐",
        "菜场 小吃 碳水 一条街",
        "老面 羌饼 油条 豆浆 排队",
        "现炸 熏鱼 糟鸡 白斩鸡 档口",
        "菜场 蛋糕 奶油 下午售罄",
        "菜场 鱼丸 手工 手工肉丸",
        "菜场美食 红黑榜 合集",
        "爷叔 阿姨 排队 老字号 熟食",
    ],
    "private_kitchen": [
        "私房菜 预约制 无门头",
        "私宴 家宴 主厨发办 tasting",
        "楼中店 小区里 美食 隐藏",
        "私房菜 老饕 私藏 菜单",
        "家宴 厨师上门 私厨 套餐",
        "私厨 工作室 预约 几桌",
        "私房菜 无菜单 主厨安排",
        "胡同老房子 洋房 私房菜",
        "私宴 红黑榜 合集 避雷",
        "chef's table hidden private kitchen",
    ],
}


def _append(path, rec):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def done_queries(path):
    s = set()
    p = pathlib.Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("kind") == "discover":
                    s.add(r.get("query"))
            except Exception:
                pass
    return s


def _gather_one_query(bu, query, notes_per_query, city):
    X.search(bu, query, city)
    positions = X.note_positions(bu, limit=notes_per_query + 4)
    notes, seen_url = [], set()
    for p in positions:
        if len(notes) >= notes_per_query:
            break
        info = X.open_note(bu, p["x"], p["y"])
        if not info.get("ok"):
            continue
        if info.get("url") in seen_url:
            X.close_note(bu)
            continue
        seen_url.add(info.get("url"))
        comments = X.scroll_and_get_comments(bu)
        X.close_note(bu)
        notes.append({"title": info["title"], "author": info["author"], "date": info["date"],
                      "desc": info["desc"], "url": info["url"], "comments": comments})
    return notes


def run_discovery(bu, raw_path, category="bread", batch=0, per_batch=5,
                  notes_per_query=4, city="上海"):
    """按批次跑发现词。batch=0 跑前 per_batch 个，1 跑接下来 per_batch 个，依此类推。"""
    words = DISCOVERY_QUERIES[category]
    start, end = batch * per_batch, min((batch + 1) * per_batch, len(words))
    todo = words[start:end]
    done = done_queries(raw_path)
    ran = []
    for q in todo:
        if q in done:
            continue
        notes = _gather_one_query(bu, q, notes_per_query, city)
        _append(raw_path, {"kind": "discover", "category": category, "query": q,
                           "city": city, "notes": notes})
        ran.append(q)
        print(f"  [{q}] 采集 {len(notes)} 篇")
    remaining = len([w for w in words if w not in done])
    print(f"本批跑 {len(ran)} 词；该品类剩余未跑 {remaining} 词")
    return {"ran": len(ran), "queries": ran, "remaining": remaining}
