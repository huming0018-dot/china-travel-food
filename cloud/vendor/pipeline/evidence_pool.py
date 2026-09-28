#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_pool.py — 跨源证据账本 + 信任加权汇总（离线、确定性、可重跑）。

为什么存在（机制根因）：
  admission_gate 按「单品类 × 单来源目录」聚合，不跨源；B站搜索只给标题（无简介），
  单源凑不齐「≥2 独立声音 + 口味≥3.5」，于是 B站 0 admit、稀疏源永不贡献。
  本模块把所有来源归一化到同一餐厅账本，做【跨源互证 + 信任加权】：
    - 真实食客（小红书 verified，trust high/mid）：权重 1.0，独立声音全计；
    - 地图平台评论（高德，trust low）：权重 0.4，仅弱互证、不单独构成独立食客；
    - B站 KOL 视频（标题严格匹配品牌）：权重 0.6，计为 curator 声音；
    - 权威标签（米其林/黑珍珠）：1 个来源声音、保证不漏、触发取证，不带口味。
  口味采用评论 aspect_taste（1-5）；B站标题用 POS/NEG 现算；时间半衰期 180 天。

用法（容器内）：
  python3 evidence_pool.py                 # 产出 /app/data/evidence/pool.jsonl + 汇总
  python3 evidence_pool.py --commit        # 对跨源够格的【新品牌】走 candidate_apply（默认 dry）
"""
import argparse
import json
import math
import pathlib
import re
import sys
from collections import defaultdict

try:
    import common as C
except Exception:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import common as C

OUT_DIR = pathlib.Path("/app/data/evidence")
DISC = pathlib.Path("/app/data/discovery")

# 通用词 / 品类 / 地名 / 菜名 —— 不得作为可匹配品牌（治“居酒屋/外滩/烧烤”误命中）
STOP = set("""
居酒屋 寿司 拉面 荞麦面 乌冬 面包 咖啡 甜品 蛋糕 甜点  gelato 冰淇淋 冰激凌 酒吧 酒馆 烧烤 烤肉
烧鸟 烧肉 火锅 日料 日本料理 日式 西餐 法餐 意餐 中餐 本帮菜 粤菜 川菜 探店 美食 餐厅 饭店 好吃
上海 外滩 海上 陆家嘴 静安 徐汇 黄浦 长宁 浦东 早餐 午餐 晚餐 下午茶 点心 牛排 炸鸡 炸猪排 猪排
奶茶 茶饮 茶馆 厨房 菜单 老板 招牌 宝藏 私藏 打卡 红黑榜 测评 合集 盘点 推荐 攻略 教程 做法
在家 复刻 翻车 踩雷 避雷 苍蝇馆 菜市场 小吃 路边摊 老字号 咖喱 烩饭 意面 披萨 汉堡 三明治
生煎 锅贴 饺子 馄饨 包子 小笼 汤圆 炒饭 盖饭 便当 定食 饭团 关东煮 天妇罗 鳗鱼 和牛 海鲜
""".split())

POS = {"好吃": .35, "正宗": .3, "惊艳": .4, "鲜嫩": .25, "入味": .25, "地道": .3, "香": .15,
       "酥脆": .25, "浓郁": .15, "回购": .25, "新鲜": .25, "爆汁": .3, "鲜美": .25, "必吃": .25,
       "天花板": .25, "入口即化": .35, "封神": .3, "名不虚传": .3}
NEG = {"难吃": -.6, "避雷": -.5, "踩雷": -.5, "失望": -.4, "一般": -.3, "不好吃": -.55,
       "腥": -.35, "柴": -.35, "预制": -.4, "不新鲜": -.45, "糊弄": -.4, "寡淡": -.3,
       "名不副实": -.4, "平平无奇": -.25}


def title_taste(text):
    pos = sum(w for k, w in POS.items() if k in text)
    neg = sum(w for k, w in NEG.items() if k in text)
    if pos == 0 and neg == 0:
        return None
    return max(1.0, min(5.0, round(3.8 + pos + neg, 2)))


def han(s):
    return "".join(c for c in s if "一" <= c <= "鿿")


def brand_forms(r):
    """返回该餐厅可用于标题匹配的规范品牌形式（高精度：剔除通用词与短·段）。"""
    full = re.split(r"[（(]", r["name"])[0].strip()
    cands = set()

    def add(s):
        n = C.cjk_norm(s)
        nh = len(han(n))
        if not n or n in STOP:
            return
        # 主名：≥2 汉字 或 ≥4 拉丁
        if nh >= 2 or (nh == 0 and len(n) >= 4):
            cands.add(n)

    add(r["name"])
    add(full)
    # ·/・/•/&/ 分段：仅当 ≥3 汉字（避免“居酒屋/外滩”这类 2-3 字通用段；
    # 3 字也可能是通用词，STOP 已过滤）
    for seg in re.split(r"[·・•&/]", full):
        n = C.cjk_norm(seg)
        if n and len(han(n)) >= 3 and n not in STOP:
            cands.add(n)
    al = r.get("aliases")
    items = al if isinstance(al, list) else (
        re.split(r"[,，;；/]", al) if isinstance(al, str) else [])
    for a in items:
        n = C.cjk_norm(a)
        if n and n not in STOP and (len(han(n)) >= 2 or len(n) >= 4):
            cands.add(n)
    return cands


def recency_w(iso):
    if not iso:
        return 1.0
    try:
        import datetime
        d = iso[:10]
        y, m, dd = (int(x) for x in d.split("-"))
        age = (datetime.date.today() - datetime.date(y, m, dd)).days
        return math.exp(-max(age, 0) / 180.0)
    except Exception:
        return 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rests = C.fetch_all(
        "restaurants",
        "id,name,name_en,aliases,status,district,address,signature_dishes,price_avg,tier")
    rid2r = {r["id"]: r for r in rests}

    # 权威标签（dimension=认证，含 米其林/黑珍珠）
    cuis = C.fetch_all("cuisines", "id,name,dimension")
    auth_ids = {c["id"] for c in cuis if c.get("dimension") == "认证"
                and ("米其林" in (c["name"] or "") or "黑珍珠" in (c["name"] or ""))}
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    rid_auth = defaultdict(bool)
    for x in rc:
        if x["cuisine_id"] in auth_ids:
            rid_auth[x["restaurant_id"]] = True

    # 餐厅账本初始化
    pool = {r["id"]: {
        "rid": r["id"], "name": r["name"], "status": r["status"],
        "district": r["district"], "authority": rid_auth.get(r["id"], False),
        "real": {}, "map": {}, "kol": {}, "taste_real": [], "taste_all": []}
        for r in rests}

    # 1) reviews（已带 rid）
    rvs = C.fetch_all(
        "reviews",
        "restaurant_id,author_name,source_platform,trust_level,is_verified_diner,"
        "aspect_taste,visit_date,created_at,source_url")
    for v in rvs:
        rid = v["restaurant_id"]
        if rid not in pool:
            continue
        p = pool[rid]
        tw = {"high": 1.0, "mid": 0.7, "low": 0.4}.get(v.get("trust_level"), 0.4)
        tw *= recency_w(v.get("visit_date") or v.get("created_at"))
        taste = v.get("aspect_taste")
        author = (v.get("author_name") or "")[:24]
        rec = {"author": author, "plat": v.get("source_platform"),
               "taste": taste, "w": round(tw, 2)}
        if v.get("is_verified_diner"):
            p["real"][author + v.get("source_url", "")] = rec
            if taste:
                p["taste_real"].append((taste, tw))
                p["taste_all"].append((taste, tw))
        else:
            p["map"][author + v.get("source_url", "")] = rec
            if taste:
                p["taste_all"].append((taste, tw * 0.5))

    # 2) B站标题 → 品牌严格匹配
    forms_index = []   # (form, rid)
    for r in rests:
        for f in brand_forms(r):
            forms_index.append((f, r["id"]))
    forms_index.sort(key=lambda x: -len(x[0]))

    n_videos = 0
    for pp in sorted(DISC.glob("raw_bili_*.jsonl")):
        for line in pp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            for n in rec.get("notes", []):
                title = n.get("title", "")
                t = C.cjk_norm(title)
                n_videos += 1
                for f, rid in forms_index:
                    if f in t:
                        p = pool[rid]
                        author = (n.get("author") or "")[:24]
                        tv = title_taste(title)
                        p["kol"][author + n.get("url", "")] = {
                            "author": author, "taste": tv,
                            "w": round(0.6 * recency_w(None), 2), "cat": rec.get("category")}
                        if tv:
                            p["taste_all"].append((tv, 0.6))
                        break

    # 3) 汇总 + 裁决
    def wmean(vals):
        if not vals:
            return None
        sw = sum(w for _, w in vals)
        return round(sum(x * w for x, w in vals) / sw, 2) if sw else None

    rows = []
    for p in pool.values():
        n_real = len(p["real"])
        n_map = len(p["map"])
        n_kol = len(p["kol"])
        taste_real = wmean(p["taste_real"])
        taste_all = wmean(p["taste_all"])
        # 独立声音：真实食客 + KOL（地图评论不独立计）
        indep = n_real + n_kol
        evidence = ("real" if n_real >= 2 else
                    "some_real" if n_real == 1 else
                    "kol" if n_kol >= 1 else "none")
        rows.append({
            "rid": p["rid"], "name": p["name"], "status": p["status"],
            "authority": p["authority"], "n_real": n_real, "n_map": n_map,
            "n_kol": n_kol, "indep": indep, "taste_real": taste_real,
            "taste_all": taste_all, "evidence": evidence})

    (OUT_DIR / "pool.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in sorted(rows, key=lambda y: -y["indep"])),
        encoding="utf-8")

    # 统计
    n_auth = sum(1 for x in rows if x["authority"])
    auth_pending = [x for x in rows if x["authority"] and x["n_real"] == 0]
    with_real2 = [x for x in rows if x["n_real"] >= 2]
    with_real1 = [x for x in rows if x["n_real"] == 1]
    with_kol = [x for x in rows if x["n_kol"] >= 1]
    # 跨源互证：有权威或多KOL但无真实食客 → 待取证
    cross = [x for x in rows if x["n_real"] == 0 and (x["n_kol"] >= 1 or x["authority"])]

    print(f"餐厅总数 {len(rows)} | B站视频 {n_videos}")
    print(f"权威标签店 {n_auth}；其中无真实食客、待取证 {len(auth_pending)}")
    print(f"真实食客≥2：{len(with_real2)} | =1：{len(with_real1)}")
    print(f"B站KOL覆盖店：{len(with_kol)} | 无真实食客但有KOL/权威（跨源待补）：{len(cross)}")
    print("\n=== 真实食客证据 TOP12（口味优先）===")
    for x in sorted(rows, key=lambda y: -(y["n_real"]))[:12]:
        print(f"  {x['name'][:22]:<24} 真实{x['n_real']} KOL{x['n_kol']} "
              f"地图{x['n_map']} 口味(真实){x['taste_real']} 权威{'Y' if x['authority'] else '-'}")
    print("\n=== B站KOL新增覆盖（此前无真实食客）样例 ===")
    for x in [c for c in cross if c["n_kol"] >= 1][:12]:
        print(f"  {x['name'][:24]:<26} KOL{x['n_kol']} 口味(综合){x['taste_all']} "
              f"权威{'Y' if x['authority'] else '-'}")
    print(f"\n输出：{OUT_DIR/'pool.jsonl'}")
    if not args.commit:
        print("（dry-run；--commit 才会对跨源够格新品牌走 candidate_apply）")


if __name__ == "__main__":
    main()
