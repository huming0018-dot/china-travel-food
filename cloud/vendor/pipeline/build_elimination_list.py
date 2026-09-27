#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 negative_elimination_list.md — 出清清单（软标记，非物理删除）。"""
import collections
import pathlib
import sys

import common as C

OUT = pathlib.Path(
    "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/social/negative_elimination_list.md"
)


def main():
    rs = C.fetch_all(
        "restaurants",
        "id,name,status,chain_type,central_kitchen,premade_risk,review_count,"
        "score_total,review_confidence,soft_ad_flag,soft_ad_penalty,"
        "is_chain_standardized,price_avg,district,price_scene",
        order_col="id",
    )
    act = [r for r in rs if r["status"] == "active"]

    # 分类桶
    by_chain = []       # 大型/资本化连锁
    by_ck = []          # central_kitchen=确认
    by_premade = []     # premade_risk=高
    by_softad = []      # soft_ad_flag=confirmed（品牌软广）
    by_lowqual = []     # score<55 & review=0（无真实口碑低质量）
    by_suspected_chain = []  # soft_ad=suspected 但非 lowqual（连锁/预制嫌疑）

    for r in act:
        ct = r.get("chain_type") or ""
        ck = r.get("central_kitchen") or ""
        pr = r.get("premade_risk") or ""
        sf = r.get("soft_ad_flag") or "none"
        rc = r.get("review_count") or 0
        st = r.get("score_total") or 0

        is_big_chain = ct in ("大型连锁", "资本化连锁")
        is_ck_confirmed = ck == "确认"
        is_premade_high = pr == "高"
        is_softad_confirmed = sf == "confirmed"
        is_lowqual = rc == 0 and st < 55

        if is_lowqual:
            by_lowqual.append(r)
        if is_big_chain:
            by_chain.append(r)
        if is_ck_confirmed:
            by_ck.append(r)
        if is_premade_high:
            by_premade.append(r)
        if is_softad_confirmed:
            by_softad.append(r)
        if sf == "suspected" and not is_lowqual:
            by_suspected_chain.append(r)

    # 写 Markdown
    lines = []
    lines.append("# 上海美食图鉴 — 负面清单与出清记录（软标记，非物理删除）")
    lines.append("")
    lines.append(f"> 生成日期：{C.today()} ｜ 审计脚本：`scripts/food_pipeline/chain_audit.py` + `negative_audit.py`")
    lines.append(">")
    lines.append("> **最高原则**：只收真正好吃、食客真实堂食口碑出色的店；系统性对抗软广/预制菜/资本化连锁。")
    lines.append("> **出清方式**：一律软标记（`chain_type/central_kitchen/premade_risk` 标签 + `soft_ad_flag/soft_ad_penalty` 评分降级 + `is_chain_standardized` 前端可隐藏）。**禁止物理删除，保留可恢复。**")
    lines.append("")
    lines.append("## 1. 总览统计")
    lines.append("")
    lines.append("| 分类 | 数量 | 标记方式 |")
    lines.append("|---|---|---|")
    lines.append(f"| 资本化/大型连锁 | {len(by_chain)} | chain_type + 前端隐藏 |")
    lines.append(f"| 中央厨房确认 | {len(by_ck)} | central_kitchen=确认 |")
    lines.append(f"| 预制菜高风险 | {len(by_premade)} | premade_risk=高 |")
    lines.append(f"| 软广硬广确认 | {len(by_softad)} | soft_ad_flag=confirmed, penalty=25 |")
    lines.append(f"| 软广嫌疑（连锁/预制） | {len(by_suspected_chain)} | soft_ad_flag=suspected, penalty=10 |")
    lines.append(f"| 无真实口碑低质量（score<55 & review=0） | {len(by_lowqual)} | soft_ad_flag=suspected, penalty=20, 评分下沉 |")
    total_marked = len({r['id'] for r in by_chain + by_ck + by_premade + by_softad + by_lowqual})
    lines.append(f"| **被软标记店铺合计（去重）** | **{total_marked}** | |")
    lines.append("")
    lines.append(f"- active 店铺总数：{len(act)}")
    lines.append(f"- 可被前端「隐藏连锁/预制」开关过滤（is_chain_standardized=true）：{sum(1 for r in act if r['is_chain_standardized'])}")
    lines.append(f"- soft_ad_flag=suspected：{sum(1 for r in act if r['soft_ad_flag']=='suspected')}")
    lines.append(f"- soft_ad_flag=confirmed：{sum(1 for r in act if r['soft_ad_flag']=='confirmed')}")
    lines.append("")

    def render_table(title, rows, cols):
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| id | 店名 | 区 | 人均 | score | review | chain_type | ck | premade | soft_ad | penalty |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(rows, key=lambda x: x["id"]):
            lines.append(
                f"| {r['id']} | {r['name']} | {r.get('district') or ''} | "
                f"{r.get('price_avg') or ''} | {r.get('score_total') or ''} | "
                f"{r.get('review_count') or 0} | {r.get('chain_type') or ''} | "
                f"{r.get('central_kitchen') or ''} | {r.get('premade_risk') or ''} | "
                f"{r.get('soft_ad_flag') or 'none'} | {r.get('soft_ad_penalty') or 0} |"
            )
        lines.append("")

    render_table(f"2. 资本化/大型连锁清单（{len(by_chain)}家）", by_chain, None)
    render_table(f"3. 中央厨房确认清单（{len(by_ck)}家）", by_ck, None)
    render_table(f"4. 预制菜高风险清单（{len(by_premade)}家）", by_premade, None)
    render_table(f"5. 软广硬广确认清单（{len(by_softad)}家，penalty=25）", by_softad, None)
    render_table(f"6. 无真实口碑低质量待出清清单（{len(by_lowqual)}家，score<55 & review=0）", by_lowqual, None)

    # 同名异址连锁分店保留说明
    lines.append("## 7. 同名异址连锁分店保留说明")
    lines.append("")
    lines.append("- 连锁分店**不合并、不物理删除**，每家分店作为独立实体保留（id 不同、地址不同）。")
    lines.append("- 同品牌多分店统一打 `chain_type` / `central_kitchen` / `premade_risk` 标签，前端「隐藏连锁」开关可一键过滤。")
    lines.append("- **例外保留**：高端餐饮集团（新荣记/大董/甬府/鲁采/荣府宴）虽为多店，但 `central_kitchen=无`、`premade_risk=无`、`is_chain_standardized=false`，不惩罚、可进精选。")
    lines.append("- **例外下沉**：小型连锁中 `premade_risk=低/疑似` 的（如桂满陇、左庭右院）打 `central_kitchen=疑似`，可隐藏；`premade_risk=无` 的同城现做多店保留。")
    lines.append("")

    # 重复店说明
    lines.append("## 8. 倾向合并的重复店")
    lines.append("")
    lines.append("- 本轮审计未发现新的同址重复店（`merge_duplicates.py` 历史已处理）。")
    lines.append("- 同名异址（如「新荣记」南京西路店/BFC店/前滩店/虹桥店/滨江店）为合法多店，保留不合并。")
    lines.append("")

    # 规则说明
    lines.append("## 9. 本轮新增规则（negative_audit.py）")
    lines.append("")
    lines.append("| 规则 | 触发条件 | 软标记动作 |")
    lines.append("|---|---|---|")
    lines.append("| R1 小型连锁 ck 补全 | chain_type=小型连锁 且 ck=NULL | pr=低/疑似→ck=疑似；pr=无→ck=无 |")
    lines.append("| R2 预制品牌扩充词表 | 店名命中 PREMADE_EXTRA（费大厨/新白鹿/丸龟/鲜芋仙等） | chain_type/ck/pr 标签 + standardized 自动推导 |")
    lines.append("| R3 低质量无口碑店 | review_count=0 且 score_total<55 | soft_ad_flag=suspected, penalty≥20 |")
    lines.append("| R4 连锁未标 soft_ad | 大型/资本化连锁但 soft_ad_flag=none | soft_ad_flag=suspected, penalty=10 |")
    lines.append("")
    lines.append("**关键教训**：`is_chain_standardized` 是 Postgres **generated column**，不能直接 PATCH（报错 428C9）；需通过更新 `chain_type/central_kitchen/premade_risk/soft_ad_flag` 让 DB 自动推导。")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"已写: {OUT}")
    print(f"总标记去重: {total_marked}")
    print(f"  连锁: {len(by_chain)}, 中央厨房确认: {len(by_ck)}, 预制高: {len(by_premade)},")
    print(f"  软广确认: {len(by_softad)}, 软广嫌疑: {len(by_suspected_chain)}, 低质量无口碑: {len(by_lowqual)}")


if __name__ == "__main__":
    main()
