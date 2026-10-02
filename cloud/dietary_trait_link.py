#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dietary_trait_link.py — 菜单「饮食特质标签」提取引擎（清真 / 素食纯素 / 无麸质 / 低卡轻食）。

为什么存在（task #36，治通识问题）：
  用户需要按 清真、素食、无麸质、低卡 等饮食限制筛选；这些是 dimension='标签' 的特质，
  可与菜系叶共存。历史上没有从已采集内容里解析这些特质的模块。本引擎保守地从【结构化字段】
  （店名 / 招牌菜 / 卖点 / 语义简介）提取明确线索并挂签：
    - 店名命中=0.95；其余结构化字段命中=0.85；
    - 不采信单条评论的随口一说（review 驱动需"认证/明确多源"，留作后续），宁空不假；
    - 幂等，只补未挂的标签；dry-run 默认，--apply 写库并回读。

标签 id（cuisines，dimension=标签）：
  45 素食/纯素；372 清真 Halal；373 无麸质 Gluten-Free；374 低卡/轻食 Low-Calorie。

用法：python3 dietary_trait_link.py [--apply]
"""
import argparse
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", str(HERE / "vendor" / "pipeline"))
for _p in (HERE, PIPE, HERE / "vendor" / "pipeline"):
    if (pathlib.Path(_p) / "common.py").exists():
        sys.path.insert(0, str(_p))
        break
import common as C  # noqa: E402

# 每个标签：
#   name_any —— 店名包含即高置信（主身份）
#   body_re  —— 结构化字段里的【主身份强证据】正则；"有素食/轻食选项"这类弱线索不算，宁空不假
import re
TRAITS = {
    45: {"name_any": ["素食", "纯素", "蔬食", "素斋", "vegan", "vegetarian"],
         "body_re": [r"纯素", r"全素", r"素斋", r"无蛋奶",
                     r"素食(餐厅|饭店|专门|为主)", r"蔬食(餐厅|专门|为主)?",
                     r"以素(食)?为主", r"主打(素食|蔬食)",
                     r"vegan\s*restaurant", r"vegetarian\s*restaurant"]},
    372: {"name_any": ["清真", "halal", "穆斯林"],
          "body_re": [r"清真(认证|餐厅|饭店|菜馆|美食)?", r"halal"]},
    373: {"name_any": ["无麸质", "gluten"],
          "body_re": [r"无麸质", r"不含麸质", r"gluten[-\s]?free"]},
    374: {"name_any": ["轻食", "低卡", "减脂"],
          "body_re": [r"轻食(餐厅|专门)", r"主打轻食", r"健康轻食", r"轻食沙拉",
                      r"健康碗", r"减脂餐", r"低(卡|热量)(餐|为主)?",
                      r"low[-\s]?calorie"]},
}


def as_str(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " ".join(str(v) for k, v in x.items()
                        if k in ("name", "dish", "title", "text", "description"))
    return str(x)


def hits(text, kws):
    t = (text or "").lower()
    return [k for k in kws if k.lower() in t]


def build_plan():
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    have = {}
    for x in rc:
        have.setdefault(x["restaurant_id"], set()).add(x["cuisine_id"])
    rests = C.fetch_all(
        "restaurants",
        "id,name,signature_dishes,selling_points,semantic_description,status",
        order_col="id")
    plan = []
    for r in rests:
        if r.get("status") != "active":
            continue
        cur = have.get(r["id"], set())
        name = r["name"] or ""
        body = " ".join(
            [as_str(x) for x in (r.get("signature_dishes") or [])]
            + ([as_str(x) for x in r["selling_points"]]
               if isinstance(r.get("selling_points"), list)
               else [as_str(r.get("selling_points") or "")])
            + [as_str(r.get("semantic_description") or "")])
        for tag, spec in TRAITS.items():
            if tag in cur:
                continue
            nl = (name or "").lower()
            nh = [k for k in spec["name_any"] if k.lower() in nl]
            bm = [p for p in spec["body_re"] if re.search(p, body, re.I)]
            if nh:
                plan.append({"rid": r["id"], "name": name, "tag": tag,
                             "conf": 0.95, "why": f"店名{nh[:2]}"})
            elif bm:
                plan.append({"rid": r["id"], "name": name, "tag": tag,
                             "conf": 0.85, "why": f"主身份证据{bm[:2]}"})
    return plan


def apply(plan):
    rows = [{"restaurant_id": p["rid"], "cuisine_id": p["tag"], "is_primary": False}
            for p in plan]
    if not rows:
        return
    r = C.req("POST", "/restaurant_cuisines", json=rows)
    if r.status_code not in (200, 201):
        print("[ERROR]", r.status_code, r.text[:300])


def readback(plan):
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    have = {}
    for x in rc:
        have.setdefault(x["restaurant_id"], set()).add(x["cuisine_id"])
    ok = True
    for p in plan:
        if p["tag"] not in have.get(p["rid"], set()):
            print("  [ASSERT FAIL]", p["rid"], p["tag"])
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    plan = build_plan()
    by_tag = {}
    for p in plan:
        by_tag[p["tag"]] = by_tag.get(p["tag"], 0) + 1
    print(f"[{'APPLY' if a.apply else 'DRY-RUN'}] 特质标签待挂={len(plan)} 分布={by_tag}")
    for p in plan:
        print(f"  #{p['rid']} {p['name'][:26]:28s} +tag{p['tag']} conf={p['conf']} {p['why']}")
    if not a.apply:
        print("\n[DRY-RUN] 加 --apply 才写库。")
        return
    apply(plan)
    if plan and readback(plan):
        print("\n[APPLIED] 回读断言 PASS")


if __name__ == "__main__":
    main()
