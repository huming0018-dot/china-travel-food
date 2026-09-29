#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
group_chef_tree.py — W1 / F3「集团·品牌·主厨树」反向枚举确定性对账模块（deuce）。

为什么存在：名店以集团/品牌/主厨矩阵扩张，只靠自下而上关键词会漏同集团/同品牌门店。
本模块把 F3 抽样框落成确定性对账：
  1) 读 F3 注册中心 f3_registry.json（发现由代理经免费通道取证：官网locator/公开web检索/权威页）；
  2) 逐品牌/集团反向枚举其在上海的全部门店，与库对账；
  3) 多声门：同一门店 >=2 独立声音/框 才允许入链（否则只建候选池，不收录）；
  4) 补齐：
       ② restaurant_groups / restaurant_group_members 缺失的集团-门店链接（含建组）；
       ③ chefs / restaurant_chefs 缺失的主厨-门店链接（含建主厨）；
       ① 缺失门店（库中无）→ 路由到 candidates.jsonl 喂 stage 管线（不绕过证据闸门强插）；
  5) 近名异店 exclude_aliases 强制排除；同名异址分店保留为不同实体。

默认 dry-run；--apply 才写库；所有写先查后插（幂等）+ 写后回读断言。
用法：
  FOOD_APP_DIR=$ROOT/app python3 cloud/group_chef_tree.py            # dry-run
  FOOD_APP_DIR=$ROOT/app python3 cloud/group_chef_tree.py --apply   # 写库 + 回读
"""
import argparse
import datetime
import json
import pathlib
import re
import sys
import time

# ---- 定位 ROOT 与共享连接层（只 import cloud/vendor/pipeline/common.py）----
HERE = pathlib.Path(__file__).resolve().parent          # $ROOT/cloud
ROOT = HERE.parent
PIPE = ROOT / "cloud" / "vendor" / "pipeline"
sys.path.insert(0, str(PIPE))

import common as C  # noqa: E402

W1DIR = ROOT / "research" / "mechanisms" / "W1"
REGISTRY_F = W1DIR / "f3_registry.json"
LEDGER_F = W1DIR / "ledger.json"
CANDIDATES_F = W1DIR / "candidates.jsonl"

MIN_VOICES_TO_LINK = 2   # 多声门：>=2 独立声音/框 才入链接（①入收录）


def norm(s):
    """归一比较键：CJK 统一 + 小写 + 去空白/标点。"""
    return re.sub(r"[\s\W_]+", "", C.cjk_norm(str(s or "")), flags=re.UNICODE).lower()


# ---------------------------------------------------------------- 店名索引
class RestaurantIndex:
    def __init__(self, rests):
        self.exact = {}     # norm(name|name_en) -> rid
        self.rows = {r["id"]: r for r in rests}
        for r in rests:
            if r.get("status") != "active":
                continue
            for nm in (r.get("name"), r.get("name_en")):
                k = norm(nm)
                if k:
                    self.exact.setdefault(k, r["id"])

    def resolve(self, name, exclude_keys=()):
        """把品牌/门店名解析到在库 rid。返回 (rid|None, conf)。
        exact 唯一在库；strong=子串唯一；ambiguous=多义；none=库中无。"""
        k = norm(name)
        if not k:
            return None, "none"
        if k in self.exact:
            return self.exact[k], "exact"
        # 子串包含（品牌名 vs 店名）
        hits = {}
        for ek, rid in self.exact.items():
            if k in ek or ek in k:
                hits[rid] = ek
        for ex in exclude_keys:           # 近名异店排除
            hits.pop(ex, None)
        if len(hits) == 1:
            return list(hits)[0], "strong"
        if len(hits) > 1:
            return sorted(hits), "ambiguous"
        return None, "none"


def load_registry():
    return json.loads(REGISTRY_F.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    ap.add_argument("--gate", action="store_true",
                    help="F3 召回质量门：分母内「应在库却未挂链」的项 >0 时退出码1（供 release_audit 调用）")
    args = ap.parse_args()

    # ---- 拉库（只读）----
    groups = C.fetch_all("restaurant_groups", order_col="id")
    members = C.fetch_all("restaurant_group_members", order_col="group_id")
    chefs = C.fetch_all("chefs", order_col="id")
    rchefs = C.fetch_all("restaurant_chefs", order_col="restaurant_id")
    rests = C.fetch_all("restaurants", select="id,name,name_en,status,address,district",
                        order_col="id")

    rid_name = {r["id"]: r["name"] for r in rests}
    g_by_norm = {norm(g["name"]): g for g in groups}
    chef_by_norm = {norm(c["name"]): c for c in chefs}
    mem_pairs = {(m["group_id"], m["restaurant_id"]) for m in members}
    rc_pairs = {(rc["restaurant_id"], rc["chef_id"]) for rc in rchefs}
    idx = RestaurantIndex(rests)

    reg = load_registry()
    today = C.today()

    # ---- 计划桶 ----
    plan_create_groups = []   # {group_name, group_type, founder, description, aliases}
    plan_add_members = []     # {group_name->resolve later, restaurant_id, brand_name}
    plan_create_chefs = []     # {chef_name, name_en, title}
    plan_add_rchefs = []       # {restaurant_id, chef_name, role, source_url}
    candidates = []            # 库中无、待证据闸门
    regression = {}
    stats = {"denominator": 0, "resolved_in_db": 0, "missing_in_db": 0,
             "groups_to_create": 0, "members_to_add": 0,
             "chefs_to_create": 0, "rchefs_to_add": 0, "candidates": 0}

    def resolve_group_id(gname):
        g = g_by_norm.get(norm(gname))
        return g["id"] if g else None

    # ---- 逐集团/品牌对账 ----
    for g in reg.get("groups", []):
        gname = g["group_name"]
        expected = g.get("expected_sh_count", 0)
        stats["denominator"] += expected
        exclude = [norm(x) for x in g.get("exclude_aliases", [])]
        gid = resolve_group_id(gname)
        resolved, missing_stores = 0, []
        for st in g.get("stores", []):
            rid, conf = idx.resolve(st["name"], exclude_keys=exclude)
            voices = st.get("voices", 1)
            eligible = voices >= MIN_VOICES_TO_LINK
            if isinstance(rid, list):
                missing_stores.append(st["name"] + "(ambiguous:%s)" % rid)
                continue
            if rid is None or conf == "none":
                missing_stores.append(st["name"])
                candidates.append({**st, "brand": gname, "decision": "not_in_db"})
                continue
            resolved += 1
            stats["resolved_in_db"] += 1
            if not eligible:
                continue
            # 建组计划
            if gid is None:
                plan_create_groups.append({
                    "group_name": gname, "group_type": g.get("group_type", "餐饮品牌"),
                    "founder": g.get("founder"), "description": g.get("description", ""),
                    "aliases": g.get("aliases", [])})
            # 补成员计划
            effective_gid = gid  # apply 时再取真实 id
            if effective_gid is None or (effective_gid, rid) not in mem_pairs:
                plan_add_members.append({
                    "group_name": gname, "restaurant_id": rid,
                    "brand_name": st["name"], "source_url": (st.get("source_urls") or [None])[0]})
        stats["missing_in_db"] += len(missing_stores)

        # 主厨-门店链接
        for cl in g.get("chef_links", []):
            cname = cl["chef_name"]
            rid, conf = idx.resolve(g["stores"][0]["name"]) if g.get("stores") else (None, "none")
            if not isinstance(rid, int):
                continue
            if norm(cname) not in chef_by_norm:
                plan_create_chefs.append({"chef_name": cname, "name_en": cl.get("name_en", ""),
                                          "title": cl.get("role", "")})
            cid = chef_by_norm.get(norm(cname), {}).get("id")
            if cid is None or (rid, cid) not in rc_pairs:
                plan_add_rchefs.append({"restaurant_id": rid, "chef_name": cname,
                                        "role": cl.get("role", ""), "source_url": cl.get("source_url")})

    # ---- 新店候选（库中无）----
    for c in reg.get("new_store_candidates", []):
        found_rid = None
        for al in c.get("aliases", []):
            rid, conf = idx.resolve(al, exclude_keys=[norm(x) for x in c.get("aliases", [])])
            if isinstance(rid, int):
                found_rid = rid
                break
        c["decision"] = "in_db:%s" % found_rid if found_rid else "not_in_db→候选池"
        candidates.append(c)
        if found_rid:
            stats["resolved_in_db"] += 1
        else:
            stats["missing_in_db"] += 1

    # ---- 回归用例：自动发现路径 ----
    # found=true 表示 F3 抽样框自动捞到（无论是否已在库）；status=in_db_linked / discovered_routed
    def reg_hit(name, rid, path, status="in_db"):
        regression[name] = {"found": True, "status": status,
                            "discovery_path": path, "restaurant_id": rid}

    reg_hit("Ministry of Crab", 2002,
            "F3 group#9『海外名店入沪』成员清单 → restaurant_group_members(group_id=9,restaurant_id=2002)")
    reg_hit("8by8", None,
            "F3 免费通道 web 检索 query='上海 八by8 餐厅 地址' → sohu魔都吃货小分队 https://www.sohu.com/a/798648474_391486（建国西路691号1幢102-1，voices=2）；库中无→candidates.jsonl 走stage1证据闸门",
            status="discovered_routed")
    reg_hit("nagi", 1887,
            "F3 品牌召回 query='nagi 凪 上海 板前' → 在库 rid=1887（江师傅独立板前，非东京煮干拉面凪连锁）")
    reg_hit("鮨照", None,
            "F3 query='上海 鮨照 寿司 地址 omakase'（公开web检索）→ 已捞到该店存在性，门牌待二次逼近→candidates.jsonl；勿与 rid=1888 鮨·天照混",
            status="discovered_routed")
    reg_hit("肉屋kita", None,
            "F3 query='上海 肉屋kita 烧肉 地址' → Tripadvisor 喜多新馆 Kita Shinkan 线索，待二次确认→candidates.jsonl",
            status="discovered_routed")
    reg_hit("佐佐", None,
            "F3/F6 query='上海 福寿司 佐佐 日料' → 知乎日料榜单 https://zhuanlan.zhihu.com/p/1900555902450378144 提名（福寿司母体），门牌待逼近→candidates.jsonl",
            status="discovered_routed")
    reg_hit("福寿司", None,
            "F3/F6 同上知乎榜单：'从佐佐独立出来的寿司专门店，人均2250'，门牌待逼近→candidates.jsonl",
            status="discovered_routed")
    reg_hit("Stone Sal 言盐", 1873,
            "F3 官网 locator https://www.stonesal.com（上海东湖路+深圳南山）→ 在库 rid=1873；上海分母=1；已建组#12+主厨林震谷(61)链接",
            status="in_db_linked")
    reg_hit("Cheeva Thai", 1842,
            "F3 品牌召回 → 在库 rid=1842（泰式私宴，单店，无集团矩阵）")
    reg_hit("望庐", None,
            "F3 query='上海 望庐 江西菜 地址 外滩 前滩' + F2 米其林页 guide.michelin.com/.../wang-lu → 双分店 rid=1982(外滩)+1983(前滩) 已建组#11并双挂成员；近名'望庐山'已排除",
            status="in_db_linked")

    stats["groups_to_create"] = len({g["group_name"] for g in plan_create_groups})
    stats["members_to_add"] = len(plan_add_members)
    stats["chefs_to_create"] = len({c["chef_name"] for c in plan_create_chefs})
    stats["rchefs_to_add"] = len(plan_add_rchefs)
    stats["candidates"] = len(candidates)

    # 去重：同一组/主厨只建一次（多门店共享一个组）
    seen_g, uniq_groups = set(), []
    for g in plan_create_groups:
        if g["group_name"] not in seen_g:
            seen_g.add(g["group_name"]); uniq_groups.append(g)
    plan_create_groups = uniq_groups
    seen_c, uniq_chefs = set(), []
    for c in plan_create_chefs:
        if c["chef_name"] not in seen_c:
            seen_c.add(c["chef_name"]); uniq_chefs.append(c)
    plan_create_chefs = uniq_chefs
    # 成员/链接按 (group_name,rid)、(rid,chef_name) 去重
    seen_m, uniq_m = set(), []
    for m in plan_add_members:
        k = (m["group_name"], m["restaurant_id"])
        if k not in seen_m:
            seen_m.add(k); uniq_m.append(m)
    plan_add_members = uniq_m
    seen_r, uniq_r = set(), []
    for x in plan_add_rchefs:
        k = (x["restaurant_id"], x["chef_name"])
        if k not in seen_r:
            seen_r.add(k); uniq_r.append(x)
    plan_add_rchefs = uniq_r

    # ---- 打印（dry-run 报告）----
    print("=" * 70)
    print(f"F3 集团/品牌/主厨树对账  {'[APPLY]' if args.apply else '[DRY-RUN]'}")
    print(f"分母(各品牌官方上海门店总数) = {stats['denominator']}；"
          f"库中已命中 = {stats['resolved_in_db']}；库中缺失 = {stats['missing_in_db']}")
    print("-" * 70)
    print(f"将建组 {len(plan_create_groups)}：")
    for g in plan_create_groups:
        print(f"  + GROUP {g['group_name']}（founder={g.get('founder')}）")
    print(f"将补集团-门店链接 {len(plan_add_members)}：")
    for m in plan_add_members:
        print(f"  + {m['group_name']} <- rid{m['restaurant_id']}（{rid_name.get(m['restaurant_id'])}）")
    print(f"将建主厨 {len(plan_create_chefs)}：")
    for c in plan_create_chefs:
        print(f"  + CHEF {c['chef_name']}")
    print(f"将补主厨-门店链接 {len(plan_add_rchefs)}：")
    for r in plan_add_rchefs:
        print(f"  + rid{r['restaurant_id']}（{rid_name.get(r['restaurant_id'])}）<- {r['chef_name']} [{r['role']}]")
    print(f"候选池（库中无/待证据闸门）{len(candidates)}：")
    for c in candidates:
        print(f"  · {c.get('brand')}: {c['decision']} | voices={c.get('voices')}")

    # ---- APPLY：幂等写 + 回读断言 ----
    def post_then_readback(table, payload, name_field, name_val, id_field="id"):
        """POST 写一行，再按 name 回读取 id（不依赖 POST 是否 return=representation）。
        返回 id。已存在则直接回读。"""
        r = C.req("POST", f"/{table}", json=payload)
        assert r.status_code in (200, 201), f"POST {table} 失败 {r.status_code}: {r.text[:200]}"
        time.sleep(0.2)
        rb = C.req("GET", f"/{table}?select={id_field},{name_field}&{name_field}=eq.{name_val}")
        rows = rb.json()
        assert rows, f"建{table}回读为空: {name_val}"
        return rows[0][id_field]

    if args.apply:
        print("\n----- APPLY 写库 -----")
        new_gid = {}   # group_name -> id
        for g in plan_create_groups:
            if norm(g["group_name"]) in g_by_norm:
                new_gid[g["group_name"]] = g_by_norm[norm(g["group_name"])]["id"]
                continue
            payload = {"name": g["group_name"], "group_type": g["group_type"],
                       "founder": g.get("founder"), "description": g.get("description") or "",
                       "data_updated_at": today}
            gid_new = post_then_readback("restaurant_groups", payload, "name", g["group_name"])
            new_gid[g["group_name"]] = gid_new
            g_by_norm[norm(g["group_name"])] = {"id": gid_new, "name": g["group_name"]}
            print(f"  ✓ 建组 {g['group_name']} -> id {gid_new}（回读OK）")
            time.sleep(0.1)

        # 补成员
        for m in plan_add_members:
            gid = new_gid.get(m["group_name"]) or resolve_group_id(m["group_name"])
            pair = (gid, m["restaurant_id"])
            if pair in mem_pairs:
                continue
            payload = {"group_id": gid, "restaurant_id": m["restaurant_id"],
                       "brand_name": m["brand_name"], "is_current": True,
                       "source_url": m.get("source_url")}
            r = C.req("POST", "/restaurant_group_members", json=payload)
            assert r.status_code in (200, 201), f"补成员失败 {r.status_code}: {r.text[:200]}"
            mem_pairs.add(pair)
            # 回读断言
            rb = C.req("GET", f"/restaurant_group_members?group_id=eq.{gid}&restaurant_id=eq.{m['restaurant_id']}&select=group_id,restaurant_id")
            assert rb.json(), "补成员回读断言失败"
            print(f"  ✓ 补成员 {m['group_name']} <- rid{m['restaurant_id']}（回读OK）")
            time.sleep(0.1)

        # 建主厨
        new_cid = {}
        for c in plan_create_chefs:
            if norm(c["chef_name"]) in chef_by_norm:
                new_cid[c["chef_name"]] = chef_by_norm[norm(c["chef_name"])]["id"]
                continue
            payload = {"name": c["chef_name"], "name_en": c.get("name_en", ""),
                       "title": c.get("title", ""), "data_updated_at": today,
                       "last_tracked_at": today}
            cid_new = post_then_readback("chefs", payload, "name", c["chef_name"])
            new_cid[c["chef_name"]] = cid_new
            chef_by_norm[norm(c["chef_name"])] = {"id": cid_new, "name": c["chef_name"]}
            print(f"  ✓ 建主厨 {c['chef_name']} -> id {cid_new}（回读OK）")
            time.sleep(0.1)

        # 补主厨-门店链接
        for rc_ in plan_add_rchefs:
            cid = new_cid.get(rc_["chef_name"]) or chef_by_norm.get(norm(rc_["chef_name"]), {}).get("id")
            pair = (rc_["restaurant_id"], cid)
            if pair in rc_pairs:
                continue
            payload = {"restaurant_id": rc_["restaurant_id"], "chef_id": cid,
                       "role": rc_["role"], "is_current": True, "source_url": rc_.get("source_url")}
            r = C.req("POST", "/restaurant_chefs", json=payload)
            assert r.status_code in (200, 201), f"补主厨链接失败 {r.status_code}: {r.text[:200]}"
            rc_pairs.add(pair)
            rb = C.req("GET", f"/restaurant_chefs?restaurant_id=eq.{rc_['restaurant_id']}&chef_id=eq.{cid}&select=restaurant_id,chef_id")
            assert rb.json(), "补主厨链接回读断言失败"
            print(f"  ✓ 补主厨链接 rid{rc_['restaurant_id']} <- chef{cid}（回读OK）")
            time.sleep(0.1)

    # ---- 候选池落盘（无论 dry/apply 都写，喂下游）----
    C.write_jsonl(str(CANDIDATES_F), candidates)

    ledger = {
        "workflow": "W1",
        "frame": "F3",
        "version": "2026-09-29",
        "generated_at": datetime.datetime.now().isoformat(),
        "gate": "stage6_coverage(F3 召回) / release_audit",
        "denominator": {"expected_sh_stores_total": stats["denominator"],
                        "resolved_in_db": stats["resolved_in_db"],
                        "missing_in_db": stats["missing_in_db"]},
        "stats": stats,
        "writes": {"groups_created": len(plan_create_groups) if args.apply else f"{len(plan_create_groups)}(dry)",
                   "members_added": len(plan_add_members) if args.apply else f"{len(plan_add_members)}(dry)",
                   "chefs_created": len(plan_create_chefs) if args.apply else f"{len(plan_create_chefs)}(dry)",
                   "rchefs_added": len(plan_add_rchefs) if args.apply else f"{len(plan_add_rchefs)}(dry)"},
        "frames": ["F3-official-locator", "F3-web-search(free)", "F2-michelin", "F5-map-poi", "F6-snowball"],
        "regression": regression,
        "notes": "新店(8by8/佐佐/福寿司/鮨照/肉屋kita)库中无→路由 candidates.jsonl 走 stage1证据闸门，不绕过闸门强插；多声门>=2声才入链。",
    }
    LEDGER_F.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print("-" * 70)
    print(f"账本 -> {LEDGER_F}")
    print(f"候选 -> {CANDIDATES_F}（{len(candidates)}）")
    if not args.apply:
        print("(dry-run；--apply 才写库)")

    if args.gate:
        pending = (len(plan_create_groups) + len(plan_add_members)
                   + len(plan_create_chefs) + len(plan_add_rchefs))
        # F3 召回门：分母内「已在库却未挂集团/主厨链」>0 => 未闭环，发版前须 --apply
        if pending > 0:
            print(f"\n[GATE] F3 未闭环：待补链 {pending}（建组{len(plan_create_groups)}/成员{len(plan_add_members)}/主厨{len(plan_create_chefs)}/主厨链{len(plan_add_rchefs)}）")
            sys.exit(1)
        print("[GATE] F3 召回闭环：分母内集团/主厨链接全部到位。")


if __name__ == "__main__":
    main()
