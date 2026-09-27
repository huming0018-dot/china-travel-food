#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
signature_dish_classifier.py — Part C: 招牌菜→品类 语义匹配 + 全盘错分扫描

核心原则：
1. 不能只看店名（"茶楼"≠茶馆）；以 signature_dishes + evidence_summary 为主，name 为辅。
2. 多标签：一家店可同时命中"烘焙"+"中式茶饮"（如裕莲茶楼）。
3. 宁空不假：信号弱/冲突 → 标"待人工"，不强行改。
4. 只输出推荐与置信度，默认 dry-run；不自动写库（写库走单独脚本 + 备份）。

用法：
  python3 signature_dish_classifier.py              # 全量扫描，输出 mismatch_report.json
  python3 signature_dish_classifier.py --spot 1739  # 单店调试
"""
import sys, json, re, pathlib
from collections import defaultdict
import common as C

# ------------------------------------------------------------------
# 关键词 → cuisine_id 规则。cuisine_id 来自库内 cuisines 表（见 build()）。
# 每条: (正则, cuisine_id 名, 强度)。强度>=2 视为强信号。
# 店名命中权重 *0.5，招牌菜/证据命中权重 *1。
# ------------------------------------------------------------------
def build_rules():
    return [
        # --- 烘焙 / 蛋挞 / 面包 ---
        (r"蛋挞|可颂|牛角包|脏包|贝果|司康|肉桂卷|吐司|欧包|酸种|面包|烘焙|酥皮|可丽露|费南雪|玛德琳|蛋糕", "面包/烘焙", 2),
        (r"甜品|甜点|蛋糕|法式甜品|巴斯克|提拉米苏|舒芙蕾|马卡龙|慕斯", "甜品", 2),
        (r"冰淇淋|gelato|Gelato|雪芭|雪葩|刨冰", "冰淇淋Gelato", 1),
        # --- 中式茶饮 / 奶茶 ---
        (r"奶茶|奶绿|果茶|鲜果茶|柠檬茶|珍珠|乌龙奶茶|茶钻|琥珀奶|中式茶饮|新中式茶", "茶饮", 2),
        (r"普洱|岩茶|龙井|碧螺春|铁观音|大红袍|点茶|茶艺|茶室|茶馆", "茶馆/茶室", 1),
        # --- 咖啡 ---
        (r"手冲|拿铁|澳白|Dirty|dirty|espresso|咖啡豆|自烘|美式咖啡|拿铁咖啡|flat white", "咖啡", 2),
        # --- 酒 / 酒吧 ---
        (r"鸡尾酒|调酒|whisky|威士忌|精酿|啤酒吧|自然酒|wine bar|小酒馆|bistro|Bistro", "Bar", 1),
        # --- 日料细分 ---
        (r"寿司|omakase|Omakase|板前|江户前", "寿司", 2),
        (r"烧鸟|烧鸟串|烤鸡串", "烧鸟", 2),
        (r"拉面|豚骨|蘸面|沾面", "拉面", 2),
        (r"怀石|会席|京料理", "怀石", 2),
        (r"天妇罗|天ぷら", "天妇罗", 2),
        (r"鳗鱼|鳗鱼饭|鳗丼", "鳗鱼饭", 2),
        # --- 中餐细分 ---
        (r"烤鸭|北京烤鸭|片皮鸭", "北京烤鸭", 2),
        (r"生煎", "生煎", 2),
        (r"小笼|小笼包|汤包", "小笼包", 2),
        (r"馄饨|云吞", "馄饨", 2),
        (r"饺子|锅贴", "饺子", 2),
        (r"叉烧|烧腊|烧鹅|卤味|酱鸭|糟货", "烧腊/卤味", 2),
        (r"早茶|点心|虾饺|烧卖|凤爪|流沙包", "港式茶餐厅/冰室", 1),
        (r"火锅|涮肉|涮羊肉|串串|麻辣烫|冒菜|猪肚鸡|椰子鸡", "火锅/锅物", 2),
        (r"烧烤|烤串|烤肉|居酒屋烧|BBQ", "烧烤/烤串", 2),
        (r"牛肉面|兰州拉面|面馆|牛肉面", "兰州牛肉面", 1),
        (r"米线|米粉|螺蛳粉|桂林米粉", "柳州螺蛳粉", 1),
        # --- 西餐/快餐细分 ---
        (r"汉堡", "汉堡", 2),
        (r"炸鸡", "炸鸡", 2),
        (r"披萨|比萨|pizza|Pizza", "那不勒斯披萨", 2),
        (r"意面|pasta|Pasta| carbonara", "意面", 2),
        (r"牛排|战斧|t骨|T骨|dry.?aged", "美式牛排", 2),
        (r"早午餐|brunch|Brunch|班尼迪克", "早午餐 Brunch", 2),
    ]


def load_cuisine_map():
    rows = C.fetch_all('cuisines', select='id,name,dimension', order_col='id')
    return {r['name']: r['id'] for r in rows}, rows


def classify_shop(shop, cname2id, rules):
    name = str(shop.get("name") or "")
    sig = shop.get("signature_dishes") or []
    sig_text = " ".join(sig) if isinstance(sig, list) else str(sig)
    ev = str(shop.get("evidence_summary") or "")
    # 招牌菜/证据是强信号源；店名是弱信号
    hits = defaultdict(float)
    why = defaultdict(list)
    for pat, cname, strength in rules:
        cid = cname2id.get(cname)
        if not cid:
            continue
        if re.search(pat, sig_text):
            hits[cid] += strength
            why[cid].append(f"招牌菜:{re.search(pat, sig_text).group(0)}")
        if re.search(pat, ev):
            hits[cid] += strength * 0.5
            why[cid].append("证据")
        if re.search(pat, name):
            hits[cid] += strength * 0.3
            why[cid].append(f"店名:{re.search(pat, name).group(0)}")
    return hits, why


def main():
    cname2id, cuis = load_cuisine_map()
    rules = build_rules()
    # 校验规则里引用的 cuisine 名都存在
    missing = [c for _, c, _ in rules if c not in cname2id]
    if missing:
        print("警告: 规则引用了不存在的 cuisine 名:", missing)

    shops = C.fetch_all('restaurants',
                        select='id,name,signature_dishes,evidence_summary,price_scene',
                        order_col='id')
    rc = C.fetch_all('restaurant_cuisines', select='restaurant_id,cuisine_id', order_col='restaurant_id')
    by_shop = defaultdict(set)
    for l in rc:
        by_shop[l['restaurant_id']].add(l['cuisine_id'])
    id2name = {c['id']: c['name'] for c in cuis}

    spot = None
    if "--spot" in sys.argv:
        spot = int(sys.argv[sys.argv.index("--spot") + 1])

    mismatches = []
    for s in shops:
        sid = s['id']
        hits, why = classify_shop(s, cname2id, rules)
        if not hits:
            continue
        current = by_shop.get(sid, set())
        # 推荐分类：强度>=2 的强信号
        recs = {cid: sc for cid, sc in hits.items() if sc >= 2}
        if not recs:
            continue
        # 缺失：强信号命中但当前没挂
        missing_links = {cid: sc for cid, sc in recs.items() if cid not in current}
        if spot:
            if sid == spot:
                print(f"=== {sid} {s['name']} ===")
                print("招牌菜:", s.get("signature_dishes"))
                print("当前分类:", [id2name.get(c) for c in current])
                for cid, sc in sorted(recs.items(), key=lambda x: -x[1]):
                    mark = "  [缺]" if cid in missing_links else "  [已有]"
                    print(f"  {mark} {id2name.get(cid)} (score={sc}) {why[cid][:3]}")
            continue
        if missing_links:
            mismatches.append({
                "id": sid, "name": s["name"],
                "current": sorted(id2name.get(c, str(c)) for c in current),
                "missing_recs": sorted(
                    [{"cuisine": id2name.get(c), "cuisine_id": c, "score": round(sc, 1),
                      "why": why[c][:4]} for c, sc in missing_links.items()],
                    key=lambda x: -x["score"]),
            })

    if spot:
        return
    mismatches.sort(key=lambda r: -max(m["score"] for m in r["missing_recs"]))
    out = pathlib.Path(__file__).parent / "mismatch_report.json"
    out.write_text(json.dumps(mismatches, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"扫描 {len(shops)} 家，发现 {len(mismatches)} 家存在招牌菜信号缺失/错分")
    print("Top 20 缺分类强信号：")
    for r in mismatches[:20]:
        top = r["missing_recs"][0]
        print(f"  id={r['id']} {r['name'][:24]:24s} -> 缺[{top['cuisine']}] score={top['score']} 现挂={r['current'][:3]}")


if __name__ == "__main__":
    main()
