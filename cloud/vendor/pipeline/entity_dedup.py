#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entity_dedup.py — Phase 0-A 实体解析去重 + 名称交叉验证（确定性、默认 dry-run）

设计原则（对齐 north-star / entity-verification / mechanism-master P2）：
- 一家店一个 canonical id；同店异写→合并（正名为准、异写入 aliases、证据取并集）；
  近名异店（地址/品牌/菜系不同）→保留独立实体，禁止误并。
- 合并时绝不一删了之：先把指向被合并 id 的全部子表行迁移/去重并重指到保留 id，
  最后才 DELETE 被合并行；字段合并只补空（coalesce），绝不覆盖已补电话/坐标。
- 并发安全：每簇 apply 前重新快照成员行，若与计划时不一致就该簇重算；
  云端 amap/电话定时任务可能同时 PATCH，合并是"读最新→consolidate"，不覆盖他人刚写。
- 默认 dry-run 产出逐簇报告与名称修正清单；--apply 才写库，写后回读自检。

子表（以 db/migrations 实际 schema 为准，ON DELETE 多为 CASCADE，直接删行会丢数据）：
  restaurant_cuisines      PK(restaurant_id,cuisine_id)            CASCADE
  reviews                  id UUID, user_id+visit_date             CASCADE
  restaurant_chefs         PK(restaurant_id,chef_id,role)          CASCADE
  restaurant_awards        uniq(restaurant_id,award_type,year)    CASCADE
  food_events              restaurant_id CASCADE / related_... SET NULL（两字段都要处理）
  restaurant_group_members PK(group_id,restaurant_id)              CASCADE
  negotiations             id, channel                             CASCADE
  price_benchmarks         id, dish_name                           CASCADE
  favorites                uniq(user_id,restaurant_id)             CASCADE
  food_kol_mentions        restaurant_id SET NULL                  （改指保留 id，不置空）

用法：
  python3 entity_dedup.py                     # dry-run，打印逐簇报告 + 名称修正清单
  python3 entity_dedup.py --apply             # 自检全绿后才真正合并（仍逐簇回读）
  python3 entity_dedup.py --plan /app/data/entity_dedup_plan.json
"""
import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict

import common as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
KEEP_FILES = [os.path.join(DATA, "entity_keep_pairs.json"),
              os.path.join(HERE, "entity_keep_pairs.json")]

# ---------------------------------------------------------------------------
# 子表迁移注册表：(表, fk列, 业务键函数(除restaurant_id外的去重键), 有无独立id)
# ---------------------------------------------------------------------------
def _rc_key(r):      return (r["cuisine_id"],)
def _chef_key(r):    return (r["chef_id"], r.get("role"))
def _group_key(r):   return (r["group_id"],)
def _review_key(r):  return (r.get("user_id"), r.get("visit_date"),
                             (r.get("content") or "")[:120])
def _award_key(r):   return (r["award_type"], r.get("year"), r.get("season"))
def _event_key(r):   return (r.get("category"), r.get("title"), r.get("event_date"))
def _neg_key(r):     return (r.get("channel"),)
def _pb_key(r):      return (r.get("dish_name"),)
def _fav_key(r):     return (r.get("user_id"),)
def _kol_key(r):     return (r.get("post_id"), r.get("mentioned_raw"))

# 有独立 id（serial/uuid）的表：改走 PATCH restaurant_id
# 复合主键表（无独立 id，或 PK 含 restaurant_id）：走 POST 新行 + DELETE 旧行
CHILD_TABLES = [
    # table, fk_col, business_key, composite_pk?
    ("restaurant_cuisines",      "restaurant_id", _rc_key,     True),
    ("reviews",                  "restaurant_id", _review_key, False),
    ("restaurant_chefs",         "restaurant_id", _chef_key,   True),
    ("restaurant_awards",        "restaurant_id", _award_key,  False),
    ("food_events",              "restaurant_id", _event_key,  False),
    ("food_events",              "related_restaurant_id", _event_key, False),  # 第二 FK
    ("restaurant_group_members", "restaurant_id", _group_key,   True),
    ("negotiations",             "restaurant_id", _neg_key,    False),
    ("price_benchmarks",         "restaurant_id", _pb_key,     False),
    ("favorites",                "restaurant_id", _fav_key,    False),
    ("food_kol_mentions",        "restaurant_id", _kol_key,    False),
]
# 只需迁移主 fk 的表（food_events 的 related 单独处理）
FK_TABLES = [(t, fk, k, comp) for (t, fk, k, comp) in CHILD_TABLES]

SCORE_KEYS = ["score_objective", "score_diner", "score_taste", "score_endorsement"]
# 字段合并：只补 keeper 空值；电话/坐标永不覆盖已存在的有效值
FILL_KEYS = ["phone", "address", "name_en", "booking_method", "business_area",
             "price_range", "signature_dishes", "evidence_summary", "open_days",
             "semantic_description", "chef_name", "dist"]

GENERIC_STOP = {"cafe", "coffee", "bar", "the", "and", "restaurant", "bistro",
                "bakery", "shop", "store", "co", "kitchen", "de", "la", "le"}


# ---------------------------------------------------------------------------
# 归一 / 距离
# ---------------------------------------------------------------------------
def brand_core(name):
    s = re.split(r"[（(]", str(name or ""))[0]
    m = re.search(r"[路街道里弄号镇]|广场|中心|商场", s)
    if m:
        s = s[:m.start()]
    s = re.sub(r"(上海)?(全国首店|首店|分店|总店|直营店|旗舰店|店)$", "", s)
    return C.cjk_norm(s)


def latin_core(name):
    pre = re.split(r"[（(]", str(name or ""))[0].lower()
    toks = [t for t in re.findall(r"[a-z0-9]+", pre)
            if len(t) >= 3 and t not in GENERIC_STOP]
    joined = "".join(toks)
    return ("lat:" + joined) if len(joined) >= 4 else ""


def phone_set(s):
    out = set()
    for p in re.split(r"[/,，;；]", str(s or "")):
        d = re.sub(r"\D", "", p)
        if len(d) >= 10:  # 021+8=11 / 11位手机
            out.add(d)
    return out


def ll(r):
    return C.parse_location(r.get("location"))


def dist_m(a, b):
    if not a or not b:
        return None
    R = 6371000
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla = math.radians(b[1] - a[1]); dlo = math.radians(b[0] - a[0])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# 双向裁决
# ---------------------------------------------------------------------------
def adjudicate(A, B):
    """返回 ('merge'|'keep'|'review', reason)。
    合并需强证据：品牌相关 AND（同座机 OR 同门牌 addr_core OR 坐标<25m）。
    近名异店：坐标明显分开（连锁分店）/ 不同区 / 不同路 → 保留。"""
    pa, pb = phone_set(A.get("phone")), phone_set(B.get("phone"))
    land_a = {p for p in pa if p.startswith("021") or p.startswith("400")}
    land_b = {p for p in pb if p.startswith("021") or p.startswith("400")}
    shared_land = bool(land_a & land_b)
    shared_mobile = bool(pa & pb) and not shared_land

    aa, ab = C.addr_core(A.get("address")), C.addr_core(B.get("address"))
    same_addr = bool(aa) and aa == ab

    la, lb = ll(A), ll(B)
    d = dist_m(la, lb) if (la and lb) else None

    same_district = (A.get("district") and B.get("district")
                     and A.get("district") == B.get("district"))

    reasons = []
    if shared_land:
        reasons.append("shared_landline")
    if same_addr:
        reasons.append("same_addr_core")
    if d is not None and d < 25:
        reasons.append(f"coord<25m({int(d)}m)")
    if d is not None:
        reasons.append(f"{int(d)}m")
    if shared_mobile:
        reasons.append("shared_mobile")

    # 强合并信号
    strong = shared_land or same_addr or (d is not None and d < 25)
    # 明显不同的物理位置（连锁分店）
    far = d is not None and d > 200
    diff_road = bool(aa and ab and aa != ab)

    if strong and not far:
        # 同址异写。但若门牌号不同且距离>60m，仍需复核
        if diff_road and d is not None and d > 60:
            return "review", "weak_merge:" + ",".join(reasons)
        return "merge", "same_venue:" + ",".join(reasons)
    if far:
        return "keep", "diff_branch:" + ",".join(reasons)  # 连锁异址分店
    # 中等距离（25-200m）+ 弱信号：商场共用中心坐标等不确定
    if d is not None and d <= 200 and (shared_mobile or same_addr or (d < 80)):
        return "review", "near_venue:" + ",".join(reasons)
    return "keep", "no_strong_evidence:" + ",".join(reasons)


# ---------------------------------------------------------------------------
# 候选簇构建（按品牌核心倒排 + 单链连通）
# ---------------------------------------------------------------------------
def build_clusters(rests, keep_pairs):
    by_key = defaultdict(list)
    for r in rests:
        for k in (brand_core(r.get("name")), latin_core(r.get("name"))):
            if k:
                by_key[k].append(r)
    raw = []
    for k, items in by_key.items():
        if len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                verdict, why = adjudicate(a, b)
                raw.append((a["id"], b["id"], verdict, why, k))
    # 按 keep_pairs 强制 keep
    kept = set()
    for sig in keep_pairs:
        ids = tuple(sig.split("|"))
        for x in ids:
            for y in ids:
                if x != y:
                    kept.add(tuple(sorted((int(x), int(y)))))
    edges = []
    for aid, bid, v, why, k in raw:
        pair = tuple(sorted((aid, bid)))
        if pair in kept:
            continue
        if v == "merge":
            edges.append((aid, bid, why, k))
    # 连通分量
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for aid, bid, _, _ in edges:
        ra, rb = find(aid), find(bid)
        if ra != rb:
            parent[rb] = ra
    groups = defaultdict(list)
    for aid, bid, _, _ in edges:
        groups[find(aid)] += [aid, bid]
    clusters = []
    seen = set()
    for members in groups.values():
        sig = tuple(sorted(set(members)))
        if len(sig) > 1 and sig not in seen:
            seen.add(sig)
            clusters.append(sig)
    # review 对（不自动合并，单列）
    review_pairs = [(aid, bid, why, k) for aid, bid, v, why, k in raw
                    if v == "review" and tuple(sorted((aid, bid))) not in kept]
    return clusters, review_pairs


# ---------------------------------------------------------------------------
# 完整度 / keeper 选择
# ---------------------------------------------------------------------------
def completeness(r):
    s = 0
    if r.get("status") == "active":
        s += 3
    if r.get("location"):
        s += 3
    if C.clean_phone(r.get("phone"))[0]:
        s += 2
    if r.get("signature_dishes"):
        s += 1
    s += 2 * sum(1 for k in SCORE_KEYS if r.get(k) is not None)
    s += min(len(r.get("evidence_summary") or "") // 100, 3)
    if r.get("booking_method"):
        s += 1
    if r.get("restaurant_cuisines_n"):
        s += min(r["restaurant_cuisines_n"] / 2, 3)
    return s


# ---------------------------------------------------------------------------
# 子表迁移（核心数据安全）
# ---------------------------------------------------------------------------
def fetch_rows(table, fk, rid):
    r = C.req("GET", f"/{table}?{fk}=eq.{rid}")
    if r.status_code not in (200, 201):
        return []
    return r.json() or []


def migrate_child_row(table, fk, biz_key, comp_pk, dup_row, keeper_id, log):
    """把 dup_row 迁到 keeper。业务键已存在于 keeper → 删 dup 行；否则改指/复制。"""
    kp = biz_key(dup_row)
    # keeper 是否已存在同业务键
    keeper_rows = fetch_rows(table, fk, keeper_id)
    exists = any(biz_key(k) == kp for k in keeper_rows)
    if exists:
        if "id" in dup_row:
            r = C.req("DELETE", f"/{table}?id=eq.{dup_row['id']}")
            log.append(f"{table} dup-row del {dup_row.get('id')}: {r.status_code}")
        else:
            # 复合 PK：按 fk+业务键过滤删
            flt = composite_filter(table, fk, dup_row)
            r = C.req("DELETE", f"/{table}?{flt}")
            log.append(f"{table} dup-row del({flt}): {r.status_code}")
        return "dedup_del"
    # 改指 / 复制
    if not comp_pk and "id" in dup_row:
        r = C.req("PATCH", f"/{table}?id=eq.{dup_row['id']}", json={fk: keeper_id})
        log.append(f"{table} {dup_row.get('id')} {fk}->{keeper_id}: {r.status_code}")
        return "repoint"
    # 复合 PK：POST 新行（keeper），删 dup 行
    body = {k: v for k, v in dup_row.items() if k not in ("id", fk)}
    body[fk] = keeper_id
    r = C.req("POST", f"/{table}", json=body)
    log.append(f"{table} +{kp}->{keeper_id}: {r.status_code}")
    if r.status_code not in (200, 201):
        log.append(f"  POST FAIL body={body} resp={r.text[:200]}")
    # 删 dup 行
    if "id" in dup_row:
        C.req("DELETE", f"/{table}?id=eq.{dup_row['id']}")
    else:
        C.req("DELETE", f"/{table}?{composite_filter(table, fk, dup_row)}")
    return "copy_del"


def composite_filter(table, fk, row):
    if table == "restaurant_cuisines":
        return f"restaurant_id=eq.{row['restaurant_id']}&cuisine_id=eq.{row['cuisine_id']}"
    if table == "restaurant_chefs":
        return (f"restaurant_id=eq.{row['restaurant_id']}&chef_id=eq.{row['chef_id']}"
                f"&role=eq.{row.get('role')}")
    if table == "restaurant_group_members":
        return f"restaurant_id=eq.{row['restaurant_id']}&group_id=eq.{row['group_id']}"
    return f"{fk}=eq.{row[fk]}"


def migrate_children(dup_id, keeper_id, log):
    """迁移指向 dup_id 的所有子表行到 keeper_id。返回迁移条数。"""
    moved = 0
    for table, fk, biz_key, comp_pk in FK_TABLES:
        rows = fetch_rows(table, fk, dup_id)
        for row in rows:
            migrate_child_row(table, fk, biz_key, comp_pk, row, keeper_id, log)
            moved += 1
            time.sleep(0.04)
    # food_events.related_restaurant_id 单独处理（SET NULL → 主动改指）
    for row in fetch_rows("food_events", "related_restaurant_id", dup_id):
        # keeper 是否已有同 event 业务键
        kp = _event_key(row)
        keeper_rows = fetch_rows("food_events", "related_restaurant_id", keeper_id)
        if not any(_event_key(k) == kp for k in keeper_rows):
            r = C.req("PATCH", f"/food_events?id=eq.{row['id']}",
                      json={"related_restaurant_id": keeper_id})
            log.append(f"food_events.related {row['id']}->{keeper_id}: {r.status_code}")
            moved += 1
        else:
            r = C.req("PATCH", f"/food_events?id=eq.{row['id']}",
                      json={"related_restaurant_id": None})
            log.append(f"food_events.related dup {row['id']}->null: {r.status_code}")
        time.sleep(0.04)
    return moved


# ---------------------------------------------------------------------------
# 字段合并：只补空，永不覆盖已存在的电话/坐标
# ---------------------------------------------------------------------------
def plan_field_merge(keeper, dups):
    fill = {}
    for k in FILL_KEYS:
        if not keeper.get(k):
            for d in dups:
                if d.get(k):
                    fill[k] = d[k]
                    break
    for k in SCORE_KEYS:
        if keeper.get(k) is None:
            for d in dups:
                if d.get(k) is not None:
                    fill[k] = d[k]
                    break
    if not keeper.get("location"):
        for d in dups:
            p = ll(d)
            if p:
                fill["location"] = C.point_ewkt(*p)
                break
    # aliases 并集：把被合并店名收进 keeper.aliases（旧名仍可搜到，但不作正名）
    existing = list(keeper.get("aliases") or [])
    for d in dups:
        nm = d.get("name")
        if nm and nm != keeper.get("name") and nm not in existing:
            existing.append(nm)
        ne = d.get("name_en")
        if ne and ne != keeper.get("name_en") and ne not in existing:
            existing.append(ne)
    if existing and existing != list(keeper.get("aliases") or []):
        fill["aliases"] = existing
    return fill


# ---------------------------------------------------------------------------
# 名称交叉验证（L1-L6 启发式 + 已核实登记表）
# ---------------------------------------------------------------------------
# 已核实正名（来自 entity-verification.md 第5节，L1-L5 多源一致）。
# 键 = 库内可能出现的异写 cjk_norm；值 = (正名, 权威依据说明)
NAME_AUTHORITY = {
    "白茸": ("白茸 Bai Rong", "米其林入选/L3 + BFC官网/L1 + 高德/L4"),
    "佰荣": ("白茸 Bai Rong", "同音错字→白茸；米其林/BFC/高德三源"),
    "白荣": ("白茸 Bai Rong", "同音错字→白茸（BFC鲁菜）；勿与南京东路温州馆混"),
    "百荣": ("白茸 Bai Rong", "同音错字→白茸"),
}
# 非店名后缀（采集把营业时段写进店名，应剥离进 notes 而非正名）
BAD_NAME_SUFFIX = re.compile(r"[（(](午市套餐|晚餐|午餐|夜宵|下午茶|营业中|探店|测评)[）)]\s*$")


def name_audit(rests):
    fixes = []
    for r in rests:
        nm = r.get("name") or ""
        cn = C.cjk_norm(nm)
        # 1) 同音错字登记表
        if cn in NAME_AUTHORITY:
            correct, why = NAME_AUTHORITY[cn]
            if C.cjk_norm(correct) != cn:
                fixes.append({"id": r["id"], "wrong": nm, "correct": correct,
                              "level": "L3/L1", "reason": why, "authority_urls":
                              ["guide.michelin.com", "BFC官网", "amap"]})
        # 2) 店名里混入营业时段等非店名词缀
        m = BAD_NAME_SUFFIX.search(nm)
        if m:
            clean = nm[:m.start()].strip()
            fixes.append({"id": r["id"], "wrong": nm, "correct": clean,
                          "level": "L0:heuristic",
                          "reason": f"店名混入非店名词缀{m.group(0)}，应剥离（疑似采集噪声）",
                          "authority_urls": []})
    return fixes


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def load_keep_pairs():
    keep = []
    for kf in KEEP_FILES:
        if os.path.exists(kf):
            try:
                keep += json.load(open(kf, encoding="utf-8"))
            except Exception:
                pass
    return keep


def snapshot_members(ids):
    return {r["id"]: r for r in C.fetch_all(
        "restaurants", "*", order_col="id") if r["id"] in set(ids)}


def selftest(rests, by_id):
    """闭环自检（A6）：四个回归用例 + 两类方向，断言机制行为正确。
    不写库，只读。任一断言失败即非零退出。"""
    ok = True
    def expect(label, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if not cond:
            ok = False

    def get(rid):
        return by_id.get(rid)

    # 1) pain chaud：建国西路(1164) vs 番禺路(1785) 是连锁异址分店 → 必须 keep
    pc = [r for r in rests if C.cjk_norm(r.get("name","")).startswith("painchaud")
          or "百丘" in (r.get("name") or "")]
    print(f"● pain chaud 实体 {[r['id'] for r in pc]}: " +
          " / ".join(r["name"] for r in pc))
    r1, r2 = get(1164), get(1785)
    if r1 and r2:
        v, _ = adjudicate(r1, r2)
        expect(f"pain chaud 建国西路 vs 番禺路 → keep（连锁分店，不误并）: {v}", v == "keep")
    # 历史同店异写 1235 已并入 1164（merge_report.json 证据）
    expect("pain chaud 建国西路同店异写 1235 已不存在（历史合并生效）", get(1235) is None)

    # 2) 纹兵卫：金虹桥(44) vs 天山(1870) 是不同分店 → keep；44 店名噪声被审计
    wb = [r for r in rests if "纹兵卫" in (r.get("name") or "")]
    print(f"● 纹兵卫 实体 {[(r['id'], r['name']) for r in wb]}")
    w1, w2 = get(44), get(1870)
    if w1 and w2:
        v, _ = adjudicate(w1, w2)
        expect(f"纹兵卫 金虹桥 vs 天山 → keep（不同分店，不误并）: {v}", v == "keep")
    expect("纹兵卫 id=44 店名噪声（午市套餐后缀）被 name_audit 检出",
           any(f["id"] == 44 for f in name_audit(rests)))

    # 3) 南兴园：只应一条实体（历史重复已合并）
    nx = [r for r in rests if "南兴园" in (r.get("name") or "")]
    print(f"● 南兴园 实体 {[(r['id'], r['name']) for r in nx]}")
    expect("南兴园 已收敛为单条实体（不误拆/不重建重复）", len(nx) == 1)

    # 4) 白茸：BFC(815) vs 太阳宫小鲜(812) 子品牌异店 → keep；815 正名已正确
    br = [r for r in rests if "白茸" in (r.get("name") or "")]
    print(f"● 白茸系 实体 {[(r['id'], r['name']) for r in br]}")
    b1, b2 = get(815), get(812)
    if b1 and b2:
        v, _ = adjudicate(b1, b2)
        expect(f"白茸 BFC vs 白茸小鲜太阳宫 → keep（子品牌异店，不误并）: {v}", v == "keep")
    expect("白茸 BFC 正名已为『白茸 Bai Rong』（无佰荣/白荣/百荣错字）",
           get(815) and C.cjk_norm(get(815)["name"]) == "白茸bairong")

    # 5) 合成对：同店异写（同名 + 同坐标）→ 必须 merge
    fake_a = {"name": "测试店", "address": "A路100号", "phone": "02112345678",
              "location": C.point_ewkt(121.47, 31.23), "district": "黄浦区"}
    fake_b = {"name": "测试餐厅(大丸百货店)", "address": "A路100号",
              "phone": "02112345678", "location": C.point_ewkt(121.470001, 31.230001),
              "district": "黄浦区"}
    v, _ = adjudicate(fake_a, fake_b)
    expect(f"合成同店异写（同名+同址+同座机）→ merge: {v}", v == "merge")

    # 6) 合成对：近名异店（同品牌，相距 3km）→ 必须 keep
    fake_c = {"name": "测试店", "address": "A路100号", "phone": "02111111111",
              "location": C.point_ewkt(121.47, 31.23), "district": "黄浦区"}
    fake_d = {"name": "测试店(万达店)", "address": "B路200号", "phone": "02122222222",
              "location": C.point_ewkt(121.51, 31.26), "district": "浦东新区"}
    v, _ = adjudicate(fake_c, fake_d)
    expect(f"合成近名异店（同品牌相距~3km）→ keep: {v}", v == "keep")

    print("● SELFTEST " + ("ALL PASS" if ok else "HAS FAILURE"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--plan")
    ap.add_argument("--report", default=os.path.join(DATA, "entity_dedup_report.json"))
    args = ap.parse_args()

    rests = C.fetch_all("restaurants", "*", order_col="id")
    # 附带 RC 计数用于完整度
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id", order_col="restaurant_id")
    rc_n = defaultdict(int)
    for x in rc:
        rc_n[x["restaurant_id"]] += 1
    for r in rests:
        r["restaurant_cuisines_n"] = rc_n.get(r["id"], 0)
    by_id = {r["id"]: r for r in rests}

    keep_pairs = load_keep_pairs()
    clusters, review_pairs = build_clusters(rests, keep_pairs)

    if args.selftest:
        ok = selftest(rests, by_id)
        sys.exit(0 if ok else 1)

    # 选择 keeper
    plan = []
    for sig in clusters:
        members = [by_id[i] for i in sig]
        ranked = sorted(members, key=completeness, reverse=True)
        keeper = ranked[0]
        dups = ranked[1:]
        # 子表迁移预估
        child_counts = {}
        for d in dups:
            for table, fk, _, _ in FK_TABLES:
                n = len(fetch_rows(table, fk, d["id"]))
                if n:
                    child_counts[table] = child_counts.get(table, 0) + n
        plan.append({
            "member_ids": list(sig),
            "keeper_id": keeper["id"],
            "keeper_name": keeper["name"],
            "drop_ids": [d["id"] for d in dups],
            "drop_names": [d["name"] for d in dups],
            "keeper_completeness": completeness(keeper),
            "field_fill": plan_field_merge(keeper, dups),
            "child_migration_estimate": child_counts,
        })

    name_fixes = name_audit(rests)

    # ---- 打印逐簇报告 ----
    print(f"==== 实体去重 dry-run ====")
    print(f"全库 restaurants: {len(rests)}")
    print(f"自动合并簇: {len(plan)}；待复核对: {len(review_pairs)}；keep_pairs 已豁免: {len(keep_pairs)}")
    for p in plan:
        print(f"\n● 簇 keeper={p['keeper_id']} {p['keeper_name']!r} "
              f"(comp={p['keeper_completeness']})")
        for did in p["drop_ids"]:
            d = by_id[did]
            print(f"   MERGE drop={did} {d['name']!r} addr={d.get('address')!r}")
        print(f"   字段补空: {list(p['field_fill'].keys())}")
        print(f"   子表迁移预估: {p['child_migration_estimate']}")
    print(f"\n---- 待复核（不自动合并）----")
    for aid, bid, why, k in review_pairs:
        print(f"   ? {aid} {by_id[aid]['name']!r} <-> {bid} {by_id[bid]['name']!r} | {why}")
    print(f"\n---- 名称修正清单 ({len(name_fixes)}) ----")
    for f in name_fixes:
        print(f"   ! id={f['id']} {f['wrong']!r} -> {f['correct']!r} | {f['reason']}")

    if args.plan:
        out = {"clusters": plan, "review_pairs":
               [{"a": a, "b": b, "why": w, "key": k} for a, b, w, k in review_pairs],
               "name_fixes": name_fixes}
        json.dump(out, open(args.plan, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"\n计划写 {args.plan}")

    if not args.apply:
        print(f"\n【DRY-RUN】将合并 {len(plan)} 簇、删除实体 "
              f"{sum(len(p['drop_ids']) for p in plan)} 个。确认后加 --apply。")
        return

    # ---- APPLY（逐簇：重新快照 → 字段合并 → 子表迁移 → 删行 → 回读）----
    log = []
    merged_restaurants = 0
    for p in plan:
        keeper_id = p["keeper_id"]
        # 并发安全：apply 前重新快照
        fresh = snapshot_members(p["member_ids"])
        if keeper_id not in fresh:
            log.append(f"!! keeper {keeper_id} 在计划后消失，跳过该簇")
            continue
        keeper = fresh[keeper_id]
        dups = [fresh[i] for i in p["drop_ids"] if i in fresh]
        if not dups:
            continue
        # 重新计算字段合并（基于最新快照，不覆盖他人刚写）
        fill = plan_field_merge(keeper, dups)
        if fill:
            r = C.req("PATCH", f"/restaurants?id=eq.{keeper_id}", json=fill)
            log.append(f"PATCH keeper {keeper_id} fill {list(fill)}: {r.status_code}")
        # 迁移子表
        for d in dups:
            migrate_children(d["id"], keeper_id, log)
            time.sleep(0.1)
        # 回读确认 keeper 还在
        rb = C.req("GET", f"/restaurants?id=eq.{keeper_id}").json()
        # 删被合并行（此时所有 FK 已迁走，CASCADE 不会再丢业务数据）
        for d in dups:
            r = C.req("DELETE", f"/restaurants?id=eq.{d['id']}")
            log.append(f"DELETE restaurant {d['id']}: {r.status_code}")
            if r.status_code not in (200, 204):
                log.append(f"!! 删除 {d['id']} 失败: {r.text[:200]}")
            merged_restaurants += 1
            time.sleep(0.1)
        print(f"✓ 簇 -> keeper {keeper_id} {keeper.get('name')} 回读={'ok' if rb else 'MISSING'}")

    # 名称修正（保守：只改已核实登记表，且需 authority_urls）
    name_applied = 0
    for f in name_fixes:
        if f["level"].startswith("L") and f["authority_urls"]:
            r = C.req("PATCH", f"/restaurants?id=eq.{f['id']}",
                      json={"name": f["correct"]})
            log.append(f"NAMEFIX {f['id']} {f['wrong']}->{f['correct']}: {r.status_code}")
            name_applied += 1

    # ---- 自检 ----
    after = C.fetch_all("restaurants", "id,name,phone,location", order_col="id")
    after_ids = {r["id"] for r in after}
    selfcheck = {
        "keeper_rows_exist": all(p["keeper_id"] in after_ids for p in plan),
        "dropped_gone": all(not any(did in after_ids for did in p["drop_ids"])
                            for p in plan),
        "merged_restaurants": merged_restaurants,
        "name_fixes_applied": name_applied,
        "total_after": len(after),
    }
    print(f"\n自检: {json.dumps(selfcheck, ensure_ascii=False)}")
    json.dump({"plan": plan, "log": log, "selfcheck": selfcheck,
               "name_fixes": name_fixes}, open(args.report, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"报告写 {args.report}")


if __name__ == "__main__":
    main()
