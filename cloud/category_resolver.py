#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""category_resolver.py — 数据驱动的「discovery bundle → category slug」路由器。

为什么存在（2026-09-28 覆盖攻坚）：
  旧 gap_runner.map_category 用 ~29 个关键词子串硬编码，129 个 plan bundle 有 81 个
  映射不到 category（智利 / 烧卖 / 烧饼 / 汤包 / 包子 / 葱油饼 / 各国菜…），这些叶子
  从未进入采集。本模块改为**由 cuisines 分类体系数据驱动解析**：

    1. 用 bundle lineage 的名字（叶子优先，复合名按 · 拆分）在 cuisines 表中定位节点；
    2. 沿 parent_category 父链（同维度）向上，每经过一个节点就看其「桶根名」是否在
       discovery_keywords.ROOT_NAME_TO_SLUG 反查表里——叶子侧最先命中的即 category；
    3. 纯标签 / 特殊标签（工业化餐饮、宠物友好、上海老字号、素食纯素、分子先锋…）不是
       采集桶，返回 (None, reason)，claim_next_leaf 跳过。

  新增国家 / 形态桶：只需在 discovery_keywords 的 GEO_COUNTRY / FORM_BUCKETS /
  JAPAN_FORMS / SERVICE_FORMS 登记，本路由器自动生效，无需改路由代码。

主接口：
  resolve(lineage, leaf_id=None) -> (slug:str|None, reason:str)
"""
import json
import pathlib
import sys
import time

_HERE = pathlib.Path(__file__).resolve().parent
for _p in ("/app/pipeline", str(_HERE / "vendor" / "pipeline"),
           str(_HERE), "/app/cloud"):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import common as C            # noqa: E402
import discovery_keywords as K  # noqa: E402


# 极少数无法靠父链/名字解析时的硬覆盖（leaf_id -> slug），默认空。
LEAF_OVERRIDE = {}

_CACHE = {"t": 0.0, "rows": None, "by_id": {}, "by_name": {}}
_CACHE_TTL = 600


def _norm(s):
    return C.cjk_norm(str(s or ""))


def load_cuisines(force=False):
    now = time.time()
    if force or _CACHE["rows"] is None or now - _CACHE["t"] > _CACHE_TTL:
        rows = C.fetch_all("cuisines", "id,name,dimension,parent_category",
                           order_col="id")
        by_id = {r["id"]: r for r in rows}
        by_name = {}
        for r in rows:
            by_name.setdefault(_norm(r["name"]), []).append(r)
        _CACHE.update(rows=rows, by_id=by_id, by_name=by_name, t=now)
    return _CACHE["rows"]


def _parent(row, by_id, by_name=None):
    """父节点；父为虚拟根名字/不存在则返回 None。

    支持三种 parent_category：
      - int / 数字字符串：按 id 取，要求同维度（菜系链不串到食材）；
      - 非数字字符串：先按名字在 cuisines 表中查（食材叶常以根名字符串挂到
        「包馅面食/饼/甜品/点心」等真实存在的形态根）；命中且同维度即父节点；
        若该名字在表中无行（亚洲/欧洲/中餐等虚拟根），返回 None。
    """
    p = row.get("parent_category")
    dim = row.get("dimension")
    if isinstance(p, int) or (isinstance(p, str) and p.isdigit()):
        pid = int(p)
        par = by_id.get(pid)
        if par and par.get("dimension") == dim:
            return par
        return None
    if isinstance(p, str) and p.strip() and by_name:
        hits = by_name.get(_norm(p), [])
        same = [h for h in hits if h.get("dimension") == dim]
        pool = same or hits
        # 多个同名时优先「自身即为根」的形态根（parent 为 None/虚拟名）
        for h in pool:
            hp = h.get("parent_category")
            if hp is None or (isinstance(hp, str) and not hp.isdigit()):
                return h
        if pool:
            return pool[0]
    return None


def _walk_slug(row, by_id, by_name=None):
    """从该节点沿父链向上，返回叶子侧最先命中的 bucket slug。"""
    cur, guard = row, 0
    while cur is not None:
        slug = K.ROOT_NAME_TO_SLUG.get(cur.get("name"))
        if slug:
            return slug
        cur = _parent(cur, by_id, by_name)
        guard += 1
        if guard > 24:
            break
    return None


def _tokens(lineage):
    """从 lineage 叶子侧产出待匹配名字（复合名按 ·/· 拆分）。"""
    out = []
    for node in reversed(list(lineage)):
        for part in str(node).replace("·", "·").split("·"):
            t = part.strip()
            if t and t not in out:
                out.append(t)
    return out


def _ancestor_names(row, by_id, by_name=None):
    out, cur, guard = [], row, 0
    while True:
        par = _parent(cur, by_id, by_name)
        if par is None:
            break
        out.append(par.get("name"))
        cur = par
        guard += 1
        if guard > 24:
            break
    return out


def resolve(lineage, leaf_id=None):
    lineage = list(lineage or [])
    if leaf_id is not None and int(leaf_id) in LEAF_OVERRIDE:
        return LEAF_OVERRIDE[int(leaf_id)], "leaf override"

    rows = load_cuisines()
    by_id = _CACHE["by_id"]
    by_name = _CACHE["by_name"]

    # 上下文（更早的 lineage 元素）名字集合，用于确认候选在正确子树
    context = [_norm(x) for x in lineage[:-1]]
    multi_ctx = len(lineage) >= 2

    # 收集候选节点（保持叶子优先顺序），按精确名匹配
    cand, seen = [], set()
    for tok in _tokens(lineage):
        for r in _CACHE["by_name"].get(_norm(tok), []):
            if r["id"] not in seen:
                seen.add(r["id"])
                cand.append(r)

    if not cand:
        return None, "lineage 名字在 cuisines 表中无节点：%s" % " / ".join(lineage)

    # 非采集节点判定（标签/特殊标签）
    def is_nonsourcing(r):
        if r.get("dimension") in K.NON_SOURCING_DIMS:
            return True
        if r.get("name") in K.SPECIAL_NON_SOURCING_ROOTS:
            return True
        return False

    # 维度偏好：有父上下文时菜系优先（日料/台湾菜…）；单节点时食材/形式优先（薄饼/会所/饼）
    if multi_ctx:
        dim_rank = {"菜系": 0, "食材": 1, "形式": 2}
    else:
        dim_rank = {"食材": 0, "形式": 1, "菜系": 2}

    def score(r):
        anc = [_norm(x) for x in _ancestor_names(r, by_id, by_name)]
        ctx_hit = 1 if any(c in anc for c in context) else 0
        # 精确等于叶子 token 给 0，否则（contains 命中）给 1
        return (-ctx_hit, dim_rank.get(r.get("dimension"), 3), len(r.get("name", "")))

    nonsourcing = []
    for r in sorted(cand, key=score):
        if is_nonsourcing(r):
            nonsourcing.append(r)
            continue
        slug = _walk_slug(r, by_id, by_name)
        if slug:
            return slug, "via %s" % r.get("name")

    if nonsourcing:
        return None, "标签/特殊节点非采集桶：%s" % nonsourcing[0].get("name")
    return None, "沿父链未找到 bucket 根：%s" % " / ".join(lineage)


def resolve_all_bundles(plan):
    """批量解析，返回 (mapped, unmapped)，用于自检覆盖率。"""
    mapped, unmapped = [], []
    for b in plan:
        slug, why = resolve(b.get("lineage"), b.get("id"))
        (mapped if slug else unmapped).append((b, slug, why))
    return mapped, unmapped


if __name__ == "__main__":
    plan_path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/coverage/discovery_plan.json"
    plan = json.loads(pathlib.Path(plan_path).read_text("utf-8"))
    mapped, unmapped = resolve_all_bundles(plan)
    print("可映射 %d / 不可映射 %d / 共 %d" % (len(mapped), len(unmapped), len(plan)))
    for b, slug, why in mapped:
        print("  %3d %-28s -> %s" % (b["id"], b["lineage"][-1], slug))
    if unmapped:
        print("\n--- 仍不可映射 ---")
        for b, slug, why in unmapped:
            print("  %3d %s  (%s)" % (b["id"], " / ".join(b["lineage"]), why))
