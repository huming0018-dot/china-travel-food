#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flatten_ingredients.py — 食材维度扁平化 / 同名食材叶子合并（常驻实体对齐）。

背景：食材维度回答"吃什么（面 / 饭 / 肉 / 海鲜…）"，应是用户认知的扁平标签集合。
历史采集把"面"按 中式汤面 / 日式面 / 亚洲其他面 拆成 3 个同名叶子（id 51/52/53），
"饭"拆成 57/58/59。前端选"面"只命中其中一个（241 家中式面），漏掉日式拉面、
亚洲面店；同名多叶也让食材行重复。"什么风味/流派"已由【菜系】维度承载，食材
维度再按系分组属冗余，故合并同名、扁平化（parent_category=None）。

规则：
  MERGE 中 keep 为保留叶子，merges 为待合并删除叶子：
    1) 挂 merge 但未挂 keep 的店 → 补挂 keep（RC，期望201/409）；
    2) 删除该店与 merge 的关联（期望204）；
    3) 全部迁完后删除 merge 标签本身（期望204）；
  4) 所有 dimension=食材 标签 parent_category 置 None（食材扁平、无分组行）。
默认 dry-run；--commit 才写，逐笔幂等，可安全重跑。

注意：合并只在【食材】维度内做；菜系/形式标签不受影响。
"""
import sys, os, argparse, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa

# (keep, [merges...])
MERGE = [
    (51, [52, 53]),   # 面
    (57, [58, 59]),   # 饭
]


def load():
    cuis = C.fetch_all("cuisines", "id,name,dimension,parent_category")
    byid = {c["id"]: c for c in cuis}
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    hold = collections.defaultdict(set)
    for x in rc:
        hold[x["restaurant_id"]].add(x["cuisine_id"])
    return byid, hold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    byid, hold = load()

    plan = []
    for keep, merges in MERGE:
        for m in merges:
            for rid, tags in hold.items():
                if m in tags:
                    plan.append((rid, keep, m, keep not in tags))
    add = [p for p in plan if p[3]]
    print(f"待迁移 RC {len(plan)} 笔（其中需补挂 keep 的 {len(add)} 笔）；"
          f"待删食材标签 {sum(len(m) for _, m in MERGE)} 个")
    for keep, merges in MERGE:
        for m in merges:
            print(f"  {byid[m]['name']} id{m} (parent={byid[m]['parent_category']}) "
                  f"-> 并入 id{keep}")

    if not args.commit:
        print("\n[dry-run] 确认后加 --commit 执行")
        return

    add_n = del_rc = fail = 0
    for rid, keep, m, need_add in plan:
        if need_add:
            r = C.req("POST", "/restaurant_cuisines",
                      json={"restaurant_id": rid, "cuisine_id": keep})
            if r.status_code in (201, 409):
                add_n += 1
            else:
                fail += 1
                print(f"ADD fail rid{rid} keep{keep}: {r.status_code} {r.text[:100]}")
            time.sleep(0.08)
        d = C.req("DELETE",
                  f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{m}")
        if d.status_code == 204:
            del_rc += 1
        else:
            fail += 1
            print(f"DEL RC fail rid{rid} m{m}: {d.status_code} {d.text[:100]}")
    print(f"RC 迁移：补挂 {add_n} / 删除 {del_rc} / 失败 {fail}")

    # 删除已清空的 merge 标签
    for keep, merges in MERGE:
        for m in merges:
            left = C.req("GET",
                         f"/restaurant_cuisines?cuisine_id=eq.{m}&select=restaurant_id")
            if left.json():
                print(f"标签 {m} 仍有 {len(left.json())} 关联，跳过删除")
                continue
            d = C.req("DELETE", f"/cuisines?id=eq.{m}")
            print(f"删除食材标签 {m}: {d.status_code}")

    # 扁平化：所有食材标签 parent_category=None
    ing = C.fetch_all("cuisines", "id,name,dimension,parent_category")
    nflat = 0
    for c in ing:
        if c["dimension"] == "食材" and c["parent_category"] is not None:
            r = C.req("PATCH", f"/cuisines?id=eq.{c['id']}",
                      json={"parent_category": None})
            if r.status_code in (200, 204):
                nflat += 1
            else:
                print(f"FLAT fail id{c['id']}: {r.status_code} {r.text[:100]}")
    print(f"食材标签扁平化 {nflat} 个；完成。")


if __name__ == "__main__":
    main()
