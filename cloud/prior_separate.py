#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prior_separate.py — 启发式先验 / 证据列 物理分离（migration 024 配套回写器）。

解决什么问题
  restaurants.central_kitchen='疑似' / premade_risk='低' 中大量是 chain_audit
  按连锁档位批量推的【启发式先验】（无逐店 source_url），却被硬门 reconcile.py /
  评分 curate_v4.py 当证据消费。本脚本把这些「纯先验」搬到 *_prior 列，证据列回置
  '无'，让硬门只看到真正有证据的标签。

判定（逐行、逐字段独立）
  证据命中 = fact_claims 里存在同 type 且带 source_url 的主张，
             或 /app/data/post_record/findings*.jsonl 里有 (rid, field) 且带 source_url。
  * central_kitchen:
      - '确认'            -> 硬证据，永远跳过（PROTECTED）
      - '疑似' 且无证据   -> 纯先验：搬值到 central_kitchen_prior，证据列回置 '无'
      - '疑似' 且有证据   -> 保留证据值（EVIDENCE 桶），不动
      - '无'              -> 不动
  * premade_risk:
      - '高'              -> 硬证据，永远跳过（PROTECTED）
      - '低'   且无证据   -> 纯先验：搬值到 premade_prior，证据列回置 '无'
      - '低'   且有证据   -> 保留证据值（EVIDENCE 桶），不动
      - '疑似'/'无'       -> 不在本轮清理范围（'疑似' 由 negative_audit 候选封顶产生，
                             保持原样，仅计入未处理统计）

幂等
  已分离行（对应 *_prior 非空，或证据列已回置 '无'）自动跳过、不重复搬、不覆盖已有 prior。

--apply 闸门
  默认 dry-run，只打印分类计数与样例、绝不写库。
  --apply 前先探测 024 的 *_prior 列是否存在；列不存在则中止并提示先执行 024。

用法（容器内）：
  . /app/cloud/env.sh
  python3 -u cloud/prior_separate.py              # dry-run
  python3 -u cloud/prior_separate.py --apply      # 仅在 024 已执行后
"""
import argparse
import glob
import json
import os
import pathlib
import sys
import collections

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), "/app/pipeline", "/app/cloud"):
    if p not in sys.path:
        sys.path.insert(0, p)
import common as C  # noqa: E402

# 回写时给纯先验打的低置信（启发式，非取证）
PRIOR_CONFIDENCE = 0.30
PRIOR_PROVENANCE = "heuristic"

# 本轮清理目标桶（证据列当前值）
CK_TARGET = "疑似"      # central_kitchen
PR_TARGET = "低"        # premade_risk
# 永久保护的硬证据值
CK_PROTECTED = "确认"
PR_PROTECTED = "高"

FIELD_TO_PRIOR_COL = {"central_kitchen": "central_kitchen_prior",
                      "premade_risk": "premade_prior"}


# ---------------------------------------------------------------------------
# 证据账本：findings*.jsonl（逐店搜索证据，容器内 /app/data/post_record/）
# ---------------------------------------------------------------------------
def load_findings_evidence():
    """返回 {(rid, field): [source_url, ...]}，只收带 source_url 的逐店证据。"""
    data_dir = os.environ.get("FOOD_DATA_DIR", "/app/data")
    ledger = pathlib.Path(data_dir) / "post_record"
    ev = collections.defaultdict(list)
    files = sorted(glob.glob(str(ledger / "findings*.jsonl")))
    n_lines = 0
    for f in files:
        try:
            for line in pathlib.Path(f).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid, field = d.get("restaurant_id"), d.get("field")
                url = (d.get("source_url") or "").strip()
                if rid is not None and field and url:
                    ev[(rid, field)].append(url)
                    n_lines += 1
        except OSError:
            continue
    return ev, files, n_lines


def claim_evidence(fact_claims, ctype):
    """fact_claims 里同 type 且带 source_url 的主张。"""
    if not isinstance(fact_claims, list):
        return []
    out = []
    for c in fact_claims:
        if not isinstance(c, dict):
            continue
        if c.get("type") == ctype and (c.get("source_url") or "").strip():
            out.append(c.get("source_url"))
    return out


def evidence_for(r, field, findings_ev):
    """合并 DB fact_claims 与 findings 账本的逐店/品牌证据 URL 列表。"""
    urls = claim_evidence(r.get("fact_claims"), field)
    urls += findings_ev.get((r["id"], field), [])
    return urls


# ---------------------------------------------------------------------------
# 列存在性探测（--apply 闸门）
# ---------------------------------------------------------------------------
def prior_columns_exist():
    try:
        C.req("GET", "/restaurants?select=id,central_kitchen_prior,premade_prior&limit=1").raise_for_status()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build_plan():
    findings_ev, ffiles, nlines = load_findings_evidence()
    # 探测 024 的 *_prior 列是否存在。列不存在（migration 024 未执行）时，
    # dry-run 仍要能跑通拿分类计数：select 不带 prior 列，"已迁移"桶视为空。
    # --apply 路径在 main() 末尾另有独立硬门，此处不影响。
    prior_present = prior_columns_exist()
    sel = ("id,name,status,chain_type,central_kitchen,premade_risk,fact_claims")
    if prior_present:
        sel += ",central_kitchen_prior,premade_prior"
    rests = C.fetch_all("restaurants", sel, order_col="id")

    plan = []           # 待回写：{id,name,patch}
    buckets = collections.Counter()
    samples = collections.defaultdict(list)

    def grab(key, r, extra=""):
        buckets[key] += 1
        if len(samples[key]) < 8:
            samples[key].append((r["id"], r.get("name"),
                                 r.get("chain_type"), extra))

    for r in rests:
        rid = r["id"]
        ck = r.get("central_kitchen")
        pr = r.get("premade_risk")
        # 列不存在时视为未迁移（None），不会进入 already_migrated 桶。
        ck_prior_col = r.get("central_kitchen_prior") if prior_present else None
        pr_prior_col = r.get("premade_prior") if prior_present else None

        patch = {}

        # ---- central_kitchen ----
        ck_urls = evidence_for(r, "central_kitchen", findings_ev)
        if ck == CK_PROTECTED:
            grab("ck_protected_确认", r, "硬证据保护")
        elif ck == CK_TARGET:
            if ck_urls:
                grab("ck_evidence_保留", r, f"证据×{len(ck_urls)}")
            elif ck_prior_col not in (None, ""):
                grab("ck_already_migrated", r, f"prior={ck_prior_col}")
            else:
                grab("ck_pure_prior_搬移", r, f"{ck}->prior")
                patch["central_kitchen_prior"] = ck
                patch["central_kitchen"] = "无"
        # else '无'/NULL：不动

        # ---- premade_risk ----
        pr_urls = evidence_for(r, "premade_risk", findings_ev)
        if pr == PR_PROTECTED:
            grab("pr_protected_高", r, "硬证据保护")
        elif pr == PR_TARGET:
            if pr_urls:
                grab("pr_evidence_保留", r, f"证据×{len(pr_urls)}")
            elif pr_prior_col not in (None, ""):
                grab("pr_already_migrated", r, f"prior={pr_prior_col}")
            else:
                grab("pr_pure_prior_搬移", r, f"{pr}->prior")
                patch["premade_prior"] = pr
                patch["premade_risk"] = "无"
        elif pr == "疑似":
            grab("pr_疑似_不在本轮", r, "negative候选封顶，保持原样")

        if patch:
            patch["prior_provenance"] = PRIOR_PROVENANCE
            patch["prior_confidence"] = PRIOR_CONFIDENCE
            plan.append({"id": rid, "name": r.get("name"), "patch": patch})

    return rests, plan, buckets, samples, (ffiles, nlines), findings_ev, prior_present


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="真正写库（默认 dry-run）。仅在 migration 024 已执行后可用。")
    ap.add_argument("--show", type=int, default=8, help="每桶打印样例数")
    args = ap.parse_args()

    rests, plan, buckets, samples, (ffiles, nlines), findings_ev, prior_present = build_plan()

    print("=" * 64)
    print(f"prior_separate  {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 64)
    print(f"024 *_prior 列存在? {prior_present}"
          + ("" if prior_present else "（列不存在：select 不带 prior 列，已迁移桶视为空；"
                                     "--apply 仍会在下方硬门中止）"))
    print(f"门店总数（拉取）: {len(rests)}")
    print(f"findings 账本文件: {len(ffiles)} 个 / {nlines} 条带 source_url 行")
    print("-" * 64)
    print("分类计数：")
    for k in sorted(buckets):
        print(f"  {k:28s} {buckets[k]}")
    print("-" * 64)
    print(f"待回写行数（合并后）: {len(plan)}")

    if samples:
        print("-" * 64)
        print("样例（每桶至多展示）：")
        for k in sorted(samples):
            print(f"  [{k}]")
            for rid, name, ct, extra in samples[k][:args.show]:
                print(f"     id={rid:<6} {ct or '-':<8} {str(name)[:28]:<28} {extra}")

    # ---- --apply 闸门 ----
    if not args.apply:
        print("-" * 64)
        print("[dry-run] 未写任何数据。核对计数/样例后：")
        print("  1) 确认已在 SQL Editor 执行 db/migrations/024_prior_evidence_separation.sql")
        print("  2) 再加 --apply 回写。")
        return

    if not prior_columns_exist():
        sys.exit("✖ 中止：检测不到 *_prior 列。请先在 Supabase SQL Editor 执行 "
                 "db/migrations/024_prior_evidence_separation.sql 后再 --apply。")

    if not plan:
        print("无待回写（已全部分离，幂等）。")
        return

    print("-" * 64)
    print(f"开始 --apply 回写 {len(plan)} 行 ...")
    ok, fail = 0, 0
    for x in plan:
        try:
            r = C.req("PATCH", f"/restaurants?id=eq.{x['id']}", json=x["patch"])
            r.raise_for_status()
            # 写后回读校验
            got = C.fetch_all(
                "restaurants",
                "id,central_kitchen,premade_risk,central_kitchen_prior,premade_prior",
                extra=f"id=eq.{x['id']}")
            ok += 1
            print(f"  ✓ id={x['id']} {str(x['name'])[:24]} -> {json.dumps(x['patch'], ensure_ascii=False)}")
        except Exception as e:
            fail += 1
            print(f"  ✗ id={x['id']} 失败: {e}")
    print("-" * 64)
    print(f"完成：成功 {ok}，失败 {fail}。")


if __name__ == "__main__":
    main()
