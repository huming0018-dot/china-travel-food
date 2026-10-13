#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""discovery_planner.py — 深覆盖「地毯搜索」计划器（标准模块 + 可定制词根）。

输入 coverage_ledger 的缺口叶子(empty/shallow)，结合 cuisines 本体，把每个叶子展开成
按平台路由的密集查询词束，供各平台采集器消费：
  xhs / douyin / bili / weibo : 社交地毯词（正文 + **必采评论区**做图遍历扩 frontier）
  wechat : 公众号长文测评
  map    : 高德/腾讯 POI 词
发现词只给"起点"：采集器打开正文后必须扫评论区，把评论里提到的新店名加入 frontier。

用法：
  python3 discovery_planner.py --ledger /app/data/coverage/ledger.json \
      --save /app/data/coverage/discovery_plan.json
  python3 discovery_planner.py --sample 264
"""
import argparse
import json
import pathlib

import common as C

SOCIAL_TEMPLATES = [
    "上海 {t}", "{t} 推荐 好吃", "{t} 私藏 回购 舍不得公开",
    "{t} 老饕 懂吃 无广", "{t} 红黑榜 合集 盘点",
    "{c} {t} 本地人 回头客", "{t} 真实测评 踩雷",
    "{t} 主厨 传承 工作室", "{t} 预约 排队 老顾客",
    "{t} 正宗 排名", "{t} 宝藏 小店", "上海 {t} 哪家好吃",
]
WECHAT_TEMPLATES = ["上海 {t} 测评", "{t} 老店 推荐", "{c} {t} 盘点"]
MAP_TEMPLATES = ["上海 {t}", "{t}"]

EN = {
    "拉面·博多豚骨": "hakata tonkotsu ramen", "拉面·蘸面": "tsukemen",
    "拉面·二郎系": "jiro ramen", "拉面·横滨家系": "ieki ramen",
    "乌冬·赞岐": "sanuki udon", "舒芙蕾松饼": "souffle pancake",
    "甜可丽饼": "crepe", "咸galette": "galette", "东欧菜": "eastern european food",
    "新中式茶饮": "new chinese tea", "港式奶茶·茶室": "hong kong milk tea",
    "智利": "chilean food", "法式Bistro": "french bistro",
}
TAGGY = {"外卖/外带", "上海老字号", "美食广场/Food Court", "私宴/会所"}


def load_cuisines():
    cu = C.fetch_all("cuisines", order_col="id")
    by = {x["id"]: x for x in cu}
    up = {}
    for x in cu:
        p = x.get("parent_category")
        if isinstance(p, int):
            up[x["id"]] = p
        elif isinstance(p, str) and p.isdigit():
            up[x["id"]] = int(p)
    return by, up


def lineage(cid, by, up):
    chain, cur, seen = [], cid, set()
    while cur in by and cur not in seen:
        seen.add(cur)
        chain.append(by[cur]["name"])
        cur = up.get(cur)
        if cur is None:
            break
    return list(reversed(chain))


def natural_terms(t, parent_name=""):
    """把"拉面·博多豚骨"这类叶子名转成真实搜索词：博多豚骨拉面 / 博多豚骨。"""
    terms = [t]
    if "·" in t:
        pre, style = t.split("·", 1)
        if parent_name:
            terms.append(f"{style}{parent_name}")  # 博多豚骨拉面 / 赞岐乌冬
        terms.append(style)
        terms.append(f"{style}{pre}")
    out, seen = [], set()
    for x in terms:
        x = x.strip()
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out


def build_bundle(leaf, by, up):
    cid = leaf["id"]; t = leaf["name"]
    chain = lineage(cid, by, up)
    pid = up.get(cid)
    pname = by[pid]["name"] if pid in by else ""
    nats = natural_terms(t, pname)
    primary = nats[1] if len(nats) > 1 and pname else nats[0]
    c = chain[0] if len(chain) > 1 else pname
    social, seen = [], set()

    def add(q):
        q = " ".join(q.split())
        if q not in seen:
            seen.add(q); social.append(q)

    for tpl in SOCIAL_TEMPLATES:
        add(tpl.format(t=primary, c=c))
    for extra in nats:
        add(extra)
    en = EN.get(t)
    if en:
        add(f"best {en} shanghai")
    return {
        "id": cid, "name": t, "lineage": chain,
        "priority": 2 if t in TAGGY else (0 if leaf["status"] == "empty" else 1),
        "queries": {
            "xhs": social, "douyin": social[:8], "bili": social[:8],
            "weibo": social[:8],
            "wechat": [x.format(t=primary, c=c) for x in WECHAT_TEMPLATES],
            "map": [x.format(t=primary) for x in MAP_TEMPLATES],
        },
        "mine_comments": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="/app/data/coverage/ledger.json")
    ap.add_argument("--save", default="/app/data/coverage/discovery_plan.json")
    ap.add_argument("--sample", type=int, default=0)
    args = ap.parse_args()

    by, up = load_cuisines()
    ledger = json.loads(pathlib.Path(args.ledger).read_text(encoding="utf-8"))
    gaps = [x for x in ledger if x.get("leaf") and x["status"] in ("empty", "shallow")]
    bundles = [build_bundle(x, by, up) for x in gaps]
    bundles.sort(key=lambda b: (b["priority"], b["id"]))

    if args.sample:
        b = next((z for z in bundles if z["id"] == args.sample), None)
        print(json.dumps(b, ensure_ascii=False, indent=1) if b else "not in gaps")
        return

    total_q = sum(len(v) for b in bundles for v in b["queries"].values())
    print(f"缺口叶子 {len(bundles)}，地毯查询总数 {total_q}")
    for b in bundles[:12]:
        print(f"  p{b['priority']} {b['id']:>3} {b['name']:<18} xhs词{len(b['queries']['xhs'])}  路径{' > '.join(b['lineage'])}")

    p = pathlib.Path(args.save)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bundles, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nsaved -> {args.save}")


if __name__ == "__main__":
    main()
