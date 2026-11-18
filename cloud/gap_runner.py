#!/usr/bin/env python3
"""缺口规划只读能力。自动补齐执行已暂停；不是可启动worker。
保留category聚合、种子与覆盖读取，供subtype_distributor使用。
历史执行实现恢复点a241b7e670460764af68e3e8e3e7d35ee9e32795。
"""
import collections
import json
import pathlib
import sys
import category_resolver as resolver
import discovery_keywords as K
DATA = pathlib.Path('/app/data')
COVDIR = DATA / 'coverage'
PLAN_F = COVDIR / 'discovery_plan.json'
FRONT_F = COVDIR / 'frontier.json'
LEDGER_F = COVDIR / 'ledger.json'

def map_category(lineage, leaf_id=None):
    """数据驱动路由：返回 category slug 或 ''。"""
    slug, _why = resolver.resolve(lineage, leaf_id)
    return slug or ""

def category_worklist():
    """把 plan bundles 解析后按 category 聚合。

    返回 {cat: {leaves:[id...], names:[...], seeds:[并集 xhs 词]}}，
    resolver 无法映射（标签/特殊节点）的细叶被排除。
    """
    bundles = json.loads(PLAN_F.read_text(encoding="utf-8"))
    out = collections.OrderedDict()
    for b in bundles:
        cat = map_category(b["lineage"], b["id"])
        if not cat:
            continue
        e = out.setdefault(cat, {"leaves": [], "names": [], "seeds": []})
        e["leaves"].append(b["id"])
        e["names"].append(b["name"])
        for q in b.get("queries", {}).get("xhs", []):
            if q not in e["seeds"]:
                e["seeds"].append(q)
    return out

def _frontier_names(leaves):
    """地图 frontier 中、关联到本 category 任一细叶且 status=new 的店名。"""
    out = []
    if FRONT_F.exists():
        try:
            fr = json.loads(FRONT_F.read_text(encoding="utf-8"))
        except Exception:
            return out
        for e in fr.values():
            if e.get("status") == "new" and any(
                    lf in e.get("cuisines", []) for lf in leaves):
                if e.get("name") and e["name"] not in out:
                    out.append(e["name"])
    return out

def _ancestor_chain(leaf_id, byid, byname):
    """叶子→根的祖先 id 链（含叶子）；父为虚拟根/不存则止。"""
    chain, seen, cur = [], set(), byid.get(int(leaf_id))
    while cur is not None:
        cid = cur["id"]
        if cid in seen:
            break
        seen.add(cid)
        chain.append(cid)
        p = resolver._parent(cur, byid, byname)
        cur = byid.get(p["id"]) if p else None
    return chain

def category_supply(cat, worklist=None):
    """category 粒度供给。返回 dict 或 None。

      root     = 本 category 细叶在 cuisines 父链上的【最近公共祖先 LCA】（不依赖
                 CUISINE_ROOT 的显示名，避免「越南菜 vs 越餐」这类名字漂移）；
      n_active = root 聚合在营店数（账本父节点 = 根直挂 + 各叶后代去重；根本身是叶
                 则取该叶 n_active）；
      target   = 本 category 计划细叶 target_n 之和。
    """
    if not LEDGER_F.exists():
        return None
    resolver.load_cuisines()
    byid = resolver._CACHE["by_id"]
    byname = resolver._CACHE["by_name"]
    wl = worklist or category_worklist()
    e = wl.get(cat)
    rows = json.loads(LEDGER_F.read_text(encoding="utf-8"))
    by = {r["id"]: r for r in rows}
    leaves = e["leaves"] if e else []

    # 1) LCA：各细叶祖先链的交集里，最深的那个
    root_id = None
    valid = [lf for lf in leaves if int(lf) in byid]
    if valid:
        chains = [_ancestor_chain(lf, byid, byname) for lf in valid]
        common = set(chains[0])
        for ch in chains[1:]:
            common &= set(ch)
        for cid in chains[0]:          # 链为 叶→根，首个命中即最深公共祖先
            if cid in common:
                root_id = cid
                break

    # 2) 兜底：按 CUISINE_ROOT 显示名精确找根
    if root_id is None:
        root_name = K.CUISINE_ROOT.get(cat)
        cands = [r for r in rows if r.get("name") == root_name]
        root = next((r for r in cands if not r.get("leaf")),
                    cands[0] if cands else None)
        if not root:
            return None
        root_id = root["id"]

    root = by.get(root_id)
    if root is None:
        return None

    # target：本 category 计划细叶 target_n 之和；计划无叶则取根下全部叶
    plan_leaves = [int(lf) for lf in leaves
                   if int(lf) in by and by[int(lf)].get("leaf")]
    if plan_leaves:
        target = sum(by[lf].get("target_n", 3) for lf in plan_leaves)
    else:
        children = collections.defaultdict(list)
        for cid, row in byid.items():
            p = resolver._parent(row, byid, byname)
            if p is not None:
                children[p["id"]].append(cid)
        desc, stack = [], [root_id]
        while stack:
            c = stack.pop()
            for ch in children.get(c, []):
                desc.append(ch)
                stack.append(ch)
        leaf_desc = [d for d in desc if d in by and by[d].get("leaf")]
        target = (sum(by[d].get("target_n", 3) for d in leaf_desc)
                  if leaf_desc else root.get("target_n", 3))

    n = root.get("n_active", 0)
    return {"root_id": root_id, "root_name": root.get("name"),
            "n_active": n, "target": target, "met": n >= target}


def main():
    print('已暂停：gap_runner 自动缺口补齐；未采集、未认领、未入库。保留只读规划函数。', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
