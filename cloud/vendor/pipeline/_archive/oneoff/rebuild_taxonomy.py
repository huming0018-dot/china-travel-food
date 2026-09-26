#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_taxonomy.py — 菜系树重构（旧四大根 → 大陆→国家新树 + 非正餐场景树）

设计原则：
1. 一级为虚拟根（不建行，只作 parent_category 字符串）：
   中餐 / 亚洲 / 欧洲 / 非洲 / 北美洲 / 南美洲 / 融合菜 / 非正餐
2. 优先复用现有标签（PATCH parent_category / name，保留 id → 关联不断）；
   只在确实缺失时新建（POST 后按 name+dimension+parent 回查，幂等可重跑）。
3. 默认 dry-run；--commit 才写。写后输出 name+parent → id 映射 JSON。

用法：
  python3 rebuild_taxonomy.py                 # 预演
  python3 rebuild_taxonomy.py --commit        # 执行
  python3 rebuild_taxonomy.py --commit -o map.json
"""
import argparse
import json
import pathlib
import sys
import time

import common as C

# 一级虚拟根（不是标签行）
VIRTUAL_ROOTS = {"中餐", "亚洲", "欧洲", "非洲", "北美洲", "南美洲", "融合菜", "非正餐"}

# —— 现有标签 PATCH：id → (new_parent_category, new_name or None) ——
PATCH_TAGS = {
    # 欧洲（原 parent=西餐）
    26: ("欧洲", None), 27: ("欧洲", None), 28: ("欧洲", None), 29: ("欧洲", None),
    30: ("欧洲", None), 32: ("欧洲", None), 33: ("欧洲", None), 34: ("欧洲", None),
    # 北美洲
    31: ("北美洲", None),            # 美餐
    42: ("北美洲", "墨西哥菜"),       # 墨西哥/拉美菜 → 墨西哥菜
    # 亚洲（原 parent=亚洲菜）
    35: ("亚洲", None), 36: ("亚洲", None), 37: ("亚洲", None), 38: ("亚洲", None),
    39: ("亚洲", None), 40: ("亚洲", None), 41: ("亚洲", None), 85: ("亚洲", None),
    # 非洲 / 融合菜（原 parent=其他）
    43: ("非洲", None),
    44: ("融合菜", None),
    # 日料面类：id236「乌冬·荞麦」→「乌冬」（荞麦另建）
    236: (None, "乌冬"),
}

# —— 新建标签：(name, dimension, parent) ——
NEW_TAGS = [
    # 中餐新增菜系
    ("创新菜", "菜系", "中餐"),

    # 亚洲·日本·面类三级拆分
    ("荞麦", "菜系", "日料/日本料理"),
    ("拉面·虾白汤", "菜系", "拉面"),
    ("拉面·柚子盐鸡白汤", "菜系", "拉面"),
    ("拉面·博多豚骨", "菜系", "拉面"),
    ("拉面·蘸面", "菜系", "拉面"),
    ("拉面·二郎系", "菜系", "拉面"),
    ("拉面·横滨家系", "菜系", "拉面"),
    ("拉面·纪州酱油豚骨", "菜系", "拉面"),
    ("拉面·熊本黑蒜味噌", "菜系", "拉面"),
    ("荞麦·冷荞麦/山药泥", "菜系", "荞麦"),
    ("荞麦·天妇罗盛荞麦", "菜系", "荞麦"),
    ("荞麦·十割/二八", "菜系", "荞麦"),
    ("乌冬·赞岐", "菜系", "乌冬"),
    ("乌冬·咖喱", "菜系", "乌冬"),
    ("乌冬·手打", "菜系", "乌冬"),

    # 欧洲新增国家
    ("奥地利", "菜系", "欧洲"),
    ("比利时", "菜系", "欧洲"),
    ("维也纳炸猪排", "菜系", "奥地利"),
    ("维也纳烤肋排/皇帝松饼", "菜系", "奥地利"),
    ("比利时啤酒/华夫饼", "菜系", "比利时"),
    ("比利时青口贝/薯条", "菜系", "比利时"),

    # 非洲
    ("摩洛哥", "菜系", "非洲"),
    ("南非", "菜系", "非洲"),
    ("摩洛哥塔吉锅正餐", "菜系", "摩洛哥"),
    ("Couscous库斯库斯", "菜系", "摩洛哥"),
    ("南非正餐/烤肉", "菜系", "南非"),
    ("Bobotie马来风味派", "菜系", "南非"),

    # 北美洲·墨西哥三级
    ("Tex-Mex", "菜系", "墨西哥菜"),
    ("创意Taco/Quesadilla", "菜系", "墨西哥菜"),

    # 南美洲
    ("巴西", "菜系", "南美洲"),
    ("秘鲁", "菜系", "南美洲"),
    ("阿根廷", "菜系", "南美洲"),
    ("智利", "菜系", "南美洲"),
    ("巴西烤肉Churrasco自助", "菜系", "巴西"),
    ("巴西烤牛舌/烤菠萝", "菜系", "巴西"),
    ("秘鲁国菜Ceviche酸橘汁腌鱼", "菜系", "秘鲁"),
    ("秘鲁-西班牙融合菜", "菜系", "秘鲁"),
    ("阿根廷Asado炭烤牛排", "菜系", "阿根廷"),
    ("Empanada馅饼/Chimichurri", "菜系", "阿根廷"),

    # 非正餐场景树（二级）
    ("咖啡", "菜系", "非正餐"),
    ("面包", "菜系", "非正餐"),
    ("甜品", "菜系", "非正餐"),
    ("Bar", "菜系", "非正餐"),
    # 咖啡三级
    ("创意特调咖啡", "菜系", "咖啡"),
    ("手冲/自烘豆专门", "菜系", "咖啡"),
    ("社区精品咖啡", "菜系", "咖啡"),
    ("连锁咖啡", "菜系", "咖啡"),
    # 面包三级
    ("可颂/起酥专门", "菜系", "面包"),
    ("日式面包", "菜系", "面包"),
    ("社区烘焙坊", "菜系", "面包"),
    ("贝果专门", "菜系", "面包"),
    ("酸种面包专门", "菜系", "面包"),
    # 甜品三级
    ("冰淇淋Gelato", "菜系", "甜品"),
    ("刨冰", "菜系", "甜品"),
    ("松饼/薄饼", "菜系", "甜品"),
    ("糖水/甜汤", "菜系", "甜品"),
    ("蛋糕/法式甜品", "菜系", "甜品"),
    ("铜锣烧/和果子", "菜系", "甜品"),
    # Bar 三级
    ("威士忌吧", "菜系", "Bar"),
    ("精酿啤酒吧", "菜系", "Bar"),
    ("葡萄酒/自然酒吧", "菜系", "Bar"),
    ("鸡尾酒吧", "菜系", "Bar"),
]


def key(name, dim, parent):
    return (name or "").strip(), dim, (parent or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("-o", "--output",
                    default="/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/_taxonomy/tag_ids.json")
    args = ap.parse_args()

    rows = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    by_id = {r["id"]: r for r in rows}
    by_key = {}
    for r in rows:
        by_key.setdefault(key(r["name"], r["dimension"], r.get("parent_category")), []).append(r)

    plan_patch, plan_create = [], []

    # 1) PATCH 现有标签
    for cid, (new_parent, new_name) in PATCH_TAGS.items():
        r = by_id.get(cid)
        if not r:
            print(f"[warn] id={cid} 不存在，跳过 PATCH")
            continue
        body = {}
        if new_parent is not None and (r.get("parent_category") or "") != new_parent:
            body["parent_category"] = new_parent
        if new_name and (r.get("name") or "") != new_name:
            body["name"] = new_name
        if body:
            plan_patch.append((cid, r["name"], body))

    # 2) 新建缺失标签（保持声明顺序，父先于子）
    pending = list(NEW_TAGS)
    # 用工作副本模拟已建，保证同批次父子可解析
    work_keys = set(by_key.keys())
    for (name, dim, parent) in NEW_TAGS:
        k = key(name, dim, parent)
        if k in work_keys:
            continue
        plan_create.append((name, dim, parent))
        work_keys.add(k)  # 视为将建

    print(f"=== 预演（{'COMMIT' if args.commit else 'DRY-RUN'}）===")
    print(f"PATCH {len(plan_patch)} 个标签：")
    for cid, nm, body in plan_patch:
        print(f"  id{cid} 「{nm}」→ {body}")
    print(f"CREATE {len(plan_create)} 个标签：")
    for name, dim, parent in plan_create:
        print(f"  [{dim}] {parent or '∅'} / {name}")

    if not args.commit:
        print("\ndry-run，未写库；确认后加 --commit")
        return

    # 执行 PATCH
    for cid, nm, body in plan_patch:
        r = C.req("PATCH", f"/cuisines?id=eq.{cid}", json=body)
        if r.status_code not in (200, 204):
            sys.exit(f"PATCH id{cid} 失败: {r.status_code} {r.text[:200]}")
        time.sleep(0.12)

    # 执行 CREATE（逐个回查拿 id）
    for name, dim, parent in plan_create:
        body = {"name": name, "dimension": dim}
        if parent:
            body["parent_category"] = parent
        r = C.req("POST", "/cuisines", json=body)
        if r.status_code not in (200, 201):
            sys.exit(f"CREATE {body} 失败: {r.status_code} {r.text[:200]}")
        time.sleep(0.2)
        q = {"name": f"eq.{name}", "dimension": f"eq.{dim}",
             "select": "id,name,dimension,parent_category"}
        got = C.req("GET", "/cuisines", params=q).json()
        if parent:
            got = [x for x in got if (x.get("parent_category") or "") == parent]
        if not got:
            sys.exit(f"CREATE 后回查不到: {body}")

    # 重新拉全表，输出映射
    final = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    out = {}
    for r in final:
        out[f"{r.get('parent_category') or '∅'}::{r['name']}::{r['dimension']}"] = r["id"]
    p = pathlib.Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成：PATCH {len(plan_patch)} / CREATE {len(plan_create)}")
    print(f"标签总数 {len(final)}；映射已写 {p}")


if __name__ == "__main__":
    main()
