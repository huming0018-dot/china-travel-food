#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowd_scale.py — 众包任务包扩容工具（PM窗口，2026-10-02 新增）

扩容机制（"怎么扩"的标准答案）：
  数据源 → 过滤 → 去重（对库内已收录 + 已发布任务包）→ 排序 → 切包 → 发布

数据源优先级（按价值排序）：
  1. 官方榜单种子（cloud/dianping_seed.json 等 *seed*.json）—— 权威、覆盖冷启动
  2. 库内 restaurants 表 —— 按筛选条件取未覆盖店铺（评分/商圈/菜系/价格带）
  3. 待补字段池 —— 口味分空 / 营业时间空 / 评论不足的店铺优先补采

用法：
  python3 cloud/crowd_scale.py --source seed --pack-size 6 --kpi 5 --quota 20 [--limit 60]
  python3 cloud/crowd_scale.py --source db   --pack-size 6 --kpi 5 --quota 20 [--district 静安] [--tier 高端]
  python3 cloud/crowd_scale.py --source fill --pack-size 6 --kpi 5 --quota 20 [--field taste_score_empty]

安全：
  - 只发布未覆盖店铺（对 restaurants.name + 已发布 pack 双重去重）
  - 不删除/改动任何已存在数据
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor" / "pipeline"))

import common as C  # noqa: E402
import crowd_pack  # noqa: E402


def load_covered():
    """已覆盖店铺集合 = 已有有效证据(matched_store)的店铺 + 已发布任务包（外部审计 #52 表格项：
    原实现把所有现存餐厅算已覆盖导致候选全被过滤；改为按'已有证明'计算覆盖）"""
    covered = set()
    # 有 accepted 证据的店铺视为已覆盖（证据可能来自众包回流）
    pr = C.req("GET", "/crowd_proofs?select=matched_store,gate_status&limit=10000")
    if pr.status_code == 200:
        for x in pr.json():
            if x.get("gate_status") == "accepted" and x.get("matched_store"):
                covered.add(x["matched_store"])
    # 已发布任务包中的店铺视为在采（open/in_progress/fulfilled/closed 都算）
    rt = C.req("GET", "/crowd_tasks?select=pack,status&limit=200")
    if rt.status_code == 200:
        for t in rt.json():
            p = t.get("pack")
            if isinstance(p, list):
                covered.update(p)
            elif isinstance(p, str):
                covered.update(re.findall(r"[^\"\"{}\[\],]+", p))
    return covered


def from_seed(path, limit=None):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    # 先判输入类型（外部审计 #52 表格项：list 直接 .get 会抛 AttributeError）
    if isinstance(data, list):
        shops = data
    elif isinstance(data, dict):
        shops = data.get("shops") or data.get("stores") or []
    else:
        shops = []
    return shops[:limit] if limit else shops


def from_db(limit=None, district=None, tier=None, min_score=None):
    """库内取未覆盖店铺：可选 商圈/档次/最低分 过滤，按评分降序。
    tier 支持 中/英 别名 → 映射到库内取值（奢华/中档/平价）。"""
    TIER_MAP = {"奢华": "奢华", "luxury": "奢华", "高端": "奢华",
                "中档": "中档", "mid": "中档", "大众": "中档",
                "平价": "平价", "budget": "平价"}
    if tier and tier in TIER_MAP:
        tier = TIER_MAP[tier]
    sel = "name"
    filters = []
    if district:
        filters.append(f"district=eq.{district}")
    if tier:
        filters.append(f"tier=eq.{tier}")
    if min_score is not None:
        filters.append(f"score_total=gte.{min_score}")
    path = "/restaurants?select=name"
    if filters:
        path += "&" + "&".join(filters)
    path += "&order=score_total.desc&limit=1000"
    r = C.req("GET", path)
    if r.status_code != 200:
        sys.exit(f"查询失败: {r.status_code} {r.text[:200]}")
    names = [x["name"] for x in r.json() if x.get("name")]
    return names[:limit] if limit else names


def from_fill(field, limit=None):
    """补字段池：口味分空等字段为空的店铺优先补采。"""
    sel_field = {"taste_score_empty": "name,score_taste"}
    if field not in sel_field:
        sys.exit(f"未知补采字段: {field}，可选 {list(sel_field)}")
    r = C.req("GET", f"/restaurants?select=name&score_taste=is.null&limit=1000")
    if r.status_code != 200:
        sys.exit(f"查询失败: {r.status_code} {r.text[:200]}")
    names = [x["name"] for x in r.json() if x.get("name")]
    return names[:limit] if limit else names


def main():
    ap = argparse.ArgumentParser(description="众包任务包扩容")
    ap.add_argument("--source", required=True, choices=["seed", "db", "fill"])
    ap.add_argument("--seed-file", default="cloud/dianping_seed.json")
    ap.add_argument("--pack-size", type=int, default=6)
    ap.add_argument("--kpi", type=int, default=5)
    ap.add_argument("--quota", type=int, default=20)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--district", default=None)
    ap.add_argument("--tier", default=None)
    ap.add_argument("--min-score", type=float, default=None)
    ap.add_argument("--field", default=None)
    a = ap.parse_args()

    print("=== 众包扩容 ===")
    covered = load_covered()
    print(f"已覆盖（库内+已发布包）: {len(covered)} 家")

    if a.source == "seed":
        candidates = from_seed(a.seed_file, a.limit)
        src_desc = f"种子名单 {a.seed_file}"
    elif a.source == "db":
        candidates = from_db(a.limit, a.district, a.tier, a.min_score)
        src_desc = f"库内筛选(district={a.district} tier={a.tier} score>={a.min_score})"
    else:
        candidates = from_fill(a.field, a.limit)
        src_desc = f"补采池(field={a.field})"

    # 去重：只发布未覆盖的
    fresh = [s for s in candidates if s not in covered]
    print(f"{src_desc}: 候选 {len(candidates)}，其中未覆盖 {len(fresh)}")
    if not fresh:
        print("全部已覆盖，无需扩容。")
        return

    # 发布
    created = crowd_pack.publish(fresh, a.pack_size, "both", a.kpi, a.quota, pack_type="store")
    print(f"\n✅ 扩容完成：新发布 {len(created)} 个任务包（{len(fresh)} 家店铺）")


if __name__ == "__main__":
    main()
