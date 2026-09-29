#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recalc_scores.py — 按 v3 公式重算餐厅总分，修复89家公式不符

公式（与 stage1_validate.py / DB trigger 005 一致）：
  total = round(max(0, 0.35*score_taste + 0.25*score_objective + 0.25*score_diner + 0.15*score_endorsement - score_softad_penalty), 1)

仅更新分项齐全且与库中 score_total 偏差>0.15 的记录。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'vendor', 'pipeline'))
import common as C

def calc(taste, obj, diner, endo, pen):
    if taste is None or obj is None or diner is None or endo is None:
        return None
    pen = pen or 0
    return round(max(0, 0.35*taste + 0.25*obj + 0.25*diner + 0.15*endo - pen), 1)

def main():
    rows = C.fetch_all('restaurants',
        'id,name,score_taste,score_objective,score_diner,score_endorsement,soft_ad_penalty,score_total,status',
        order_col='id')
    active = [r for r in rows if r.get('status') == 'active']
    mismatches, fixed, skipped = [], 0, 0

    for r in active:
        expected = calc(r.get('score_taste'), r.get('score_objective'),
                        r.get('score_diner'), r.get('score_endorsement'),
                        r.get('soft_ad_penalty'))
        if expected is None:
            skipped += 1
            continue
        actual = r.get('score_total')
        if actual is None or abs(actual - expected) > 0.15:
            mismatches.append((r['id'], r['name'], actual, expected))

    print(f"在营餐厅: {len(active)}, 分项不全跳过: {skipped}, 公式不符: {len(mismatches)}")
    if not mismatches:
        print("无需修复")
        return

    print("\n前10条不符:")
    for rid, name, actual, expected in mismatches[:10]:
        print(f"  #{rid} {name}: 库中={actual} 应为={expected}")

    # 执行更新
    for rid, name, actual, expected in mismatches:
        r = C.req('PATCH', f'/restaurants?id=eq.{rid}',
                  json={'score_total': expected})
        if r.status_code == 200:
            fixed += 1
        else:
            print(f"  更新失败 #{rid}: {r.status_code} {r.text[:100]}")

    print(f"\n已修复: {fixed}/{len(mismatches)}")

if __name__ == '__main__':
    main()
