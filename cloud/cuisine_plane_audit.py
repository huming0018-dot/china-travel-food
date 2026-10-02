#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cuisine_plane_audit.py — 菜系「维度纯度 / 层级完整性」回归锁（确定性、只读、轻量）。

为什么存在（治反复出现的通识分类 bug）：
  历史上反复出现：① 食材/形式标签漏进菜系浏览（拉面视图混入"菜单里有一道拉面"的店）；
  ② 同一品牌因字符略不同被建成多个叶（纹兵卫多遍）；③ 链接悬挂 / 菜系叶错挂父级；
  ④ 店没有任何菜系主身份叶。前端 collectFlavorIds 只在 dimension='菜系' 内遍历，
  本脚本把这套"分层不可串"的不变量固化为回归检查，每次发布/每日跑，违规即报警。

检查项：
  E1 悬挂：restaurant_cuisines.cuisine_id 指向不存在的标签（硬错）。
  E2 错父：dimension='菜系' 节点的 parent_category 既非虚拟根(ROOTS 名)也非菜系节点（硬错）。
  E3 重复叶：dimension='菜系' 内出现同名归一叶子（硬错，导致品牌分裂）。
  W4 无主身份：在营店没有任何 dimension='菜系' 叶（弱警，需补主身份）。
  I5 子树纯度：每个虚拟根按菜系遍历得到的 id 全部 dimension='菜系'（硬错即串维度）。

用法：
  python3 cuisine_plane_audit.py            # 扫描 + 报告
  python3 cuisine_plane_audit.py --json /app/data/patrol/cuisine_plane_audit.json
退出码：出现 E1/E2/E3/I5 硬错=1；仅 W4=0。
"""
import argparse
import json
import os
import pathlib
import re
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", str(HERE / "vendor" / "pipeline"))
for _p in (HERE, PIPE, HERE / "vendor" / "pipeline"):
    if (pathlib.Path(_p) / "common.py").exists():
        sys.path.insert(0, str(_p))
        break
import common as C  # noqa: E402

ROOTS = ['中餐', '亚洲', '欧洲', '非洲', '北美洲', '南美洲', '融合菜', '非正餐']


def cjk_norm(s):
    """繁简/异体/去标点空格的轻量归一（与 common.cjk_norm 对齐，缺失时本地兜底）。"""
    fn = getattr(C, "cjk_norm", None)
    if fn:
        return fn(s)
    s = (s or "").lower()
    s = re.sub(r"[\s\-—·・'‘’“”\"#(),.，。、:：;；?？!！（）()\[\]]+", "", s)
    return s


def children_of(cuis, key):
    return [c for c in cuis if c.get("dimension") == "菜系"
            and str(c.get("parent_category") or "") == str(key)]


def subtree(cuis, name):
    """镜像前端 collectFlavorIds：虚拟根取一级，真实节点按 id，仅在菜系维度内遍历。"""
    ids, stack = set(), list(children_of(cuis, name))
    seed = [c for c in cuis if c.get("dimension") == "菜系" and c["name"] == name]
    stack += seed
    while stack:
        n = stack.pop()
        if n["id"] in ids:
            continue
        ids.add(n["id"])
        stack += children_of(cuis, n["id"])
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    cuis = C.fetch_all("cuisines", "id,name,parent_category,dimension", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    rests = C.fetch_all("restaurants", "id,name,status", order_col="id")
    byid = {c["id"]: c for c in cuis}

    errors, warns = [], []

    # E1 悬挂链接
    for x in rc:
        if x["cuisine_id"] not in byid:
            errors.append({"code": "E1", "rid": x["restaurant_id"],
                           "cuisine_id": x["cuisine_id"], "msg": "链接指向不存在标签"})

    # E2 菜系节点错父
    for c in cuis:
        if c.get("dimension") != "菜系":
            continue
        p = c.get("parent_category")
        if p is None:
            continue
        if isinstance(p, str) and p in ROOTS:
            continue
        pid = int(p) if (isinstance(p, str) and p.isdigit()) else p
        pref = byid.get(pid)
        if pref is None or pref.get("dimension") != "菜系":
            errors.append({"code": "E2", "cuisine_id": c["id"], "name": c["name"],
                           "parent": p, "msg": "菜系叶父级非虚拟根/非菜系节点（串维度风险）"})

    # E3 重复菜系叶（归一同名）
    norm_groups = defaultdict(list)
    for c in cuis:
        if c.get("dimension") == "菜系":
            norm_groups[cjk_norm(c["name"])].append(c)
    for key, group in norm_groups.items():
        ids = {c["id"] for c in group}
        if len(ids) > 1:
            errors.append({"code": "E3", "norm": key,
                           "leaves": [{"id": c["id"], "name": c["name"]} for c in group],
                           "msg": "菜系叶归一后重复（品牌分裂）"})

    # I5 虚拟根子树纯度
    purity = {}
    for root in ROOTS:
        ids = subtree(cuis, root)
        bad = [i for i in ids if byid.get(i, {}).get("dimension") != "菜系"]
        purity[root] = {"nodes": len(ids), "non_cuisine_in_subtree": bad}
        for i in bad:
            errors.append({"code": "I5", "root": root, "cuisine_id": i,
                           "msg": "菜系子树混入非菜系节点"})

    # W4 在营店无菜系主身份叶
    cuisine_ids = {c["id"] for c in cuis if c.get("dimension") == "菜系"}
    have_leaf = defaultdict(bool)
    for x in rc:
        if x["cuisine_id"] in cuisine_ids:
            have_leaf[x["restaurant_id"]] = True
    for r in rests:
        if r.get("status") == "active" and not have_leaf[r["id"]]:
            warns.append({"code": "W4", "rid": r["id"], "name": r["name"],
                          "msg": "在营店无菜系主身份叶"})

    hard = [e for e in errors if e["code"] in ("E1", "E2", "E3", "I5")]
    report = {"errors": errors, "warnings": warns, "purity": purity,
              "counts": {"cuisines": len(cuis), "restaurants": len(rests),
                         "hard_errors": len(hard), "no_identity": len(warns)}}
    if a.json:
        p = pathlib.Path(a.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"扫描 cuisines={len(cuis)} restaurants={len(rests)}")
    print(f"硬错 E1/E2/E3/I5 = {len(hard)}；无主身份 W4 = {len(warns)}")
    for code in ("E1", "E2", "E3", "I5"):
        n = [e for e in errors if e["code"] == code]
        if n:
            print(f"  {code}: {len(n)} 例，如 {json.dumps(n[0], ensure_ascii=False)[:160]}")
    print("子树纯度:", {r: purity[r]["nodes"] for r in ROOTS})
    if a.json:
        print("报告:", a.json)
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
