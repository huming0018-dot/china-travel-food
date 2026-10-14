#!/usr/bin/env python3
"""Track 1B-2 保鲜/关店/迁址（只读复核计划；写入已禁用）。

历史上做两件经权威源核证的事：
  A. EHB(id=1262) closed_source 由文本备注改为权威新闻 URL（三要素已齐，补可溯源）。
  B. Nuits 迁址合并：旧铜仁路(id=1967, closed) → 新恒隆三期Pavilion(id=1978, active)。
     同一家店迁址（非连锁分店），先迁全部子表 FK 再删旧行，去重首页双显。

安全边界（2026-10-14 修复 F01/F02）：
  本文件现在只产出【只读复核计划】，不再执行任何写操作：
  - CLI --apply 在任何数据库读取/网络/写盘前立即拒绝（非零退出）；
  - 迁址合并依赖 entity_dedup.migrate_children（已无条件抛错，import 也无法绕过）；
  - 若确需保留 A（EHB 补 closed_source），必须拆成【独立、明确、可审计】的命令单独执行，
    不得与“迁址合并”共用同一个 --apply 授权；
  - 迁址合并（B）属实体删除/迁移，必须等带数据库事务的执行器就位。

关店/迁址无权威源不臆造；电话宁空不假；不猜分店。
"""
import sys, os, json, hashlib, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import entity_dedup as ED

DATA = "/app/data"

# 权威源（≥2 独立媒体一致，2025-09-28 停业）
EHB_SOURCE = "https://view.inews.qq.com/a/20251017A07FWU00"  # 腾讯新闻，转引EHB官方公众号公告
NUITS_CLOSED_SRC = "https://guide.michelin.com/cn/zh_CN/shanghai-region/shanghai/restaurants/nuits"
NUITS_NEW_SRC = "https://m.jfdaily.com/wx/detail.do?id=1180886"  # 上观：恒隆三期Pavilion 2026-09-22启幕

# 写入口统一拒绝：补来源(A) 与 迁址合并(B) 都不再由本脚本 --apply 执行。
WRITE_DISABLED = (
    "closed_relocate writes disabled: this script emits a read-only review plan only. "
    "EHB closed_source backfill (if retained) must be a separate explicit command; "
    "relocation merge/delete requires a transactional executor. See F01/F02."
)


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

    # F01/F02：任何写/合并/删除入口在【任何数据库读取/网络/文件写入之前】无条件拒绝。
    if args.apply:
        ap.error(WRITE_DISABLED)  # SystemExit code 2

    print("==== Track1B-2 关店/迁址【只读复核 REVIEW_ONLY】====")

    # ---- A. EHB closed_source URL（只读判定，仅生成提案）----
    ehb = C.req("GET", "/restaurants?id=eq.1262").json()
    ehb_plan = None
    if ehb:
        e = ehb[0]
        cur_src = e.get("closed_source") or ""
        print(f"\n[A] EHB(1262): status={e.get('status')} closed_date={e.get('closed_date')}")
        print(f"    当前 closed_source={cur_src[:80]!r}")
        if e.get("status") == "closed" and e.get("closed_date"):
            # 已是 URL 则跳过；文本备注则补权威 URL
            if not cur_src.startswith("http"):
                ehb_plan = {"id": 1262, "old_source": cur_src, "new_source": EHB_SOURCE,
                            "reason": "EHB官方公众号公告停业2025-09-28；腾讯新闻转引",
                            "action": "PROPOSED_SEPARATE_COMMAND_ONLY"}
                print(f"    → 提案补权威 URL（不自动执行，须独立命令）: {EHB_SOURCE}")
            else:
                print("    closed_source 已是 URL，无需变更")

    # ---- B. Nuits relocation merge: 1967(closed旧) → 1978(active新)（只读预估）----
    n_old = C.req("GET", "/restaurants?id=eq.1967").json()
    n_new = C.req("GET", "/restaurants?id=eq.1978").json()
    nuits_plan = None
    if n_old and n_new:
        o, n = n_old[0], n_new[0]
        print(f"\n[B] Nuits 迁址合并（仅候选，不执行）:")
        print(f"    旧 id=1967 status={o.get('status')} addr={o.get('address')!r} closed={o.get('closed_date')}")
        print(f"    新 id=1978 status={n.get('status')} addr={n.get('address')!r}")
        # 前置条件：旧=closed、新=active、同品牌（新名以旧名开头或核心名一致）
        old_core = C.cjk_norm(o.get("name"))
        new_core = C.cjk_norm(n.get("name"))
        same_brand = new_core.startswith(old_core) or old_core.startswith(new_core)
        if (o.get("status") == "closed" and n.get("status") == "active"
                and same_brand):
            # 统计待迁子表（只读 GET）
            child_counts = {}
            for table, fk, biz_key, comp_pk in ED.FK_TABLES:
                rows = ED.fetch_rows(table, fk, 1967)
                if rows:
                    child_counts[table] = len(rows)
            ev_new = n.get("evidence_summary") or ""
            fix_ev = "关店" in ev_new  # active 行误带关店警告
            nuits_plan = {"drop": 1967, "keeper": 1978, "child_counts": child_counts,
                          "fix_evidence_summary": fix_ev,
                          "action": "PROPOSED_NEEDS_TRANSACTIONAL_EXECUTOR"}
            print(f"    待迁子表: {child_counts}")
            print(f"    active 行 evidence 误带关店警告: {fix_ev}（候选清理，不自动执行）")
        else:
            print("    前置条件不满足（旧非closed/新非active/不同名），跳过")

    plan = {"status": "REVIEW_ONLY", "executable": False, "write_disabled": WRITE_DISABLED,
            "ehb": ehb_plan, "nuits": nuits_plan}
    json.dump(plan, open(args.plan, "w"), ensure_ascii=False, indent=1)
    print(f"\n只读计划写 {args.plan}（REVIEW_ONLY，不可直接执行）")
    print(f"\n【REVIEW_ONLY】候选："
          f"{'补EHB closed_source（须独立命令）' if ehb_plan else ''}"
          f"{'、合并nuits 1967→1978（须事务执行器）' if nuits_plan else ''}。")
    print("历史 --apply 已禁用（F01/F02），不做任何写入/迁址/删除。")


if __name__ == "__main__":
    main()
