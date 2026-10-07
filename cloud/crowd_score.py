#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crowd_score.py — 口味评分体系 v1 · S3 统筹打分骨架（设计稿 §3-§5）

定位：M4 统筹打分。纯函数式全量重算——同输入同输出，可复算（设计稿 §0 A3）。
每次运行 delete+insert 同 model_version 的行，旧版本留档可审计。

数学（设计稿 §3-§4 默认参数，全部显式）：
  - 评分对象 = (店铺, 菜系上下文 cell)；Beta 共轭后验，先验 Beta(1,1)
  - owner 到店评分 m=25，r∈[1,5] 转 Bernoulli p=(r-1)/4：α+=m·p, β+=m·(1-p)
  - 众包 rating（校准后）m=1.0 —— 校准映射 M 暂用恒等占位（TODO: isotonic，§5.1）
  - 众包 note 情感 m=0.3 —— crowd_proofs 无情感字段，本期跳过（TODO: 情感抽取）
  - 上限 cap=20：第 20 条之后同质证据 ×0.5^k 边际递减（§3.2）
  - 同源聚类折扣 ρ=0.5：同参与者第 n 条（0 起）×ρ^n（§3.2）
  - 排名：菜系 cell 内 Bradley-Terry；owner 成对比较 η=1.0，
    owner 分值折算弱比较 η=0.5（§4.2）；λ 收缩混合秩（§4.2 校正项）
  - CI：Beta 后验 95% 分位数（连分数 betacf + 二分求逆，纯 stdlib）
  - 锚不足：owner 证据占比 < 1/3 → owner_anchor_sufficient=false（§3.1）

输入（S2 产物口径，本期直接读 raw 表的已收录行，S2 整理层就绪后切换）：
  - crowd_proofs        gate_status='accepted' 的 kind=rating / kind=note
  - crowd_owner_ratings owner 评分与成对比较（M0，v350 迁移建表）
  - crowd_tasks         任务包（菜系 cell 粗分提示）

输出：crowd_taste_scores（v350 迁移建表），每 (model_version, store, cuisine_ctx) 一行。

用法：
  python3 crowd_score.py --dry-run            # 内置假数据全流程走一遍，只打印不写库
  python3 crowd_score.py --from-json in.json  # 从 JSON 回放（{"proofs":[],"owner_ratings":[],"tasks":[]}）
  python3 crowd_score.py                      # 连库取数 + 计算 + 打印（不写库）
  python3 crowd_score.py --write              # 连库取数 + 计算 + 落 crowd_taste_scores

连库凭据（PostgREST，service_role 级；绝不进插件/页面）：
  SUPABASE_URL                默认 https://bdwrhshgdeghgyzwpxnl.supabase.co
  SUPABASE_SERVICE_ROLE_KEY   必填（--dry-run/--from-json 除外）

部署：本文件放服务器 /home/ubuntu/china-travel-food/cloud/ 下由 owner 手动/定时运行。
"""
import argparse
import hashlib
import json
import math
import os
import sys
import urllib.request

# ================================================================ 参数（设计稿 §3-§4）
PARAM_VERSION = "taste_v1.0"      # 参数集版本：改任何默认参数必须 bump
OWNER_RATING_M = 25.0             # §3.1 owner 到店评分伪计数
CROWD_RATING_M = 1.0              # §3.1 众包 rating（校准后）伪计数
NOTE_SENTIMENT_M = 0.3            # §3.1 note 情感信号伪计数（×signal_strength，本期未接）
CAP = 20                          # §3.2 单 (s,c) 有效证据上限
CAP_DECAY = 0.5                   # §3.2 超 cap 后 ×0.5^k 边际递减
RHO = 0.5                         # §3.2 同源聚类折扣（第 n 条 ×ρ^n，n 从 0 起）
ETA_OWNER_CMP = 1.0               # §4.2 owner 成对比较 BT 全权重
ETA_OWNER_SCORE = 0.5             # §4.2 owner 分值折算弱比较权重
BT_PASSES = 50                    # BT 定点迭代轮数（固定 → 确定性）
ANCHOR_MIN_SHARE = 1.0 / 3.0      # §3.1 owner 证据占比 <1/3 → 锚不足
PRIOR_A, PRIOR_B = 1.0, 1.0       # Beta 先验（经验贝叶斯先验演化 TODO，§5.2）

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bdwrhshgdeghgyzwpxnl.supabase.co")

# ================================================================ Beta 分布（纯 stdlib）
def _betacf(a, b, x):
    """连分数求不完全 beta（Numerical Recipes 6.4），确定性固定 200 轮。"""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def beta_cdf(x, a, b):
    """正则化不完全 beta I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def beta_ppf(q, a, b):
    """Beta 分位数：cdf 单调 → 二分 80 轮，确定性。"""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ================================================================ 菜系 cell 粗分
# TODO(P2)：菜系 taxonomy 由 owner 拍板（设计稿 §11 开放问题 1），本期关键词粗分占位。
CUISINE_RULES = [
    (("火锅",), "火锅"),
    (("烤串", "烧烤", "烤肉"), "烧烤"),
    (("面", "拉面", "拌面"), "面食"),
    (("粉", "米线", "螺蛳粉"), "粉类"),
    (("本帮", "上海菜"), "本帮菜"),
    (("粤", "茶餐厅", "早茶", "烧腊"), "粤菜"),
    (("川", "麻辣", "串串"), "川菜"),
    (("湘",), "湘菜"),
    (("日料", "寿司", "刺身", "居酒屋"), "日料"),
    (("法餐", "意面", "牛排", "西餐", "brunch", "Brunch"), "西餐"),
    (("咖啡", " café"), "咖啡"),
    (("甜品", "蛋糕", "糖水"), "甜品"),
    (("小吃", "生煎", "小笼", "煎饼"), "小吃"),
]


def cuisine_of(store, pack_hint=None):
    """门店 → 菜系 cell：先匹配店名，再匹配任务包关键词提示，都不中 → unknown。"""
    for text in (store, pack_hint or ""):
        for keys, cuisine in CUISINE_RULES:
            if any(k in text for k in keys):
                return cuisine
    return "unknown"


# ================================================================ 数据接入
def _sb_key():
    for k in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY"):
        v = os.environ.get(k)
        if v:
            return v
    raise SystemExit("缺少 SUPABASE_SERVICE_ROLE_KEY（--dry-run/--from-json 不需要）")


def _sb_get(table, params):
    """PostgREST 分页全量拉取（1000/页，确定性 order by）。"""
    key = _sb_key()
    rows, off = [], 0
    while True:
        sep = "&" if params else ""
        url = "%s/rest/v1/%s?%s%slimit=1000&offset=%d" % (
            SUPABASE_URL, table, params, sep, off)
        req = urllib.request.Request(url, headers={
            "apikey": key, "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.loads(r.read().decode())
        rows.extend(page)
        if len(page) < 1000:
            return rows
        off += 1000


def fetch_inputs():
    proofs = _sb_get(
        "crowd_proofs",
        "select=id,kind,participant_id,task_id,note_id,rating,rating_reason,"
        "matched_store,raw_query,created_at&gate_status=eq.accepted&order=id")
    owner = _sb_get("crowd_owner_ratings", "select=id,store,score,reason,compare_to,created_at&order=id")
    tasks = _sb_get("crowd_tasks", "select=task_id,pack_type,pack&order=task_id")
    return {"proofs": proofs, "owner_ratings": owner, "tasks": tasks}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {"proofs": d.get("proofs", []),
            "owner_ratings": d.get("owner_ratings", []),
            "tasks": d.get("tasks", [])}


# ================================================================ 证据池化（§3.1/§3.2）
def _to_score_p(r):
    """1-5 分 → Bernoulli 胜率 p=(r-1)/4（设计稿 §3.1）。"""
    return (float(r) - 1.0) / 4.0


def collect_evidence(inputs):
    """raw 行 → 每 (store, cuisine) 的证据条目列表 + BT 比较列表。

    证据条目: {m, p, source(owner|crowd), cluster, ts, tie}
    比较条目: {cell, a, b, eta, p_exp}（a 期望胜 b 的概率 p_exp）
    返回 (cells, comparisons, stats)
    """
    task_hint = {}  # task_id → 菜系提示（keyword 型任务包关键词）
    for t in inputs["tasks"]:
        pack = t.get("pack") or []
        if t.get("pack_type") == "keyword" and pack:
            task_hint[t.get("task_id")] = str(pack[0])

    cells = {}        # (store, cuisine) → [evidence]
    comparisons = []
    stats = {"owner_ratings": 0, "crowd_ratings": 0, "crowd_ratings_deduped": 0,
             "notes_seen": 0, "notes_used": 0, "comparisons": 0,
             "comparisons_cross_cell_skipped": 0}

    def add(store, cuisine, ev):
        cells.setdefault((store, cuisine), []).append(ev)

    # ---- owner 评分（主输入 m=25；owner 是锚，不做同源折扣）
    for i, r in enumerate(inputs["owner_ratings"]):
        store = (r.get("store") or "").strip()
        if not store or r.get("score") is None:
            continue
        stats["owner_ratings"] += 1
        cuisine = cuisine_of(store)
        p = _to_score_p(r["score"])
        add(store, cuisine, {"m": OWNER_RATING_M, "p": p, "source": "owner",
                             "cluster": "owner", "ts": str(r.get("created_at") or ""), "tie": i})
        # 成对比较：store ≻ compare_to（BT 全权重，§4.2）
        cmp_to = (r.get("compare_to") or "").strip()
        if cmp_to:
            cmp_cuisine = cuisine_of(cmp_to)
            if cmp_cuisine == cuisine:
                comparisons.append({"cell": cuisine, "a": store, "b": cmp_to,
                                    "eta": ETA_OWNER_CMP, "p_exp": 1.0})
                stats["comparisons"] += 1
            else:
                stats["comparisons_cross_cell_skipped"] += 1  # §4.2：跨菜系不比较

    # ---- 众包 rating（弱输入 m=1.0；校准恒等占位 TODO §5.1；同参与者同店只计一次 §防刷）
    seen_pr = set()
    for i, pr in enumerate(inputs["proofs"]):
        if pr.get("kind") == "note":
            stats["notes_seen"] += 1
            # TODO(P2)：note 情感信号 m=0.3×signal_strength——crowd_proofs 无情感字段，
            # 需 LLM/规则抽取（设计稿 §11 开放问题 3，未授权前不抽取），本期只计数。
            continue
        if pr.get("kind") != "rating" or pr.get("rating") is None:
            continue
        store = (pr.get("matched_store") or pr.get("raw_query") or "").strip()
        if not store:
            continue
        stats["crowd_ratings"] += 1
        dedup = (pr.get("participant_id"), store)
        if dedup in seen_pr:
            stats["crowd_ratings_deduped"] += 1
            continue
        seen_pr.add(dedup)
        cuisine = cuisine_of(store, task_hint.get(pr.get("task_id")))
        add(store, cuisine, {"m": CROWD_RATING_M, "p": _to_score_p(pr["rating"]),
                             "source": "crowd", "cluster": str(pr.get("participant_id") or ""),
                             "ts": str(pr.get("created_at") or ""), "tie": i})
    return cells, comparisons, stats


def pool_cell(evs):
    """单 (s,c) 证据 → (alpha, beta, n_eff, owner_share)。折扣顺序（固定，文档化）：
    ① 同源聚类折扣：cluster 内按 (ts, tie) 排序，第 n 条（0 起）×ρ^n（owner 簇豁免）
    ② cap=20：按 (有效权重 desc, ts, tie) 排序，第 i≥20 条再 ×0.5^(i-19)
    ③ α += Σ m_eff·p；β += Σ m_eff·(1-p)
    """
    by_cluster = {}
    for e in evs:
        by_cluster.setdefault(e["cluster"], []).append(e)
    weighted = []
    for cluster, items in by_cluster.items():
        items.sort(key=lambda e: (e["ts"], e["tie"]))
        for n, e in enumerate(items):
            w = e["m"] if cluster == "owner" else e["m"] * (RHO ** n)
            weighted.append({"w": w, "p": e["p"], "source": e["source"],
                             "ts": e["ts"], "tie": e["tie"]})
    weighted.sort(key=lambda e: (-e["w"], e["ts"], e["tie"]))
    alpha, beta, n_eff, m_owner, m_all = PRIOR_A, PRIOR_B, 0.0, 0.0, 0.0
    for i, e in enumerate(weighted):
        w = e["w"] * (CAP_DECAY ** (i - CAP + 1) if i >= CAP else 1.0)
        alpha += w * e["p"]
        beta += w * (1.0 - e["p"])
        n_eff += w
        m_all += w
        if e["source"] == "owner":
            m_owner += w
    owner_share = (m_owner / m_all) if m_all > 0 else 0.0
    return alpha, beta, n_eff, owner_share


# ================================================================ BT 排名（§4.2）
def bt_rank(cell_stores, comparisons, score_evidence):
    """菜系 cell 内 BT：定点迭代 log γ 更新，固定 BT_PASSES 轮（确定性）。

    comparisons: [{a, b, eta, p_exp}]（a 期望胜 b 概率 p_exp）
    score_evidence: {store: p} owner 分值折算弱比较——与 cell 内其他 owner 锚店逐一
                    虚拟比较，目标胜率 p=(r-1)/4，η=0.5（§4.2 第三款）
    返回 {store: gamma}
    """
    gamma = {s: 1.0 for s in cell_stores}
    anchored = sorted(score_evidence.keys())
    for _ in range(BT_PASSES):
        for c in comparisons:
            ga, gb = gamma.get(c["a"], 1.0), gamma.get(c["b"], 1.0)
            p = ga / (ga + gb)
            gamma[c["a"]] = math.exp(max(-20.0, min(20.0, math.log(ga) + c["eta"] * (c["p_exp"] - p))))
            gamma[c["b"]] = math.exp(max(-20.0, min(20.0, math.log(gb) + c["eta"] * ((1.0 - c["p_exp"]) - (1.0 - p)))))
        for a in anchored:
            pa = score_evidence[a]
            for o in anchored:
                if o == a:
                    continue
                ga, go = gamma.get(a, 1.0), gamma.get(o, 1.0)
                p = ga / (ga + go)
                gamma[a] = math.exp(max(-20.0, min(20.0, math.log(ga) + ETA_OWNER_SCORE * (pa - p))))
                gamma[o] = math.exp(max(-20.0, min(20.0, math.log(go) + ETA_OWNER_SCORE * ((1.0 - pa) - (1.0 - p)))))
        # 几何均值归一（数值稳定；不改变序）
        lg = [math.log(g) for g in gamma.values()]
        gm = math.exp(sum(lg) / len(lg))
        gamma = {s: g / gm for s, g in gamma.items()}
    return gamma


def rank_of(gamma):
    """gamma → 名次（1=最高；并列按店名定序，确定性）。"""
    order = sorted(gamma, key=lambda s: (-gamma[s], s))
    return {s: i + 1 for i, s in enumerate(order)}


# ================================================================ 主计算
def compute(inputs):
    cells, comparisons, stats = collect_evidence(inputs)

    # 每 cell 池化 Beta 后验
    rows = []
    by_cuisine = {}
    for (store, cuisine), evs in cells.items():
        alpha, beta, n_eff, owner_share = pool_cell(evs)
        p_mean = alpha / (alpha + beta)
        rows.append({
            "store": store, "cuisine_ctx": cuisine,
            "alpha": alpha, "beta": beta,
            "post_mean": 1.0 + 4.0 * p_mean,                       # 映射回 1-5 分制
            "ci_lo": 1.0 + 4.0 * beta_ppf(0.025, alpha, beta),
            "ci_hi": 1.0 + 4.0 * beta_ppf(0.975, alpha, beta),
            "evidence_count": n_eff,
            "owner_evidence_share": owner_share,
            "owner_anchor_sufficient": owner_share >= ANCHOR_MIN_SHARE,
        })
        by_cuisine.setdefault(cuisine, []).append(store)

    # owner 分值折算弱比较的目标胜率：同店多次 owner 评分取均值（确定性）
    owner_p = {}
    for r in inputs["owner_ratings"]:
        store = (r.get("store") or "").strip()
        if store and r.get("score") is not None:
            owner_p.setdefault(store, []).append(_to_score_p(r["score"]))
    owner_p = {s: sum(v) / len(v) for s, v in owner_p.items()}

    # 每菜系 cell：BT + λ 收缩混合秩（§4.2 校正项）
    for cuisine, stores in by_cuisine.items():
        cmps = [c for c in comparisons if c["cell"] == cuisine]
        cell_score_ev = {s: owner_p[s] for s in stores if s in owner_p}
        # TODO(P2)：众包文本共现比较（"A 比 B 地道"，η=0.05·conf）待情感/比较抽取授权
        g_all = bt_rank(stores, cmps, cell_score_ev)
        g_owner = bt_rank(stores, cmps, cell_score_ev)  # 骨架期全部 BT 证据均为 owner 证据
        r_all, r_owner = rank_of(g_all), rank_of(g_owner)
        # λ = m_owner/(m_owner+m_crowd)（cell 级，有效证据折后质量）
        m_o = sum(r["evidence_count"] * r["owner_evidence_share"] for r in rows if r["cuisine_ctx"] == cuisine)
        m_t = sum(r["evidence_count"] for r in rows if r["cuisine_ctx"] == cuisine)
        lam = (m_o / m_t) if m_t > 0 else 0.0
        blended = {s: lam * r_owner[s] + (1.0 - lam) * r_all[s] for s in stores}
        order = sorted(stores, key=lambda s: (blended[s], -g_all[s], s))
        for rank_pos, s in enumerate(order, 1):
            for r in rows:
                if r["store"] == s and r["cuisine_ctx"] == cuisine:
                    r["gamma"] = g_all[s]
                    r["rank_in_cuisine"] = rank_pos
                    r["anchor_state"] = "anchored" if r["owner_anchor_sufficient"] else "rank_only"
                    r["_lambda"] = lam

    rows.sort(key=lambda r: (r["cuisine_ctx"], r.get("rank_in_cuisine") or 9999, r["store"]))
    return rows, stats


# ================================================================ 版本与留档（§5.1 第 6 步）
def model_version(inputs, stats):
    """model_version = 参数版本 + 输入清单哈希（同输入同输出，复算可逐位验证）。"""
    manifest = {
        "param_version": PARAM_VERSION,
        "params": {"owner_m": OWNER_RATING_M, "crowd_m": CROWD_RATING_M,
                   "note_m": NOTE_SENTIMENT_M, "cap": CAP, "cap_decay": CAP_DECAY,
                   "rho": RHO, "eta_cmp": ETA_OWNER_CMP, "eta_score": ETA_OWNER_SCORE,
                   "bt_passes": BT_PASSES, "anchor_min_share": ANCHOR_MIN_SHARE,
                   "prior": [PRIOR_A, PRIOR_B]},
        "inputs": {"proofs": len(inputs["proofs"]),
                   "owner_ratings": len(inputs["owner_ratings"]),
                   "tasks": len(inputs["tasks"])},
    }
    canonical = json.dumps({"manifest": manifest, "data": inputs},
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return "%s-%s" % (PARAM_VERSION, digest), manifest


def to_db_rows(rows, mv, manifest, stats):
    out = []
    for r in rows:
        out.append({
            "model_version": mv,
            "store": r["store"],
            "cuisine_ctx": r["cuisine_ctx"],
            "alpha": round(r["alpha"], 6),
            "beta": round(r["beta"], 6),
            "post_mean": round(r["post_mean"], 4),
            "ci_lo": round(r["ci_lo"], 4),
            "ci_hi": round(r["ci_hi"], 4),
            "evidence_count": round(r["evidence_count"], 4),
            "owner_evidence_share": round(r["owner_evidence_share"], 4),
            "owner_anchor_sufficient": r["owner_anchor_sufficient"],
            "gamma": round(r["gamma"], 6) if r.get("gamma") is not None else None,
            "rank_in_cuisine": r.get("rank_in_cuisine"),
            "anchor_state": r.get("anchor_state", "rank_only"),
            "signals_used": {"manifest": manifest, "stats": stats,
                             "cell_lambda": round(r.get("_lambda", 0.0), 4)},
        })
    return out


def write_rows(mv, db_rows):
    """全量重算落库：同 model_version delete+insert（幂等重放）。"""
    key = _sb_key()
    headers = {"apikey": key, "Authorization": "Bearer " + key,
               "Content-Type": "application/json", "Prefer": "return=minimal"}
    del_url = "%s/rest/v1/crowd_taste_scores?model_version=eq.%s" % (SUPABASE_URL, mv)
    req = urllib.request.Request(del_url, method="DELETE", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()
    req = urllib.request.Request(
        "%s/rest/v1/crowd_taste_scores" % SUPABASE_URL,
        data=json.dumps(db_rows).encode("utf-8"), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


# ================================================================ 展示
def print_report(rows, stats, mv):
    print("=" * 88)
    print("口味评分体系 · S3 打分骨架  model_version=%s" % mv)
    print("=" * 88)
    print("输入统计: owner评分 %(owner_ratings)d · 众包rating %(crowd_ratings)d"
          "（去重丢 %(crowd_ratings_deduped)d）· note %(notes_seen)d 条（情感未接，计 0 入池）"
          "· 成对比较 %(comparisons)d（跨菜系跳过 %(comparisons_cross_cell_skipped)d）" % stats)
    cur = None
    for r in rows:
        if r["cuisine_ctx"] != cur:
            cur = r["cuisine_ctx"]
            print("\n【菜系 cell: %s】" % cur)
            print("  %-4s %-24s %-7s %-14s %-7s %-8s %-6s %s" %
                  ("排名", "门店", "后验均分", "95%CI", "n_eff", "owner占比", "γ", "锚状态"))
        print("  %-4s %-24s %-7s %-14s %-7s %-8s %-6s %s" % (
            r.get("rank_in_cuisine") or "-",
            r["store"][:24],
            "%.2f" % r["post_mean"],
            "[%.2f, %.2f]" % (r["ci_lo"], r["ci_hi"]),
            "%.1f" % r["evidence_count"],
            "%.0f%%" % (100 * r["owner_evidence_share"]),
            "%.2f" % (r.get("gamma") or 0.0),
            "✓anchored" if r["owner_anchor_sufficient"] else "rank_only(锚不足)"))
    print("\n说明: CI 半宽 >0.8 分或锚不足的店只出候选排名、不进公开榜单（设计稿 §6.3）")


# ================================================================ 干跑假数据
def synthetic_inputs():
    """覆盖：owner 主锚 / 成对比较 / 众包 rating / 超 cap 递减 / 同人重复 / 锚不足 cell。"""
    tasks = [{"task_id": 1, "pack_type": "store",
              "pack": ["海底捞火锅(大悦城店)", "巴奴毛肚火锅", "巷子老火锅"]},
             {"task_id": 2, "pack_type": "store", "pack": ["老吉士本帮菜", "福1039本帮菜馆"]}]
    owner = [
        {"id": 1, "store": "海底捞火锅(大悦城店)", "score": 5,
         "reason": "毛肚脆嫩服务稳定", "compare_to": "巴奴毛肚火锅", "created_at": "2026-09-20T12:00:00Z"},
        {"id": 2, "store": "巴奴毛肚火锅", "score": 3,
         "reason": "锅底偏咸性价比一般", "compare_to": None, "created_at": "2026-09-21T12:00:00Z"},
        {"id": 3, "store": "老吉士本帮菜", "score": 4, "reason": "红烧肉地道略油",
         "compare_to": None, "created_at": "2026-09-22T12:00:00Z"},
        {"id": 4, "store": "福1039本帮菜馆", "score": 5, "reason": "熏鱼一绝环境好",
         "compare_to": "老吉士本帮菜", "created_at": "2026-09-23T12:00:00Z"},
    ]
    proofs = []
    # 海底捞：25 条众包 rating（演示 cap=20 之外的 ×0.5^k 递减），含 p002 重复一次（去重）
    for i in range(25):
        pid = "p%03d" % (i + 1)
        proofs.append({"id": 100 + i, "kind": "rating", "participant_id": pid, "task_id": 1,
                       "note_id": "n%03d" % i, "rating": 5 if i % 5 else 4,
                       "matched_store": "海底捞火锅(大悦城店)", "created_at": "2026-09-2%dT10:%02d:00Z" % (i % 10, i)})
    proofs.append({"id": 200, "kind": "rating", "participant_id": "p002", "task_id": 1,
                   "note_id": "n900", "rating": 1, "matched_store": "海底捞火锅(大悦城店)",
                   "created_at": "2026-09-29T11:00:00Z"})  # 同人同店重复 → 去重丢弃
    # 巴奴：8 条；巷子老火锅：6 条全 5 分（无 owner → 锚不足）
    for i in range(8):
        proofs.append({"id": 300 + i, "kind": "rating", "participant_id": "p%03d" % (30 + i),
                       "task_id": 1, "note_id": "n3%02d" % i, "rating": [3, 4, 2, 4, 3, 5, 3, 4][i],
                       "matched_store": "巴奴毛肚火锅", "created_at": "2026-09-25T0%d:00:00Z" % i})
    for i in range(6):
        proofs.append({"id": 400 + i, "kind": "rating", "participant_id": "p%03d" % (40 + i),
                       "task_id": 1, "note_id": "n4%02d" % i, "rating": 5,
                       "matched_store": "巷子老火锅", "created_at": "2026-09-26T0%d:00:00Z" % i})
    for i in range(4):
        proofs.append({"id": 500 + i, "kind": "rating", "participant_id": "p%03d" % (50 + i),
                       "task_id": 2, "note_id": "n5%02d" % i, "rating": 4,
                       "matched_store": "老吉士本帮菜", "created_at": "2026-09-27T0%d:00:00Z" % i})
    # note 证据：只计数不入池（情感字段未接）
    for i in range(10):
        proofs.append({"id": 600 + i, "kind": "note", "participant_id": "p%03d" % (60 + i),
                       "task_id": 1, "note_id": "n6%02d" % i, "rating": None,
                       "matched_store": "海底捞火锅(大悦城店)", "created_at": "2026-09-28T0%d:00:00Z" % (i % 10)})
    return {"proofs": proofs, "owner_ratings": owner, "tasks": tasks}


# ================================================================ main
def main():
    ap = argparse.ArgumentParser(description="口味评分体系 S3 统筹打分（全量确定性重算）")
    ap.add_argument("--dry-run", action="store_true", help="内置假数据全流程，只打印不写库")
    ap.add_argument("--from-json", metavar="FILE", help="从 JSON 回放输入（不连库）")
    ap.add_argument("--write", action="store_true", help="计算结果落 crowd_taste_scores（delete+insert）")
    ap.add_argument("--json", action="store_true", help="额外打印 JSON 输出行")
    args = ap.parse_args()

    if args.dry_run:
        inputs = synthetic_inputs()
    elif args.from_json:
        inputs = load_json(args.from_json)
    else:
        inputs = fetch_inputs()

    rows, stats = compute(inputs)
    mv, manifest = model_version(inputs, stats)
    db_rows = to_db_rows(rows, mv, manifest, stats)

    print_report(rows, stats, mv)
    if args.json:
        print("\n" + json.dumps(db_rows, ensure_ascii=False, indent=2))

    if args.dry_run or args.from_json:
        print("\n[dry-run] 未写库。加 --write 并连库才落 crowd_taste_scores。")
    elif args.write:
        write_rows(mv, db_rows)
        print("\n已落库: crowd_taste_scores × %d 行（model_version=%s，同版本 delete+insert）"
              % (len(db_rows), mv))
    else:
        print("\n[compute-only] 未写库（加 --write 落库）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
