#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adjudicate_residual.py — 外部（主 agent）对 identity_conflicts 残留的 71 个多根店做封闭选项集裁决。

原则（通用，非特征枚举）：
  - 一家 active 店只有一个主菜系根；菜单里"出现/含有"某菜系菜（serves/contains）不构成主身份（is）。
  - 日式强信号（豚骨/刺身/牛肠锅/明太子/拉面/洋食/汉堡排/蛋包饭）→ 日料；
  - 金陵烤鸭/盐水鸭/鸭血粉丝 = 苏菜（金陵），≠ 北京烤鸭/京菜；
  - 名店按品牌出身/官方定位（JG/POLUX/SHADOWS/Ortensia=法；The Nest=北欧；
    Sir Elly's 现行北意=意；利苑/金轩/头灶=粤；丰泽楼=鲁；小大董=京）；
  - 新中餐/中式法餐等无单一传统根的创意菜 → 融合菜(44)。
  - closed 店（EHB）不动。
用法：
  python3 adjudicate_residual.py            # 内存安全模拟 + 写 /app/data/residual_verdict_plan.json
  python3 adjudicate_residual.py --apply    # 执行 + 重新拉取 RC 回验
"""
import os, re, sys, json, time, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

VIRT = {"中餐", "亚洲", "欧洲", "北美洲", "南美洲", "非洲", "融合菜", "非正餐", "认证", "时段"}

# rid -> 主菜系根 id（70 家；closed EHB=1262 不在内）
VERDICT = {
    19: 85, 25: 85, 35: 85,
    493: 3,
    508: 4,
    513: 6,
    719: 3,
    731: 4, 733: 4, 738: 4, 739: 4, 741: 4, 742: 4, 745: 4, 746: 4, 787: 4,
    818: 10,
    836: 5, 837: 5, 860: 5,
    944: 8,
    1037: 17, 1038: 17,
    1077: 35, 1085: 35, 1087: 35, 1089: 35, 1093: 35,
    1135: 38,
    1137: 26, 1152: 26, 1154: 26,
    1189: 27,
    1238: 301,
    1242: 34,
    1268: 27,
    1293: 283,
    1298: 27,
    1301: 35, 1307: 35,
    1326: 85, 1327: 85,
    1330: 21,
    1390: 3,
    1392: 44,
    1461: 1,
    1493: 4,
    1506: 5, 1507: 5,
    1532: 3, 1533: 3,
    1647: 25,
    1658: 17,
    1729: 31,
    1739: 302,
    1744: 5,
    1781: 302,
    1806: 31,
    1810: 26, 1811: 26,
    1840: 5,
    1864: 292,
    1873: 31,
    1879: 9,
    1882: 44,
    1899: 26,
    1902: 26,
    1905: 44,
    1906: 27,
    1973: 27,
}

cs = {c["id"]: c for c in C.fetch_all("cuisines", order_col="id")}
name_by = {i: c["name"] for i, c in cs.items()}


def trad_root(cid):
    def _coerce(p):
        if isinstance(p, str) and p.strip().isdigit():
            return int(p.strip())
        return p
    seen = set(); cur = _coerce(cid)
    while cur in cs and cur not in seen:
        seen.add(cur); node = cs[cur]; par = _coerce(node.get("parent_category"))
        if par in VIRT or par is None:
            return cur if node.get("dimension") == "菜系" else None
        cur = par if isinstance(par, int) else None
        if cur is None:
            return None
    return None


ROOT_OF = {cid: trad_root(cid) for cid in cs}


def cuisine_leaves(rc_rows):
    """rid -> set(菜系维度叶子 cid)；只计能归到根的菜系叶子。"""
    by = collections.defaultdict(set)
    for x in rc_rows:
        cid = x["cuisine_id"]
        if cs.get(cid, {}).get("dimension") == "菜系" and ROOT_OF.get(cid) is not None:
            by[x["restaurant_id"]].add(cid)
    return by


def build_ops(leaves_by):
    ops = []
    for rid, winner in VERDICT.items():
        leaves = leaves_by.get(rid, set())
        roots = {ROOT_OF[c] for c in leaves}
        # detach 非 winner 根下的全部菜系叶子（食材/形式/认证/时段不动）
        for cid in sorted(leaves):
            if ROOT_OF[cid] != winner:
                ops.append({"rid": rid, "op": "detach", "cid": cid,
                            "why": f"主身份={name_by.get(winner)}；移除 {name_by.get(ROOT_OF[cid])}"})
        # 若 winner 根缺失（如 The Pine 挂错成法/美），补挂 winner 根节点
        if winner not in roots:
            ops.append({"rid": rid, "op": "attach", "cid": winner,
                        "why": f"补挂主身份 {name_by.get(winner)}"})
    return ops


def safety_sim(ops, leaves_by):
    state = {rid: set(leaves) for rid, leaves in leaves_by.items()}
    problems = []
    seen_ops = set()
    for o in ops:
        key = (o["rid"], o["op"], o["cid"])
        if key in seen_ops:
            problems.append(("duplicate op", o))
        seen_ops.add(key)
        rid, cid = o["rid"], o["cid"]
        if o["op"] == "attach":
            if cid not in cs or cs[cid].get("dimension") != "菜系":
                problems.append(("attach cid not cuisine", o))
            if ROOT_OF.get(cid) != VERDICT.get(rid):
                problems.append(("attach root != verdict", o))
            state.setdefault(rid, set()).add(cid)
        else:
            if cid not in state.get(rid, set()):
                problems.append(("detach pair missing", o))
            state.setdefault(rid, set()).discard(cid)
    # 每个裁决店最终恰好一个菜系根 == winner
    for rid, winner in VERDICT.items():
        roots = {ROOT_OF[c] for c in state.get(rid, set())}
        if roots != {winner}:
            problems.append(("final roots mismatch", rid, sorted(roots), winner))
    return problems, state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    RC = C.fetch_all("restaurant_cuisines", order_col="restaurant_id")
    leaves_by = cuisine_leaves(RC)

    ops = build_ops(leaves_by)
    problems, _ = safety_sim(ops, leaves_by)
    n_attach = sum(1 for o in ops if o["op"] == "attach")
    n_detach = sum(1 for o in ops if o["op"] == "detach")
    print(f"verdicts={len(VERDICT)}  ops={len(ops)} (attach {n_attach}, detach {n_detach})")
    if problems:
        print("SAFETY SIM FAILED:")
        for p in problems:
            print(" ", p)
        sys.exit(1)
    print("SAFETY SIM PASS")

    plan_path = "/app/data/residual_verdict_plan.json"
    json.dump({"ops": ops}, open(plan_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("plan written:", plan_path)
    for o in ops:
        print(" ", o["rid"], o["op"], o["cid"], "|", o["why"])

    if not a.apply:
        return

    done = 0
    for o in ops:
        rid, cid = o["rid"], o["cid"]
        if o["op"] == "attach":
            resp = C.req("POST", "/restaurant_cuisines",
                         json={"restaurant_id": rid, "cuisine_id": cid, "is_primary": False})
        else:
            resp = C.req("DELETE",
                         f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
        if resp.status_code in (200, 201, 204, 409):
            done += 1
        else:
            print("FAIL", o, resp.status_code, resp.text[:120])
        time.sleep(0.07)
    print(f"applied {done}/{len(ops)}")

    # 回验：重新拉取 RC，重算每个裁决店根
    RC2 = C.fetch_all("restaurant_cuisines", order_col="restaurant_id")
    lb2 = cuisine_leaves(RC2)
    bad = 0
    for rid, winner in VERDICT.items():
        roots = {ROOT_OF[c] for c in lb2.get(rid, set())}
        if roots != {winner}:
            bad += 1
            print("VERIFY MISMATCH", rid, sorted(roots), "want", winner)
    print(f"verify mismatches = {bad}")

    # 全库多根统计（active）
    R = C.fetch_all("restaurants", order_col="id")
    closed = {r["id"] for r in R if r.get("status") == "closed"}
    multi = []
    for rid, leaves in lb2.items():
        roots = {ROOT_OF[c] for c in leaves}
        if len(roots) > 1 and rid not in closed:
            multi.append((rid, sorted(roots)))
    print("remaining active multi-root =", len(multi))
    for m in multi[:20]:
        print("  ", m)


if __name__ == "__main__":
    main()
