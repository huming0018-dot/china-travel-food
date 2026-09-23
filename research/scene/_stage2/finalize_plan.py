#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize 写库计划：
- skip：库内已齐的多址聚合（Gregorius/有喜屋/烤匠）+ 连锁非精选（苹果花园）
- conflict 经研判（不同经营主体）转 new
- update 一律删 location（保留库内 WebService 精确坐标，不被 raw/子代理坐标覆盖）
- new 写坐标：new_coords_result(ok/ok_fallback) + 3 家精确修正
产出 final_plan.json（仍不写库，stage3 --commit 才写）。"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
PIPE = pathlib.Path(
    "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/"
    "agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
)
sys.path.insert(0, str(PIPE))
import common as C  # noqa: E402

STAGE1 = HERE.parent / "_stage1"
PLAN = STAGE1 / "plan_scene.json"
COORDS = HERE / "new_coords_result.json"
OUT = STAGE1 / "final_plan.json"

SKIP = {
    "Gregorius 航迹": "库内已有 愚园路1690/安福路1749",
    "有喜屋深夜食堂": "库内已有约24家分店",
    "烤匠麻辣烤鱼": "库内已有 龙之梦1720/五角场1443",
    "苹果花园(南泉路店)": "平价连锁、非口味精选，降存疑",
}
# 精确/建筑群修正坐标（lat, lng, 说明）
COORD_FIX = {
    "麻布屋AZABUYA(永康路店)": (31.210969, 121.458437, "永康路51号POI"),
    "顶特勒粥面馆": (31.221508, 121.46952, "淮海中路494弄22号POI"),
    "drunk baker醉师傅(陕康里店)": (31.235482, 121.449211, "陕康里建筑群(fallback)"),
}


def main():
    plan = json.load(open(PLAN))
    coord_map = {}
    for r in json.load(open(COORDS)):
        if r.get("status") in ("ok", "ok_fallback") and r.get("lat") is not None:
            coord_map[r["name"]] = (r["lat"], r["lng"])

    final, skipped = [], []
    for x in plan:
        name = x["name"]
        if name in SKIP:
            skipped.append((name, SKIP[name]))
            continue
        if x["action"] == "update":
            x["fields"].pop("location", None)  # 不覆盖库内坐标
            final.append(x)
        elif x["action"] in ("new", "conflict"):
            x["action"] = "new"
            x.pop("restaurant_id", None)
            fix = COORD_FIX.get(name)
            latlng = (fix[0], fix[1]) if fix else coord_map.get(name)
            if latlng:
                lat, lng = latlng
                x["fields"]["location"] = C.point_ewkt(lng, lat)
            final.append(x)

    json.dump(final, open(OUT, "w"), ensure_ascii=False, indent=2)
    n_new = sum(1 for x in final if x["action"] == "new")
    n_upd = sum(1 for x in final if x["action"] == "update")
    new_loc = sum(1 for x in final if x["action"] == "new"
                  and x["fields"].get("location"))
    print(f"最终写库计划: new {n_new} / update {n_upd} = {len(final)} 条")
    print(f"new 带坐标 {new_loc}/{n_new}")
    print("skip", len(skipped), "条:")
    for n, why in skipped:
        print("  -", n, "：", why)
    no_loc = [x["name"] for x in final if x["action"] == "new"
              and not x["fields"].get("location")]
    print("new 无坐标:", no_loc or "无")


if __name__ == "__main__":
    main()
