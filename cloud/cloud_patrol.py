#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cloud_patrol.py — 上海美食图鉴「数据完整性巡逻 / 保鲜」总编排器（非浏览器，REST）。

把反复回潮的缺陷收敛成确定性、可周期运行的模块，而不是逐个手补：
  1. 实体去重  —— merge_duplicates（品牌多键 + 坐标距离），治 pain chaud 异名重复。
  2. 分类校验  —— patrol_classify（概念本体/改道/主身份/互斥），治拉面误挂、老干杯双标签。
  3. 价格归一  —— price_realign（场景内分位 P20/40/60/80，标签绑数值区间；009+1B-1），治跨菜系同价倒挂。
  4. Chef 质检 —— 补 restaurants_owned 关联；占位“XX主厨/师傅”、近似重复 → REVIEW（不自动删）。
  5. 保鲜复检  —— data_updated_at + 场景保鲜期 → 待复检清单（供 amap/电话/营业时间任务消费）。
  6. 简介补薄  —— semantic_description 缺失/过薄 → semantic_profile_generator 重生成（apply 时，限量）。

安全：默认 DRY，只检测/落 plan，绝不写库、不发告警；--apply 才执行高置信写并回读验证。
状态：patrol/state.json 以指纹记 first/last/status，diff 出 new/fixed；每次最多发一条 digest，
     无变化则每 24h 一条心跳，不逐条刷屏。

用法：
  python3 cloud_patrol.py            # 巡逻（dry）
  python3 cloud_patrol.py --apply    # 执行高置信修复 + digest 告警
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline"))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import common as C        # noqa: E402
import merge_duplicates as MD  # noqa: E402
import patrol_classify as PC   # noqa: E402
import entity_dedup as ED      # noqa: E402  (Phase 0-A 全子表实体去重+名称审计，只读)
import closed_watch as CW      # noqa: E402  (1B-2 关店/迁址/stale 只读扫描)

PATROL_DIR = DATA / "patrol"
STATE_F = PATROL_DIR / "state.json"
HEARTBEAT_H = 24

# 场景保鲜期（天）：快消短、正餐中、高端长
FRESH_SCENE = {"快餐小吃": 30, "面包": 30, "咖啡茶饮": 30, "甜品": 30,
               "酒吧": 60, "正餐": 90}
PLACEHOLDER_CHEF = r"^(.*?)(主厨|师傅|名厨|大师|主厨团队)$"


def now():
    return dt.datetime.now()


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(st):
    PATROL_DIR.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 1. 实体 ----------
def check_entities(rests):
    clusters = MD.find_clusters(rests, 100)
    out = []
    for core, cl in clusters:
        ranked = sorted(cl, key=MD.completeness, reverse=True)
        out.append({"fp": f"entity:{core}:{sorted(x['id'] for x in cl)}",
                    "core": core,
                    "master": ranked[0]["id"],
                    "dups": [x["id"] for x in ranked[1:]],
                    "label": f"{core}: keep {ranked[0]['id']}, merge {[x['id'] for x in ranked[1:]]}"})
    return out


# ---------- 1b. Phase 0-A 全子表实体去重 + 名称审计（只读，不自动合并） ----------
def check_entities_full(rests):
    """只读扫描：返回 (自动合并簇数, 待复核对数, 名称修正清单)。
    真正合并由 entity_dedup.py --apply 人工确认后执行，patrol 不自动写。"""
    try:
        keep = ED.load_keep_pairs()
        clusters, review = ED.build_clusters(rests, keep)
        fixes = ED.name_audit(rests)
        return len(clusters), len(review), fixes
    except Exception as e:  # 巡检绝不能因只读扫描失败而崩
        return 0, 0, [{"error": str(e)}]


# ---------- 4. Chef 质检 ----------
def check_chefs(rests, chefs):
    by_chefname = defaultdict(list)
    for r in rests:
        cn = (r.get("chef_name") or "").strip()
        if cn:
            by_chefname[C.cjk_norm(cn)].append(r["id"])
    findings, links = [], []
    seen_norm = {}
    for h in chefs:
        nm, hid = str(h.get("name") or ""), h["id"]
        norm = C.cjk_norm(nm)
        owned = h.get("restaurants_owned") or []
        # 占位符
        if not owned and re.match(PLACEHOLDER_CHEF, norm):
            findings.append({"fp": f"chef:placeholder:{hid}", "conf": "review",
                             "label": f"chef#{hid} '{nm}' 像占位符且未关联，建议清理/补全"})
        # 自动补链：chef_name 精确匹配
        if not owned and norm in by_chefname:
            rids = by_chefname[norm]
            links.append({"chef_id": hid, "restaurant_ids": rids,
                          "fp": f"chef:link:{hid}:{sorted(rids)}",
                          "label": f"chef#{hid} '{nm}' 补链 restaurants_owned={rids}"})
        # 近似重复
        for prev_norm, prev in seen_norm.items():
            if norm != prev_norm and (norm in prev_norm or prev_norm in norm) \
                    and abs(len(norm) - len(prev_norm)) <= 2:
                findings.append({"fp": f"chef:dupe:{min(hid, prev)}-{max(hid, prev)}",
                                 "conf": "review",
                                 "label": f"chef 近似重复 #{prev} '{prev_norm}' / #{hid} '{norm}'"})
        seen_norm[norm] = hid
    return findings, links


# ---------- 5. 保鲜 ----------
def check_freshness(rests):
    stale = []
    for r in rests:
        if r.get("status") != "active":
            continue
        scene = r.get("price_scene")
        days = FRESH_SCENE.get(scene, 90)
        if r.get("tier") in ("高档", "奢华"):
            days = 180
        upd = r.get("data_updated_at") or r.get("updated_at")
        if not upd:
            continue
        try:
            t = dt.datetime.fromisoformat(str(upd).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            continue
        age = (now() - t).days
        if age > days:
            stale.append({"id": r["id"], "name": r["name"], "age": age, "days": days})
    return stale


# ---------- 6. 简介过薄 ----------
def thin_profiles(rests):
    out = []
    for r in rests:
        sd = str(r.get("semantic_description") or "")
        if len(sd) < 24:
            out.append(r["id"])
    return out


def run_script(args, timeout=900):
    try:
        p = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                           timeout=timeout, cwd=str(HERE))
        return (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return "[timeout]"
    except Exception as e:  # noqa
        return f"[error {e}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rests = C.fetch_all("restaurants", "*", order_col="id")
    chefs = C.fetch_all("chefs", "*", order_col="id")

    entities = check_entities(rests)
    dedup_clusters, dedup_review, name_fixes = check_entities_full(rests)
    classify = PC.run(apply=False)
    chef_review, chef_links = check_chefs(rests, chefs)
    stale = check_freshness(rests)
    thin = thin_profiles(rests)

    # 价格：dry 跑 price_realign 取摘要（场景内分位，009+1B-1 为准；旧 stage7 已归档）
    price_out = run_script([str(PIPE / "price_realign.py")])
    price_line = next((l for l in price_out.splitlines() if l.strip()), "price_realign 无输出")

    # 汇总指纹
    current = {}
    for e in entities:
        current[e["fp"]] = ("entity", e["label"])
    for f in classify:
        if f["conf"] in ("high", "mid"):
            current[f"classify:{f['id']}:{f['action']}:{f['cuisine_id']}"] = (
                "classify", f"{f['action']} {f['cuisine']} @ {f['name']} ({f['conf']})")
    for f in chef_review:
        current[f["fp"]] = ("chef", f["label"])
    for l in chef_links:
        current[l["fp"]] = ("chef-link", l["label"])

    state = load_state()
    new = [k for k in current if k not in state]
    fixed = [k for k in state if k not in current]

    # 落保鲜/复检清单
    PATROL_DIR.mkdir(parents=True, exist_ok=True)
    (PATROL_DIR / "stale_reverify.json").write_text(
        json.dumps(stale, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 64)
    print(f"巡逻 {now():%Y-%m-%d %H:%M}  apply={args.apply}")
    print(f"  实体重复簇 : {len(entities)}（全子表版: {dedup_clusters} 簇 / {dedup_review} 待复核）")
    print(f"  名称修正   : {len(name_fixes)} 条（只读审计，不自动改写）")
    print(f"  分类 findings: {len(classify)}（high {sum(1 for x in classify if x['conf']=='high')}）")
    print(f"  价格归一   : {price_line[:80]}")
    print(f"  chef 补链  : {len(chef_links)}；chef 待审: {len(chef_review)}")
    print(f"  过保鲜期   : {len(stale)}；简介过薄: {len(thin)}")
    cw = CW.scan(rests)
    print(f"  关店扫描   : closed三要素缺={len(cw['closed_triple_missing'])} "
          f"active带关店信号={len(cw['active_with_closed_signal'])} "
          f"stale={len(cw['stale_active'])}（只读候选，不自动改）")
    print(f"  相对上次   : new={len(new)} fixed={len(fixed)}")

    if not args.apply:
        print("\n【DRY】未写库、未告警。确认机制后加 --apply，并接入 cron。")
        # 仍更新指纹首次出现时间（不触发告警）
        ts = now().isoformat(timespec="seconds")
        for k in new:
            state[k] = {"first": ts, "last": ts, "kind": current[k][0],
                        "label": current[k][1], "status": "open"}
        for k in fixed:
            state.pop(k, None)
        for k in current:
            if k in state:
                state[k]["last"] = ts
        save_state(state)
        return

    # ---- APPLY ----
    applied_log = []
    if entities:
        applied_log.append("merge: " + run_script([str(PIPE / "merge_duplicates.py"), "--commit"])[:400])
    classify_apply = PC.run(apply=True)
    applied_log.append(f"classify applied findings={len(classify_apply)}")
    applied_log.append("price: " + run_script([str(PIPE / "price_realign.py"), "--apply"])[:400])
    # chef 补链
    for l in chef_links:
        h = next(x for x in chefs if x["id"] == l["chef_id"])
        names = [next((r["name"] for r in rests if r["id"] == rid), "") for rid in l["restaurant_ids"]]
        rr = C.req("PATCH", f"/chefs?id=eq.{h['id']}", json={"restaurants_owned": names})
        applied_log.append(f"chef link {h['id']}: {rr.status_code}")
    # 简介补薄（限量 40，避免单轮过长）
    if thin:
        run_script([str(PIPE / "semantic_profile_generator.py"), "--commit", "--limit", "40"])

    # 回读：重算一次检测，标记 fixed
    rests2 = C.fetch_all("restaurants", "*", order_col="id")
    ent2 = check_entities(rests2)
    remain_fp = {e["fp"] for e in ent2}
    ts = now().isoformat(timespec="seconds")
    for k, v in current.items():
        if k not in state:
            state[k] = {"first": ts, "kind": v[0], "label": v[1]}
        state[k]["last"] = ts
        state[k]["status"] = "fixed" if k not in remain_fp and v[0] == "entity" else "open"
    for k in fixed:
        state.pop(k, None)
    save_state(state)

    # digest：有变化才发；否则每天一条心跳
    last_beat = state.get("_heartbeat", {}).get("last")
    due_beat = True
    if last_beat:
        try:
            due_beat = (now() - dt.datetime.fromisoformat(last_beat)).total_seconds() > HEARTBEAT_H * 3600
        except Exception:
            due_beat = True
    if new or fixed or due_beat:
        msg = (f"new={len(new)} fixed={len(fixed)}\n"
               f"实体簇 {len(entities)} | 分类 {len(classify)} | 过保鲜 {len(stale)} | 简介薄 {len(thin)}\n"
               f"chef 补链 {len(chef_links)} 待审 {len(chef_review)}")
        try:
            import health
            health.alert("美食图鉴·数据巡逻", msg)
        except Exception:
            pass
        state["_heartbeat"] = {"last": ts}
        save_state(state)
    print("\n【APPLY 完成】", "\n".join(applied_log)[:800])


if __name__ == "__main__":
    main()
