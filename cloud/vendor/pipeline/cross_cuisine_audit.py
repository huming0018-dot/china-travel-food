#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cross_cuisine_audit.py — 跨菜系根误挂检测与清理（常驻质量门）。

治"多代理写库标签 id 错位"：子代理各自 stage2/写库时 id 映射错位，会把京菜/韩餐/
粤菜/法餐等菜系根随机挂到外国餐厅（土耳其店挂京菜、越南粉挂粤菜、泰餐挂法餐）。

规则：
- 菜系根 = parent_category ∈ 四大虚拟根 的标签；一家 active 店去掉"天然跨菜系场景根"
  (融合/咖啡甜品/酒吧) 后，地域菜系根应只有 1 个；≥2 即误挂。
- 主根判定（高置信自动，否则 needs_manual）：①店名国别关键词唯一命中；②唯一挂细叶子。
默认 dry-run；--commit 才 DELETE（service key，期望204），逐笔幂等。
注意：真实融合店（如川粤为底的现代中餐）多根属合理，列人工后保留，勿误删。
"""
import sys, os, argparse, json, pathlib, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa

ZONE = ("中餐", "亚洲", "欧洲", "非洲", "北美洲", "南美洲", "融合菜", "非正餐")
# 豁免根：非正餐五枝（咖啡/面包/甜品/Bar/茶饮，非地域菜系，与正餐出身根不冲突）
SCENE_ROOTS = {"咖啡", "面包", "甜品", "Bar", "茶饮", "融合菜/Fusion"}
# 泛指洲标签：与更具体国别/菜系并列时，优先保留具体项、删泛指
GENERIC_ROOTS = {"非洲菜", "亚洲菜", "欧洲菜", "北美洲菜", "南美洲菜", "西餐", "其他"}

ROOT_KW = {
 "鲁菜": ["鲁菜","济南","胶东","孔府","鲅鱼","山东","鲁采","博山"],
 "川菜": ["川菜","蜀","川味","自贡","盐帮","江湖菜","重庆","成都","麻婆","回锅","水煮","串串","冒菜","麻辣烫","宜宾","泸州","内江","绵阳","辣子","毛血旺","酸菜鱼","烤鱼"],
 "粤菜": ["粤菜","广府","广州","潮汕","潮州","汕头","客家","顺德","港式","香港","茶餐厅","烧腊","烧鹅","叉烧","早茶","点心","打冷","生腌","砂锅粥","肠粉","菠萝油","啫啫","煲仔饭","老火","卤鹅","猪肚鸡"],
 "苏菜": ["苏菜","淮扬","扬州","金陵","苏帮","苏州","无锡","锡菜","徐海","徐州","狮子头","干丝","盐水鸭","松鼠","鳝糊"],
 "浙菜": ["浙菜","杭帮","杭州","西湖","宁波","绍兴","温州","台州","金华","新荣记","荣府","甬府","年糕","黄酒","霉干菜","瓯菜"],
 "闽菜": ["闽菜","福州","佛跳墙","闽南","厦门","泉州","沙茶面","海蛎","土笋","姜母鸭","莆田","莆仙","闽北","遇外滩"],
 "湘菜": ["湘菜","长沙","剁椒","常德","钵子","湘西","洞庭","辣椒炒肉","腊味"],
 "徽菜": ["徽菜","徽州","黄山","臭鳜鱼","毛豆腐","皖南","皖江","皖北","刀板香","问政"],
 "本帮菜": ["本帮","上海菜","老上海","浓油赤酱","生煎","小笼"],
 "京菜": ["京菜","北京","烤鸭","炙子","胡同"],
 "东北菜": ["东北","铁锅炖","锅包肉"],
 "西北菜": ["西北","兰州","西安","陕西","泡馍","凉皮","肉夹馍"],
 "新疆菜": ["新疆","乌鲁木齐","大盘鸡","馕","抓饭"],
 "西南菜": ["西南","云南","过桥米线","菌子","傣","贵州","酸汤鱼"],
 "台湾菜": ["台湾","台菜","台式"],
 "海南菜": ["海南","椰子鸡","糟粕醋","文昌"],
 "青藏菜": ["青藏","藏餐","拉萨","青稞","酥油","牦牛肉"],
 "广西菜": ["广西","螺蛳粉","桂林米粉","柳州"],
 "江西菜": ["江西","瓦罐","南昌","炒粉"],
 "河南菜": ["河南","洛阳","水席","胡辣汤"],
 "湖北菜": ["湖北","武汉","热干面","藕汤"],
 "内蒙古菜": ["内蒙古","蒙古包","烤全羊","烤羊","手把肉"],
 "韩餐": ["韩餐","韩国","korea","korean","首尔","釜山","部队","参鸡","酱蟹","泡菜","石锅"],
 "泰餐": ["泰餐","泰国","thai","曼谷","清迈","冬阴功","芒果"],
 "越餐": ["越餐","越南","viet","pho","saigon","西贡","banh mi"],
 "新马印": ["马来","新加坡","印尼","巴东","叻沙","laksa","肉骨茶","椰浆饭","nasi"],
 "印度菜": ["印度","indian","punjab","bombay","tandoor","rangoli","naan"],
 "中东/阿拉伯菜": ["中东","阿拉伯","土耳其","turkish","kebab","falafel","黎巴嫩","lebanon","efes","pasha","habibi","otantik","黎凡特","shawarma","波斯"],
 "中亚菜": ["中亚","乌兹别克","撒马尔罕","格鲁吉亚","khachapuri","哈萨克"],
 "日料/日本料理": ["日料","日本","寿司","sushi","拉面","ramen","烧鸟","yakitori","居酒屋","izakaya","鳗","天妇罗","乌冬","荞麦","omakase","割烹","怀石","洋食","猪排","丼","蔵","monta","麺"],
 "法餐": ["法餐","法国","french","chez","joel","robuchon","polux","jojo","lenotre","gateau","lafay","lefebvre","phenix","斐霓丝"],
 "意餐": ["意餐","意大利","ital","osteria","trattoria","pizzeria","giovanni"],
 "西班牙菜": ["西班牙","spain","tapas","tomatito","bodegon","albaluz"],
 "德餐": ["德餐","德国","german"],
 "俄餐": ["俄餐","俄罗斯","russia","俄士","罗宋","乌克兰","kiev","kirill"],
 "美餐": ["美餐","美式","american","burger","beef liberty","wolfgang"],
 "地中海/希腊菜": ["地中海","希腊","greek","taverna","milos","mezze"],
 "英国菜": ["英国菜","英式","brit"],
 "北欧菜": ["北欧","nordic","瑞典","sweden"],
 "墨西哥/拉美菜": ["墨西哥","mexico","agave","cantina","taco"],
 "非洲菜": ["非洲","ethiopia","moroccan","摩洛哥"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("-o", "--output", default="cross_cuisine_report.md")
    args = ap.parse_args()

    cuis = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    byid = {c["id"]: c for c in cuis}

    def root_of(cid):
        cur, seen = cid, set()
        while cur is not None:
            c = byid.get(cur)
            if not c or c["dimension"] != "菜系":
                return None
            p = c.get("parent_category")
            if p in ZONE:
                return c["name"]
            nxt = next((z["id"] for z in cuis if z["name"] == p and z["dimension"] == "菜系"), None)
            if not nxt or nxt in seen:
                return c["name"]
            seen.add(nxt); cur = nxt
        return None

    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    rests = {r["id"]: r for r in C.fetch_all("restaurants", "id,name,status", order_col="id")}
    rr = collections.defaultdict(lambda: collections.defaultdict(list))
    for x in rc:
        rt = root_of(x["cuisine_id"])
        if rt:
            rr[x["restaurant_id"]][rt].append(x["cuisine_id"])

    plan, manual = [], []
    for rid, rootmap in rr.items():
        r = rests.get(rid)
        if not r or r.get("status") == C.STATUS_CLOSED:
            continue
        geo = {k: v for k, v in rootmap.items() if k not in SCENE_ROOTS}
        if len(geo) < 2:
            continue
        low = r["name"].lower()
        kw_hit = {rt for rt in geo for kw in ROOT_KW.get(rt, []) if kw.lower() in low}
        leaf_roots = {rt for rt, cids in geo.items() if any(byid[c]["name"] != rt for c in cids)}

        generic = [rt for rt in geo if rt in GENERIC_ROOTS]
        specific = [rt for rt in geo if rt not in GENERIC_ROOTS]
        # 泛指根在有具体根时先删
        pre_dels = [(c, rt) for rt in generic for c in geo[rt]] if specific else []

        primary, basis, conf = None, None, None
        pool = specific if specific else list(geo)
        kws = [x for x in kw_hit if x in pool]
        lvs = [x for x in leaf_roots if x in pool]
        if len(pool) == 1 and pre_dels:
            primary, basis, conf = pool[0], "删泛指留具体", "high"
        elif len(set(kws)) == 1:
            primary, basis, conf = kws[0], "店名关键词", "high"
        elif len(set(lvs)) == 1:
            primary, basis, conf = lvs[0], "唯一细叶子", "medium"

        if primary:
            dels = list(pre_dels)
            for rt, cids in geo.items():
                if rt != primary:
                    for c in cids:
                        if (c, rt) not in dels:
                            dels.append((c, rt))
            plan.append({"rid": rid, "name": r["name"], "primary": primary, "basis": basis,
                         "conf": conf, "roots": sorted(geo), "dels": dels})
        else:
            manual.append({"rid": rid, "name": r["name"], "roots": sorted(geo),
                           "kw_hit": sorted(kw_hit), "leaf_roots": sorted(leaf_roots),
                           "pre_dels": pre_dels})

    print(f"自动判定 {len(plan)} 家 | 需人工 {len(manual)} 家 | 待删关联 {sum(len(p['dels']) for p in plan)} 笔")
    L = ["# 跨菜系根误挂检测报告", "",
         f"自动判定 **{len(plan)}** / 需人工 **{len(manual)}** / 待删 **{sum(len(p['dels']) for p in plan)}** 笔", "",
         "## 一、自动判定（dry-run 不删）", ""]
    for p in sorted(plan, key=lambda x: x["rid"]):
        L.append(f"- id{p['rid']} {p['name']} → 主根**{p['primary']}**({p['basis']},{p['conf']})；"
                 f"所挂{p['roots']}；将删 {[rt for _, rt in p['dels']]}")
    L += ["", "## 二、需人工裁决", ""]
    for m in manual:
        L.append(f"- id{m['rid']} {m['name']}: 根{m['roots']} 店名命中{m['kw_hit']} 细叶根{m['leaf_roots']}")
    rep = "\n".join(L); print(rep)
    pathlib.Path(args.output).write_text(rep, encoding="utf-8")
    pathlib.Path(args.output.replace(".md", ".json")).write_text(
        json.dumps({"plan": plan, "manual": manual}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.commit:
        print("\n【DRY-RUN】确认判定无误后加 --commit 删除（人工项不在自动范围）。"); return
    ok = fail = 0
    for p in plan:
        for cid, rt in p["dels"]:
            d = C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{p['rid']}&cuisine_id=eq.{cid}")
            if d.status_code == 204: ok += 1
            else: fail += 1; print(f"DELETE fail rid{p['rid']} cid{cid}: {d.status_code} {d.text[:120]}")
    print(f"\n删除 {ok} 笔 / 失败 {fail}；人工 {len(manual)} 家需单独裁决。")


if __name__ == "__main__":
    main()
