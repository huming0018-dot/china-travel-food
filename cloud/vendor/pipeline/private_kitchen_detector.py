#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
private_kitchen_detector.py — Part B: 私房菜识别器

判定对象：所有餐厅。输出每店 (private_score, marketing_score, label, reasons)。
- private_score 高 = 真私厨（预约制/家庭厨房/居民楼/无招牌/小桌板前/主厨个人）
- marketing_score 高 = 营销"私房"（公开门面/连锁/商场店/大众点评可walk-in）

判定完全基于库内已有字段（name / address / booking_method / evidence_summary /
chain_type / price_avg / tier），不依赖实时抓点评。规则确定性、可复核。

用法：
  python3 private_kitchen_detector.py            # 全量扫描，写 private_kitchen_report.json
  python3 private_kitchen_detector.py --review   # 只看当前已挂私房菜(348)+名字带私房的店
"""
import sys, json, re, pathlib
import common as C

# ---------------- 真私厨正信号（命中加分）----------------
PRIVATE_SIGNALS = [
    # 预约/无菜单/按位
    (r"无固定菜单|没有固定菜单|无菜单|按.{0,4}配菜|按时令|按位|按人头|按人数|上什么吃什么|omakase|Omakase|主厨餐桌|chef'?s? ?table|板前", 2),
    (r"提前\d+[天周月]|需提前|极难(订|约)|很难(订|约)|约不上|只接?预约|仅(限)?预约|全预约制|只做套餐|不零点", 2),
    (r"微信(预约|订位|订座)|熟客(介绍|预约)|介绍预约|invite.?only|不接待walk.?in|不接待walkin", 2),
    # 空间小/无门面/居民楼里弄
    (r"居民楼|里弄|弄堂|小区内|无招牌|没?有?招牌|敲门|按门铃|藏(?:在|于|进|身)|隐藏|隐蔽|具体地址?预约(时|后)?告知|预约(时|后)?告知", 2),
    (r"仅?\d+\s*(?:个|张|席|座|桌)[座位桌席]|只(开|做)[一两]桌|每天(只|仅)|每日(只|仅)|仅\d+席|仅\d+座|仅\d+桌", 2),
    # 主厨个人/家庭厨房起家
    (r"老板(自己|一人|亲自|掌勺|主厨)|主厨(个人|主理|露脸|不露脸)|家庭厨房|自家厨房|一户|小食堂", 1),
]
# ---------------- 营销私房负信号（命中加 marketing 分，或削弱 private）----------------
MARKETING_SIGNALS = [
    (r"连锁|集团|品牌升级|首店|旗舰店|分店|路店|购物中心|商场|广场|商务楼|写字楼|大酒店|饭店内|酒店\s*\d*楼", 2),
    (r"大众点评(可|能)?(订|约|排队)|携程(可|能)?(订|约)|可walk.?in|walk.?in|大厅|散台|散点|对外开放|营业中.*点评", 1),
    (r"全(部)?包?间|整层|多包间|可容\d+|容纳\d+人", 1),  # 大空间宴请 ≠ 家庭私厨
]
# 名字带"私房/私宴/家宴/会馆"但需结合信号判断
NAME_PRIVATE = re.compile(r"私房|私厨|私宴|家宴|私宅")
NAME_MARKETING = re.compile(r"会馆|会所|宴会厅|大酒店|酒店|大饭店")


def score_shop(shop: dict) -> dict:
    text = " ".join([
        str(shop.get("name") or ""),
        str(shop.get("address") or ""),
        str(shop.get("booking_method") or ""),
        str(shop.get("evidence_summary") or ""),
    ])
    priv, mkt, reasons = 0, 0, []
    for pat, w in PRIVATE_SIGNALS:
        m = re.search(pat, text)
        if m:
            priv += w
            reasons.append(f"私厨+{w}:{m.group(0)[:20]}")
    for pat, w in MARKETING_SIGNALS:
        m = re.search(pat, text)
        if m:
            mkt += w
            reasons.append(f"营销+{w}:{m.group(0)[:20]}")
    if NAME_PRIVATE.search(str(shop.get("name") or "")):
        priv += 1; reasons.append("店名含私厨词")
    if NAME_MARKETING.search(str(shop.get("name") or "")):
        mkt += 1; reasons.append("店名含宴请空间词")
    if shop.get("chain_type") and "连锁" in str(shop.get("chain_type")):
        mkt += 2; reasons.append("连锁品牌")
    # 判定
    if priv - mkt >= 3 and priv >= 3:
        label = "真私厨"
    elif priv - mkt <= -1 and mkt >= 2:
        label = "营销私房"
    else:
        label = "待人工"
    return {"private_score": priv, "marketing_score": mkt, "label": label, "reasons": reasons}


def main():
    review_only = "--review" in sys.argv
    print("拉取餐厅 ...")
    shops = C.fetch_all('restaurants',
                        select='id,name,address,booking_method,evidence_summary,chain_type,price_avg,tier,status',
                        order_col='id')
    # 当前已挂私房菜(348)的店
    rc = C.fetch_all('restaurant_cuisines', select='restaurant_id,cuisine_id', order_col='restaurant_id')
    private_now = {l['restaurant_id'] for l in rc if l['cuisine_id'] == 348}

    rows = []
    for s in shops:
        sc = score_shop(s)
        rows.append({
            "id": s["id"], "name": s["name"], "status": s.get("status"),
            "price_avg": s.get("price_avg"), "chain_type": s.get("chain_type"),
            "current_private_link": s["id"] in private_now, **sc,
        })

    if review_only:
        # 重点：已挂私房菜的 + 名字带私房的
        focus = [r for r in rows if r["current_private_link"] or NAME_PRIVATE.search(r["name"] or "")]
        focus.sort(key=lambda r: -(r["private_score"] - r["marketing_score"]))
        print(f"=== 已挂私房菜/名字带私厨 共 {len(focus)} 家 ===")
        for r in focus:
            print(f"[{r['label']}] priv={r['private_score']} mkt={r['marketing_score']} "
                  f"linked={r['current_private_link']} id={r['id']} {r['name']}")
            print("    ", "; ".join(r["reasons"][:5]))
    else:
        from collections import Counter
        cnt = Counter(r["label"] for r in rows)
        print("全量扫描:", dict(cnt))
        out = pathlib.Path(__file__).parent / "private_kitchen_report.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print("写出", out)


if __name__ == "__main__":
    main()
