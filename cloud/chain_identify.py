#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chain_identify.py — #37 连锁识别自动化：品牌归一 + 多店判别。

两条腿：
  1) 库内（确定性、免费）：把店名归一到「品牌核心」（去分店括号、取 · 前品牌段、
     去标点空白小写），同品牌核心在库 ≥2 家即判连锁（2–9 小型 / ≥10 大型），
     把其中仍标「独立店/空」的成员升级，资本化连锁不覆盖、不做降级。
  2) 库外（点评分店数）：由既有 dianping_enrich/dianping_daily 管线持续补，
     本脚本只负责库内可确定性识别的部分。
保守：品牌核心过短/过泛（如「面馆/火锅/咖啡」）不合并，避免误伤。
用法：python3 chain_identify.py [--apply]
"""
import argparse, json, re, sys, collections
sys.path.insert(0, "/app/cloud")
import common_core as CC

GENERIC = {"面馆","拉面","火锅","咖啡","烤肉","烧肉","寿司","甜品","面包","蛋糕","茶楼",
           "餐厅","饭店","小吃","烧烤","咖喱","奶茶","酒吧","食堂","厨房","点心","早餐",
           "快餐","小炒","茶饮","简餐","料理","菜馆","食府","酒楼","酒家"}


def norm(s):
    return re.sub(r"[\s\W_]+", "", (s or "").lower(), flags=re.UNICODE)


def brand_core(name):
    s = re.split(r"[（(]", name)[0]          # 去分店括号
    s = re.split(r"[·・]", s)[0]             # 取 · 前品牌段
    s = re.sub(r"(分店|总店|旗舰店|店)$", "", s.strip())
    return s.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rests = CC.fetch_all("restaurants", "id,name,chain_type,status", order_col="id")
    groups = collections.defaultdict(list)
    for r in rests:
        core = brand_core(r["name"])
        k = norm(core)
        if len(k) >= 3 and k not in GENERIC:
            groups[(k, core)].append(r)

    upgrades, report = 0, []
    for (k, core), members in sorted(groups.items(), key=lambda x: -len(x[1])):
        n = len(members)
        if n < 2:
            continue
        target = "大型连锁" if n >= 10 else "小型连锁"
        todo = [m for m in members
                if (m.get("chain_type") in (None, "独立店")) ]
        if not todo:
            continue
        report.append({"brand": core, "n_in_db": n, "target": target,
                       "upgrade_ids": [m["id"] for m in todo],
                       "names": [m["name"] for m in members][:12]})
        for m in todo:
            upgrades += 1
            if args.apply:
                CC.req("PATCH", f"/restaurants?id=eq.{m['id']}",
                       json={"chain_type": target}, use_service=True)

    with open("/app/data/chain_identify_groups.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"品牌组数(库内≥2)：{len(report)}；待升级门店：{upgrades}")
    for g in report[:15]:
        print(f"  {g['brand'][:20]:<22} n={g['n_in_db']:<3} -> {g['target']} "
              f"升级{len(g['upgrade_ids'])}")
    print("模式：", "APPLY" if args.apply else "dry-run")


if __name__ == "__main__":
    main()
