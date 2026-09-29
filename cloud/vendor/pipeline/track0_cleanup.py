#!/usr/bin/env python3
"""Track 0 实体清理（确定性、幂等、可回滚）。

只做两类确定性写：
  A. 脏区名归一：district 以「海市」开头（缺"上"）→ 补为「上海市」。
     例：海市长宁区 → 上海市长宁区。纯字符串前缀修正，23 条。
  B. chef#37（邓师傅）restaurants_owned 数组去重：
     ['南兴园','南兴园 NAN·XING·YUAN'] → ['南兴园']（canonical 为准，异写并入 aliases 思路）。

红线：
  - 默认 dry-run；--apply 才写。
  - 只 PATCH 目标字段（district / restaurants_owned），其余字段零触碰。
  - apply 前后对目标行做非目标字段校验和比对，确保零误伤。
  - 幂等：已修正的行重跑 = 0 变更。
  - 点名店（南兴园/纹兵卫/pain chaud/白茸/天吉）只作回归用例，不手补、不猜错分店。
"""
import sys, os, json, hashlib, argparse, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

DATA = "/app/data"


def snapshot_non_target(rests, target_ids, fields_excluded):
    """对目标行做非目标字段校验和。返回 {id: sha1}。"""
    out = {}
    for r in rests:
        if r["id"] not in target_ids:
            continue
        payload = {k: v for k, v in r.items() if k not in fields_excluded}
        out[r["id"]] = hashlib.sha1(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()
    return out


def plan_district_fix(rests):
    """返回 [(id, old_district, new_district, name)]。"""
    out = []
    for r in rests:
        d = r.get("district") or ""
        if d.startswith("海市") and not d.startswith("上海市"):
            new = "上" + d  # 海市长宁区 → 上海市长宁区
            out.append((r["id"], d, new, r.get("name")))
    return out


def plan_chef_owned_dedup():
    """chef#37 owned 数组去重。返回 (chef_id, old_list, new_list) 或 None。"""
    rows = C.req("GET", "/chefs?id=eq.37").json()
    if not rows:
        return None
    c = rows[0]
    owned = c.get("restaurants_owned") or []
    # canonical = '南兴园'；去掉带拼音/英文后缀的异写
    canonical = "南兴园"
    new = []
    for x in owned:
        if x == canonical:
            new.append(x)
        elif C.cjk_norm(x).startswith(C.cjk_norm(canonical)):
            # 异写（如 南兴园 NAN·XING·YUAN）→ 丢弃，canonical 已在列
            continue
        else:
            new.append(x)
    new = list(dict.fromkeys(new))  # 保序去重
    if new == owned:
        return None
    return (37, owned, new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--plan", default=os.path.join(DATA, "track0_cleanup_plan.json"))
    args = ap.parse_args()

    print("==== Track0 实体清理 " + ("APPLY" if args.apply else "DRY-RUN") + " ====")
    rests = C.fetch_all("restaurants",
                        "id,name,district,phone,location,price_avg,score_total,status",
                        order_col="id")

    # ---- A. 脏区名 ----
    dist_fixes = plan_district_fix(rests)
    print(f"\n[A] 脏区名归一（海市X区→上海市X区）: {len(dist_fixes)} 条")
    target_ids = set()
    for rid, old, new, name in dist_fixes:
        print(f"    id={rid:<5} {old!r} → {new!r}  ({name})")
        target_ids.add(rid)

    # ---- B. chef#37 owned 去重 ----
    chef_plan = plan_chef_owned_dedup()
    print(f"\n[B] chef#37 owned 去重: " +
          (f"{chef_plan[1]} → {chef_plan[2]}" if chef_plan else "无需变更"))

    # ---- 非目标字段校验和快照（apply 前）----
    before_cs = snapshot_non_target(rests, target_ids, {"district"})
    print(f"\n非目标字段校验和快照: {len(before_cs)} 行（apply 后比对须一致）")

    plan = {"district_fixes": [{"id": i, "old": o, "new": n, "name": nm}
                               for i, o, n, nm in dist_fixes],
            "chef_owned": chef_plan,
            "before_checksums": before_cs}
    json.dump(plan, open(args.plan, "w"), ensure_ascii=False, indent=1)
    print(f"计划写 {args.plan}")

    if not args.apply:
        print(f"\n【DRY-RUN】将修 {len(dist_fixes)} 条区名"
              f"{'、chef#37 owned 去重' if chef_plan else ''}。确认后加 --apply。")
        return

    # ---- APPLY ----
    applied = 0
    for rid, old, new, name in dist_fixes:
        r = C.req("PATCH", f"/restaurants?id=eq.{rid}",
                  json={"district": new})
        if r.status_code in (200, 204):
            applied += 1
        else:
            print(f"  !! PATCH id={rid} failed: {r.status_code} {r.text[:200]}")
    print(f"\n[A] 已 PATCH {applied}/{len(dist_fixes)} 条区名")

    if chef_plan:
        cid, old, new = chef_plan
        r = C.req("PATCH", f"/chefs?id=eq.{cid}", json={"restaurants_owned": new})
        print(f"[B] chef#{cid} owned PATCH: {r.status_code}")

    # ---- 回读 ----
    print("\n---- 回读核对 ----")
    rests2 = C.fetch_all("restaurants",
                         "id,name,district,phone,location,price_avg,score_total,status",
                         order_col="id")
    after_cs = snapshot_non_target(rests2, target_ids, {"district"})
    mismatches = [i for i in target_ids if before_cs.get(i) != after_cs.get(i)]
    if mismatches:
        print(f"  !! 非目标字段校验和不一致: {mismatches}")
    else:
        print(f"  非目标字段校验和: {len(before_cs)} 行全部一致（零误伤）")

    # 验证区名已修正
    still_dirty = [r for r in rests2
                   if (r.get("district") or "").startswith("海市")]
    print(f"  仍为「海市」开头的行: {len(still_dirty)}（应为 0）")
    for rid, old, new, name in dist_fixes[:3]:
        got = next((r.get("district") for r in rests2 if r["id"] == rid), None)
        print(f"    id={rid} district={got!r} (期望 {new!r})")

    # chef 回读
    c2 = C.req("GET", "/chefs?id=eq.37").json()[0]
    print(f"  chef#37 owned={c2.get('restaurants_owned')}")


if __name__ == "__main__":
    main()
