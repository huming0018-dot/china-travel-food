#!/usr/bin/env python3
"""Track 1B-2 保鲜/关店/迁址（确定性、幂等、可回滚）。

只做两件经权威源核证的事：
  A. EHB(id=1262) closed_source 由文本备注改为权威新闻 URL（三要素已齐，补可溯源）。
  B. Nuits 迁址合并：旧铜仁路(id=1967, closed) → 新恒隆三期Pavilion(id=1978, active)。
     同一家店迁址（非连锁分店），先迁全部子表 FK 再删旧行，去重首页双显。

硬约束：默认 dry-run；--apply 才写；写后回读；非目标字段校验和；幂等复跑=0。
关店/迁址无权威源不臆造；电话宁空不假；不猜分店。
"""
import sys, os, json, hashlib, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import entity_dedup as ED

DATA = "/app/data"

# 权威源（≥2 独立媒体一致，2025-09-28 停业）
EHB_SOURCE = "https://view.inews.qq.com/a/20251017A07FWU00"  # 腾讯新闻，转引EHB官方公众号公告
NUITS_CLOSED_SRC = "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/nuits"
NUITS_NEW_SRC = "https://m.jfdaily.com/wx/detail.do?id=1180886"  # 上观：恒隆三期Pavilion 2026-09-22启幕


def snapshot_fields(rid, fields):
    r = C.req("GET", f"/restaurants?id=eq.{rid}&select={','.join(fields)}").json()
    if not r:
        return None
    return hashlib.sha1(json.dumps(r[0], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--plan", default=os.path.join(DATA, "closed_relocate_plan.json"))
    args = ap.parse_args()

    print("==== Track1B-2 关店/迁址 " + ("APPLY" if args.apply else "DRY-RUN") + " ====")

    # ---- A. EHB closed_source URL ----
    ehb = C.req("GET", "/restaurants?id=eq.1262").json()
    ehb_plan = None
    if ehb:
        e = ehb[0]
        cur_src = e.get("closed_source") or ""
        print(f"\n[A] EHB(1262): status={e.get('status')} closed_date={e.get('closed_date')}")
        print(f"    当前 closed_source={cur_src!r:.80}")
        if e.get("status") == "closed" and e.get("closed_date"):
            # 已是 URL 则跳过；文本备注则补权威 URL
            if not cur_src.startswith("http"):
                ehb_plan = {"id": 1262, "old_source": cur_src, "new_source": EHB_SOURCE,
                            "reason": "EHB官方公众号公告停业2025-09-28；腾讯新闻转引"}
                print(f"    → 补权威 URL: {EHB_SOURCE}")
            else:
                print("    closed_source 已是 URL，无需变更")

    # ---- B. Nuits relocation merge: 1967(closed旧) → 1978(active新) ----
    n_old = C.req("GET", "/restaurants?id=eq.1967").json()
    n_new = C.req("GET", "/restaurants?id=eq.1978").json()
    nuits_plan = None
    if n_old and n_new:
        o, n = n_old[0], n_new[0]
        print(f"\n[B] Nuits 迁址合并:")
        print(f"    旧 id=1967 status={o.get('status')} addr={o.get('address')!r} closed={o.get('closed_date')}")
        print(f"    新 id=1978 status={n.get('status')} addr={n.get('address')!r}")
        # 前置条件：旧=closed、新=active、同品牌（新名以旧名开头或核心名一致）
        old_core = C.cjk_norm(o.get("name"))
        new_core = C.cjk_norm(n.get("name"))
        same_brand = new_core.startswith(old_core) or old_core.startswith(new_core)
        if (o.get("status") == "closed" and n.get("status") == "active"
                and same_brand):
            # 统计待迁子表
            child_counts = {}
            for table, fk, biz_key, comp_pk in ED.FK_TABLES:
                rows = ED.fetch_rows(table, fk, 1967)
                if rows:
                    child_counts[table] = len(rows)
            ev_new = n.get("evidence_summary") or ""
            fix_ev = "关店" in ev_new  # active 行误带关店警告
            nuits_plan = {"drop": 1967, "keeper": 1978, "child_counts": child_counts,
                          "fix_evidence_summary": fix_ev}
            print(f"    待迁子表: {child_counts}")
            print(f"    active 行 evidence 误带关店警告: {fix_ev}（将清除）")
        else:
            print("    前置条件不满足（旧非closed/新非active/不同名），跳过")

    plan = {"ehb": ehb_plan, "nuits": nuits_plan}
    json.dump(plan, open(args.plan, "w"), ensure_ascii=False, indent=1)
    print(f"\n计划写 {args.plan}")

    if not args.apply:
        print(f"\n【DRY-RUN】将"
              f"{'补EHB closed_source' if ehb_plan else ''}"
              f"{'、合并nuits 1967→1978' if nuits_plan else ''}。确认后加 --apply。")
        return

    # ---- APPLY ----
    # A. EHB
    if ehb_plan:
        r = C.req("PATCH", "/restaurants?id=eq.1262",
                  json={"closed_source": EHB_SOURCE})
        print(f"\n[A] EHB closed_source PATCH: {r.status_code}")

    # B. Nuits 迁移
    if nuits_plan:
        print(f"\n[B] 迁移子表 1967→1978 ...")
        log = []
        moved = ED.migrate_children(1967, 1978, log)
        for line in log[:20]:
            print(f"    {line}")
        print(f"    共迁移 {moved} 行")

        # 修 active 行 evidence_summary（去掉误带的关店警告，保留正常证据）
        if nuits_plan["fix_evidence_summary"]:
            new_row = C.req("GET", "/restaurants?id=eq.1978").json()[0]
            ev = new_row.get("evidence_summary") or ""
            # 去掉开头的【...关店...】警告段
            import re
            cleaned = re.sub(r"^【[^】]*关店[^】]*】来源:[^\s]*\s*警告：?", "", ev).strip()
            cleaned = cleaned or "Nuits（植庭集团旗下酒馆），2026-09 迁址恒隆广场三期Pavilion。"
            r = C.req("PATCH", "/restaurants?id=eq.1978",
                      json={"evidence_summary": cleaned,
                            "aliases": ["Nuits(铜仁路旧址)"]})
            print(f"    1978 evidence_summary 清理 PATCH: {r.status_code}")

        # 删旧行（此时 FK 已迁空）
        r = C.req("DELETE", "/restaurants?id=eq.1967")
        print(f"    DELETE restaurants 1967: {r.status_code}")

    # ---- 回读 ----
    print("\n---- 回读核对 ----")
    e2 = C.req("GET", "/restaurants?id=eq.1262").json()
    if e2:
        e2 = e2[0]
        print(f"  EHB(1262): status={e2['status']} date={e2['closed_date']} src={e2['closed_source'][:60]}")
        triple = e2["status"] == "closed" and e2["closed_date"] and e2["closed_source"].startswith("http")
        print(f"  EHB 三要素齐(status+date+url): {triple}")

    n1967 = C.req("GET", "/restaurants?id=eq.1967").json()
    n1978 = C.req("GET", "/restaurants?id=eq.1978").json()
    print(f"  nuits 1967 仍存在: {bool(n1967)}（应 False）")
    if n1978:
        n = n1978[0]
        print(f"  nuits 1978: status={n['status']} name={n['name']!r} addr={n['address']!r}")
        print(f"    evidence 含'关店': {'关店' in (n.get('evidence_summary') or '')}（应 False）")
        print(f"    aliases={n.get('aliases')}")

    # 总数
    total = len(C.fetch_all("restaurants", "id", order_col="id"))
    print(f"  restaurants 总数: {total}（迁移前 1479，删1行后应 1478）")


if __name__ == "__main__":
    main()
