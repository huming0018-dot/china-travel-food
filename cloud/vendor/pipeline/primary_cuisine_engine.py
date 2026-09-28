#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
primary_cuisine_engine.py — Phase 0-B 分类机制重做：主营(is) vs 含有(serves) 确定性引擎。

对每家 active 餐厅，在其**现有** dimension='菜系' 关联中确定性选出唯一主菜系叶
（is_primary=true），其余菜系关联一律 serves（is_primary=false）。

设计原则（对齐 north-star A1/A2/A3/A6 + cuisine-classification-engine.md + mechanism-master P3）：
1. 主营出品定类：主菜系 = 门店主营出品对应的菜系叶；菜单"也做/点缀"的出品只作次标签(serves)。
   —— 不因为"菜单出现某菜"就新增 link；本引擎只在既有菜系关联里选主，不增删 link。
2. 中餐：地域子流派(identity)优先于产品/形式第二轴(format)。例：潮汕牛肉火锅店主菜系=潮汕菜，
   潮汕牛肉火锅=次(serves)；松鹤楼主=苏帮菜，苏式汤面=次。多地域子流派并存时，按招牌菜/食客证据裁决。
3. 日料/西餐/非正餐（无地域子流派）：按主营出品证据在产品叶中选主。例：鮨琉璃主=寿司；酉町主=烧鸟。
4. 地名陷阱：店名/地址里的地名 token（扬州/四川/重庆/温州/潮汕/海南…）只作弱信号(0.1)，
   须招牌菜/食客证据佐证才采纳；名字带地名、主营另一菜系时，证据纠正之（记录拦截/纠正案例）。
5. 覆盖保护：不推翻人工已设的 leaf primary——仅高置信+招牌菜反证时才改；root→leaf 可提升。
6. 只 UPDATE restaurant_cuisines.is_primary；不增删 link、不动 restaurants/cuisines 任何其他字段。

用法：
  python3 primary_cuisine_engine.py                 # dry-run，落 before→after 报告
  python3 primary_cuisine_engine.py --commit         # 写库（PATCH is_primary）+ 回读
  python3 primary_cuisine_engine.py --snapshot FILE  # 离线迭代（读快照，不联网）
"""
import argparse, collections, json, pathlib
import common as C

ZONES = {"中餐", "亚洲", "欧洲", "非洲", "北美洲", "南美洲", "融合菜", "非正餐"}

# 产品/形式第二轴叶（format）：与地域子流派(identity)并存时，identity 为主、format 为次。
# 仅含：①中餐双轴的14个品类叶(355-368)；②日料/西餐/非正餐的产品叶（这些根下无地域子流派，按证据选主）。
# 注意：北京烤鸭/武汉过早/兰州牛肉面/新疆手抓饭等"无根下地域子流派的产品叶"不放入此集合——
#       它们在该根下是合法主叶候选，应由招牌菜证据裁决（否则会把热干面店错判成藕汤店）。
FORMAT_LEAF_NAMES = {
    # 中餐双轴第二轴（品类/店型，355-368）
    "重庆火锅", "串串香/冷锅串", "冒菜/麻辣烫", "川味面馆", "烤鱼/酸菜鱼专门",
    "广式早茶点心", "潮汕牛肉火锅", "潮汕打冷/生腌排档", "砂锅粥/粿条",
    "苏式汤面", "淮扬茶社/细点", "胶东海饺/面点", "闽菜Fine Dining", "湖南米粉",
    # 日料产品/形式（无地域子流派）
    "寿司", "烧鸟", "烧肉", "拉面", "咖喱", "天妇罗", "鳗鱼饭", "寿喜烧",
    "铁板烧", "炉端烧", "居酒屋", "怀石", "日式甜品", "日式洋食", "乌冬", "荞麦",
    "Omakase 板前",
    # 西餐产品/形式（无地域子流派）
    "法餐Fine Dining", "可颂甜品", "法式Bistro", "那不勒斯披萨", "意面", "Osteria",
    "佛罗伦萨牛排", "Tapas", "海鲜饭", "伊比利亚火腿", "猪肘香肠啤酒", "红菜汤",
    "俄式西餐", "大列巴", "美式牛排", "汉堡", "BBQ烧烤", "炸鸡", "Diner美式简餐",
    "英式早餐", "Fish&Chips", "新北欧料理", "北欧海鲜",
    "维也纳炸猪排", "维也纳烤肋排/皇帝松饼", "比利时啤酒/华夫饼", "比利时青口贝/薯条",
    "摩洛哥塔吉锅正餐", "Couscous库斯库斯", "南非正餐/烤肉", "Bobotie马来风味派",
    "Tex-Mex", "创意Taco/Quesadilla", "巴西烤肉Churrasco自助", "巴西烤牛舌/烤菠萝",
    "阿根廷Asado炭烤牛排", "Empanada馅饼/Chimichurri",
    "秘鲁国菜Ceviche酸橘汁腌鱼", "秘鲁-西班牙融合菜",
    # 非正餐产品叶（咖啡/面包/甜品/Bar/茶饮，无地域子流派）
    "创意特调咖啡", "手冲/自烘豆专门", "社区精品咖啡", "连锁咖啡",
    "可颂/起酥专门", "日式面包", "社区烘焙坊", "贝果专门", "酸种面包专门",
    "冰淇淋Gelato", "刨冰", "松饼/薄饼", "糖水/甜汤", "蛋糕/法式甜品", "铜锣烧/和果子",
    "威士忌吧", "精酿啤酒吧", "葡萄酒/自然酒吧", "鸡尾酒吧",
    "新中式茶饮", "奶茶专门店", "港式奶茶·茶室", "茶饮",
}

# 地名 token（弱信号，权重 0.1；不得仅凭此定主菜系）
PLACE_TOKENS = [
    "扬州", "江苏", "四川", "重庆", "温州", "潮汕", "潮州", "汕头", "海南", "兰州",
    "台湾", "台北", "内江", "泸州", "宜宾", "绵阳", "湖南", "长沙", "常德", "湘西",
    "安徽", "徽州", "黄山", "济南", "胶东", "烟台", "威海", "青岛", "宁波", "绍兴",
    "台州", "金华", "福州", "厦门", "泉州", "莆田", "闽南", "北京", "东北",
    "新疆", "云南", "贵州", "西安", "陕西", "河南", "湖北", "武汉", "内蒙", "蒙古",
    "高丽", "韩国", "日本", "越南", "泰国", "印度", "土耳其", "摩洛哥", "皖北", "皖江",
]

# 店名业态词（强信号，权重 0.5）
PRODUCT_NAME_WORDS = {
    "寿司": ["寿司", "鮨", "sushi", "omakase", "板前"],
    "烧鸟": ["烧鸟", "yakitori"],
    "天妇罗": ["天妇罗", "tempura"],
    "怀石": ["怀石", "会席", "割烹"],
    "居酒屋": ["居酒屋", "izakaya"],
    "乌冬": ["乌冬", "udon"],
    "荞麦": ["荞麦", "soba"],
    "鳗鱼饭": ["鳗鱼", "unagi"],
    "汉堡": ["汉堡", "burger"],
    "炸鸡": ["炸鸡", "fried chicken"],
    "美式牛排": ["牛排", "steak", "战斧"],
    "意面": ["意面", "pasta"],
    "那不勒斯披萨": ["披萨", "pizza"],
    "咖啡": ["咖啡", "coffee", "手冲", "espresso", "roaster"],
    "面包": ["面包", "bakery", "烘焙", "可颂", "croissant", "贝果", "酸种", "sourdough"],
    "甜品": ["甜品", "蛋糕", "dessert", "cake"],
    "酒吧": ["bar", "酒吧", "威士忌", "whisky", "自然酒", "wine", "精酿"],
    "茶饮": ["奶茶", "茶饮", "tea"],
}

# 招牌菜/证据 → 菜系叶关键词（多叶裁决用）
LEAF_DISH_KW = {
    "自贡盐帮菜": ["水煮牛肉", "冷吃兔", "冷吃", "鲜锅兔", "跳水兔", "自贡", "盐帮"],
    "江湖菜": ["辣子鸡", "毛血旺", "来凤鱼", "璧山兔", "江湖", "芋儿", "肥肠鸡"],
    "官府菜/蓉派川菜": ["开水白菜", "麻婆豆腐", "宫保鸡丁", "夫妻肺片", "蓉派", "官府"],
    "渝菜": ["火锅", "重庆", "渝", "毛肚", "鸭肠", "九宫格", "小面"],
    "成都家常菜/苍蝇馆子": ["豆瓣鱼", "蒜泥白肉", "家常", "苍蝇馆子"],
    "川南·宜宾菜": ["燃面", "宜宾", "把把烧", "李庄"],
    "川南·内江菜": ["内江", "甜城"],
    "川南·泸州菜": ["泸州", "白糕"],
    "川北·绵阳菜": ["绵阳", "米粉", "肥肠面"],
    "新派川菜": ["新派", "创意川", "现代川", "干烧岩鲤", "藿香"],
    "海派改良川菜": ["海派", "改良川"],
    "广府菜(广州)": ["白切鸡", "烧鹅", "老火汤", "老火靓汤", "清蒸鱼", "广府", "广州"],
    "潮汕菜": ["卤鹅", "生腌", "打冷", "蚝烙", "潮汕", "潮州", "汕头", "粿条", "鱼饭",
               "鱼生", "薄壳", "虾生", "卤水", "牛丸"],
    "顺德菜": ["顺德", "鱼生", "双皮奶", "均安", "凤城"],
    "客家菜": ["客家", "盐焗鸡", "酿豆腐", "梅菜扣肉", "猪肚鸡"],
    "港式茶餐厅/冰室": ["菠萝油", "丝袜奶茶", "蛋治", "干炒牛河", "茶餐厅", "冰室", "港式"],
    "淮扬菜": ["狮子头", "大煮干丝", "文思豆腐", "淮扬", "扬州", "镇江", "肴肉"],
    "金陵菜": ["盐水鸭", "金陵", "南京", "鸭血粉丝"],
    "苏帮菜": ["松鼠鳜鱼", "响油鳝糊", "苏帮", "苏州", "碧螺虾仁", "松鼠桂鱼"],
    "锡菜": ["无锡", "锡菜", "酱排骨", "油面筋"],
    "徐海菜": ["徐州", "地锅鸡", "把子肉", "烙馍"],
    "济南菜": ["济南", "糖醋鲤鱼", "九转大肠", "葱烧海参"],
    "胶东菜": ["胶东", "烟台", "威海", "青岛", "鲅鱼", "海胆", "海鲜"],
    "孔府菜": ["孔府", "诗礼银杏", "孔"],
    "杭帮菜": ["西湖醋鱼", "东坡肉", "龙井虾仁", "杭帮", "杭州", "叫花鸡"],
    "宁波菜": ["宁波", "冰糖甲鱼", "雪菜", "黄鱼", "年糕", "汤团"],
    "绍兴菜": ["绍兴", "霉干菜", "黄酒", "醉鸡", "糟"],
    "温州菜": ["温州", "瓯菜", "鱼丸", "敲鱼"],
    "台州菜": ["台州", "新荣记", "荣府", "家烧"],
    "福州菜": ["福州", "佛跳墙", "荔枝肉", "醉糟鸡", "鸡汤汆海蚌"],
    "闽南菜": ["厦门", "泉州", "沙茶", "海蛎煎", "姜母鸭", "土笋", "萝卜饭", "炸醋肉"],
    "莆仙菜": ["莆田", "莆仙", "卤面", "仙游"],
    "闽北菜": ["武夷山", "闽北", "熏鹅", "建瓯"],
    "长沙菜": ["长沙", "剁椒鱼头", "小炒黄牛肉", "辣椒炒肉", "口味虾", "爆炒"],
    "洞庭湖区菜": ["常德", "洞庭", "钵子菜", "河鲜", "岳阳", "鱼头"],
    "湘西菜": ["湘西", "酸汤", "腊味", "腊肉", "怀化", "张家界"],
    "徽州菜": ["臭鳜鱼", "毛豆腐", "徽州", "黄山", "刀板香", "问政山笋", "呈坎"],
    "皖江菜": ["芜湖", "安庆", "蟹黄汤包", "板鸭"],
    "皖北菜": ["蚌埠", "宿州", "牛肉汤", "太和板面", "皖北"],
    "本帮菜": ["本帮", "上海菜", "浓油赤酱", "生煎", "响油鳝丝", "草头"],
    "本帮浓油赤酱老字号": ["本帮", "老字号", "烟鲳鱼", "焖蹄", "焖肉", "八宝鸭", "油爆虾"],
    "上海家常": ["家常", "上海"],
    "海派融合": ["海派", "融合", "舒芙蕾", "鸭肝"],
    "京味家常": ["京味", "炸酱面", "爆肚", "北京菜"],
    "宫廷官府菜": ["宫廷", "官府", "御"],
    "西安菜(正餐/泡馍/葫芦鸡)": ["泡馍", "葫芦鸡", "葫芦头", "羊肉水盆"],
    "陕西小吃(肉夹馍/凉皮/油泼面)": ["肉夹馍", "凉皮", "油泼面", "米皮"],
    "云南菜": ["过桥米线", "菌子", "云南", "傣", "汽锅鸡"],
    "贵州菜": ["酸汤鱼", "贵州", "丝娃娃", "肠旺面"],
    "新疆正餐": ["大盘鸡", "新疆", "烤羊肉"],
    "东北家常菜": ["东北", "锅包肉", "地三鲜"],
    "东北铁锅炖": ["铁锅炖", "东北炖"],
    "东北饺子馆": ["东北饺子"],
    "东北菜高端": ["东北", "高端"],
    "湖北家常菜馆·藕汤": ["藕汤", "莲藕", "藕夹", "粉蒸肉", "湖北", "洪山菜薹"],
    "湖北菜高端·宴请": ["武昌鱼", "洪山菜薹", "高端", "宴请"],
    "武汉过早·热干面小吃": ["热干面", "豆皮", "蛋酒", "面窝", "过早", "糊汤粉"],
    "北京烤鸭": ["烤鸭", "片皮鸭", "挂炉"],
    "老北京铜锅涮肉": ["铜锅", "涮肉", "涮羊肉", "手切"],
    "京味炙子烤肉·京味小菜": ["炙子", "烤肉"],
    "新疆手抓饭/面馆": ["手抓饭", "丁丁炒面", "烤包子", "拌面"],
    "陕西小吃(肉夹馍/凉皮/油泼面)": ["肉夹馍", "凉皮", "油泼面", "米皮", "臊子面"],
    "兰州牛肉面": ["牛肉面", "牛大", "一清二白"],
    "台湾牛肉面·小吃": ["牛肉面", "卤味"],
    "台湾家常菜": ["台式", "台湾", "台菜", "卤肉饭", "三杯鸡", "卤猪脚", "便当", "炸鸡腿"],
    "高端台菜·台菜Bistro": ["台菜", "台式"],
    "蒙古菜": ["烤全羊", "手把肉", "蒙古"],
}


def is_root_cuisine(c):
    return c.get("parent_category") in ZONES


def cjk(s):
    return C.cjk_unify(str(s or "")).lower()


def score_leaf(leaf_name, sig_text, ev_text, name_text):
    kws = LEAF_DISH_KW.get(leaf_name, [])
    sig_t, ev_t, nm_t = cjk(sig_text), cjk(ev_text), cjk(name_text)
    sig_hits = sum(1 for k in kws if cjk(k) in sig_t)
    ev_hits = sum(1 for k in kws if cjk(k) in ev_t)
    prod_hits = 0
    for leaf, words in PRODUCT_NAME_WORDS.items():
        if leaf in leaf_name or leaf_name in leaf:
            prod_hits += sum(1 for w in words if cjk(w) in nm_t)
    place_hits = sum(1 for p in PLACE_TOKENS if cjk(p) in nm_t)
    score = sig_hits * 1.0 + ev_hits * 0.5 + prod_hits * 0.5
    return {"score": round(score, 2), "sig_hits": sig_hits, "ev_hits": ev_hits,
            "name_prod": prod_hits, "name_place_weak": place_hits}


def pick_primary(leaves, sig_text, ev_text, name_text):
    if not leaves:
        return None, "none", "无菜系叶", {}, {}
    name2leaf = {c["name"]: c for c in leaves}
    identity = [c for c in leaves if c["name"] not in FORMAT_LEAF_NAMES]
    fmt = [c for c in leaves if c["name"] in FORMAT_LEAF_NAMES]
    pool = identity if identity else fmt

    scores = {}
    for c in pool:
        scores[c["name"]] = score_leaf(c["name"], sig_text, ev_text, name_text)

    def sort_key(item):
        nm, sc = item
        return (sc["score"], 1 if nm in {x["name"] for x in identity} else 0, -len(nm))
    best_name, best = max(scores.items(), key=sort_key)

    target = name2leaf[best_name]
    others = [s["score"] for n, s in scores.items() if n != best_name]
    margin = best["score"] - max(others) if others else 9.9
    if best["sig_hits"] >= 1 and margin >= 0.5:
        conf = "high"
    elif best["score"] > 0:
        conf = "medium"
    else:
        conf = "high" if len(pool) == 1 else "low"
    basis = []
    if identity and fmt:
        basis.append(f"地域子流派({best_name})优先于产品/形式叶({[c['name'] for c in fmt]})")
    elif len(pool) == 1:
        basis.append(f"唯一菜系叶={best_name}")
    if best["sig_hits"]:
        basis.append(f"招牌菜命中{best['sig_hits']}词")
    if best["ev_hits"]:
        basis.append(f"食客证据命中{best['ev_hits']}词")
    if best["name_prod"]:
        basis.append("店名业态词佐证")
    if best["name_place_weak"] and best["sig_hits"] == 0 and best["ev_hits"] == 0:
        basis.append(f"仅店名地名弱信号({best['name_place_weak']})")
    return target["id"], conf, "; ".join(basis), best, scores


def run(data):
    cuis = data["cuisines"]; rests = data["restaurants"]; rc = data["rc"]
    byid = {c["id"]: c for c in cuis}
    rby = collections.defaultdict(list)
    for x in rc:
        rby[x["restaurant_id"]].append(x)
    rev_by = collections.defaultdict(list)
    for rv in data.get("reviews", []):
        if rv.get("review_kind") == "diner" and not rv.get("is_fake_suspect") and rv.get("source_url"):
            rev_by[rv["restaurant_id"]].append(rv)

    plan = []
    stats = collections.Counter()
    place_corrections = []  # 地名陷阱：名字地名指向X，但招牌/证据证明主营Y，引擎选了Y

    for r in rests:
        if r["status"] != "active":
            continue
        rid = r["id"]
        links = rby.get(rid, [])
        food = [l for l in links if byid.get(l["cuisine_id"], {}).get("dimension") == "菜系"]
        if not food:
            stats["no_cuisine_at_all"] += 1
            continue
        leaves = [byid[l["cuisine_id"]] for l in food if not is_root_cuisine(byid[l["cuisine_id"]])]
        roots = [l for l in food if is_root_cuisine(byid[l["cuisine_id"]])]

        sig = r.get("signature_dishes") or []
        sig_text = " ".join(str(x) for x in sig)
        ev_text = str(r.get("evidence_summary") or "")
        name_text = r.get("name") or ""

        if leaves:
            target_id, conf, reason, best_sc, all_scores = pick_primary(
                leaves, sig_text, ev_text, name_text)
        else:
            if len(roots) == 1:
                target_id = roots[0]["cuisine_id"]
                conf, reason = "high", "仅有菜系根，无更细叶"
            else:
                best = None; bests = -1
                for l in roots:
                    nm = byid[l["cuisine_id"]]["name"]
                    sc = score_leaf(nm, sig_text, ev_text, name_text)
                    if sc["score"] > bests:
                        bests = sc["score"]; best = l["cuisine_id"]
                target_id = best
                conf, reason = "medium", "多菜系根，按招牌/证据选主"
            best_sc, all_scores = {}, {}

        cur_prim = [l["cuisine_id"] for l in food if l.get("is_primary")]

        # ---- 覆盖保护：不轻易推翻人工已设的 leaf primary ----
        override_note = ""
        if len(cur_prim) == 1:
            cur_c = byid[cur_prim[0]]
            cur_is_root = is_root_cuisine(cur_c)
            if not cur_is_root and target_id != cur_prim[0]:
                # 已有 leaf primary：仅当①高置信 ②新叶招牌菜≥2命中 ③旧叶招牌菜0命中（证据明确矛盾）才改
                old_sig = score_leaf(cur_c["name"], sig_text, ev_text, name_text)["sig_hits"]
                new_sig = best_sc.get("sig_hits", 0) if best_sc else 0
                if not (conf == "high" and new_sig >= 2 and old_sig == 0):
                    override_note = (f"保留人工primary={cur_c['name']}(旧叶招牌命中{old_sig},"
                                     f"新叶={byid[target_id]['name']}命中{new_sig},证据不矛盾,不改)")
                    target_id = cur_prim[0]
                    conf = "preserved"
            elif cur_is_root and target_id and not is_root_cuisine(byid[target_id]):
                override_note = f"root→leaf:{cur_c['name']}->{byid[target_id]['name']}"

        before_prim = list(cur_prim)
        after_prim = [target_id] if target_id else []

        # 地名陷阱真案例：店名含地名 p，存在某叶名含 p（名字暗示），但引擎按招牌/证据选了别的叶
        nm_low = cjk(name_text)
        name_places = [p for p in PLACE_TOKENS if cjk(p) in nm_low]
        if name_places and leaves:
            chosen_name = byid[target_id]["name"] if target_id else ""
            for lf in leaves:
                if lf["name"] == chosen_name:
                    continue
                lf_places = [p for p in PLACE_TOKENS if cjk(p) in cjk(lf["name"])]
                if lf_places and set(lf_places) & set(name_places):
                    if best_sc.get("sig_hits", 0) >= 1 or best_sc.get("ev_hits", 0) >= 1:
                        place_corrections.append({
                            "restaurant_id": rid, "name": name_text,
                            "name_place_tokens": list(set(lf_places) & set(name_places)),
                            "name_suggested_leaf": lf["name"],
                            "evidence_chosen_leaf": chosen_name,
                            "evidence_dishes": [str(x) for x in sig][:5],
                            "note": f"店名地名指向{lf['name']}，但招牌菜/食客证据指向{chosen_name}，按主营出品定主",
                        })
                    break

        patches = []
        for l in food:
            cid = l["cuisine_id"]
            want = (cid == target_id)
            cur = bool(l.get("is_primary"))
            if want != cur:
                patches.append((rid, cid, want))

        if not patches:
            stats["no_change"] += 1; outcome = "no_change"
        elif before_prim == [] and after_prim:
            stats["main_newly_set"] += 1; outcome = "main_newly_set"
        elif len(before_prim) >= 2:
            stats["main_dedup"] += 1; outcome = "main_dedup"
        elif set(before_prim) != set(after_prim):
            stats["main_changed"] += 1; outcome = "main_changed"
        else:
            stats["secondary_only"] += 1; outcome = "secondary_only"

        ev_urls = [rv.get("source_url") for rv in rev_by.get(rid, [])[:2] if rv.get("source_url")]

        plan.append({
            "restaurant_id": rid, "name": name_text, "status": r["status"],
            "before_primary": [byid[c]["name"] for c in before_prim],
            "after_primary": [byid[c]["name"] for c in after_prim],
            "all_cuisine_tags": [byid[l["cuisine_id"]]["name"] for l in food],
            "outcome": outcome, "confidence": conf, "reason": reason,
            "override_note": override_note,
            "evidence_dishes": [str(x) for x in sig][:6],
            "evidence_summary_excerpt": ev_text[:160],
            "evidence_urls": ev_urls,
            "patches": [{"restaurant_id": p[0], "cuisine_id": p[1],
                         "cuisine_name": byid[p[1]]["name"], "is_primary": p[2]} for p in patches],
        })
    return plan, stats, place_corrections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--snapshot", default="")
    args = ap.parse_args()

    if args.snapshot:
        data = json.loads(pathlib.Path(args.snapshot).read_text(encoding="utf-8"))
    else:
        data = {
            "cuisines": C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id"),
            "restaurants": C.fetch_all("restaurants", "id,name,status,signature_dishes,evidence_summary", order_col="id"),
            "rc": C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id,is_primary", order_col="restaurant_id"),
            "reviews": C.fetch_all("reviews", "restaurant_id,source_url,source_platform,review_kind,is_fake_suspect", order_col="id"),
        }
    plan, stats, corrections = run(data)

    outdir = pathlib.Path(__file__).parent
    (outdir / "primary_engine_report.json").write_text(
        json.dumps({"stats": dict(stats), "place_corrections": corrections, "plan": plan},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Phase 0-B 主营(is)/含有(serves) 引擎 dry-run ===")
    for k, v in stats.most_common():
        print(f"  {k:24s} {v}")
    changed = [p for p in plan if p["outcome"] != "no_change"]
    print(f"\n需变更餐厅: {len(changed)} / {len(plan)}")
    print(f"地名陷阱纠正案例: {len(corrections)}")
    with open(outdir / "primary_engine_before_after.tsv", "w", encoding="utf-8") as f:
        f.write("restaurant_id\tname\toutcome\tconfidence\tbefore_primary\tafter_primary\treason\tpatches\n")
        for p in plan:
            ps = "; ".join(f"{x['cuisine_name']}->{x['is_primary']}" for x in p["patches"])
            f.write(f"{p['restaurant_id']}\t{p['name']}\t{p['outcome']}\t{p['confidence']}\t"
                    f"[{','.join(p['before_primary'])}]\t[{','.join(p['after_primary'])}]\t{p['reason']}\t{ps}\n")
    print("报告 -> primary_engine_report.json / primary_engine_before_after.tsv")

    if not args.commit:
        print("\n[dry-run] 未写库。确认自检通过后加 --commit。")
        return

    import time
    ok = fail = 0
    for p in plan:
        for pt in p["patches"]:
            cid, want = pt["cuisine_id"], pt["is_primary"]
            r = C.req("PATCH",
                      f"/restaurant_cuisines?restaurant_id=eq.{pt['restaurant_id']}&cuisine_id=eq.{cid}",
                      json={"is_primary": want})
            if r.status_code in (200, 204):
                ok += 1
            else:
                fail += 1
                print(f"  PATCH fail rid={pt['restaurant_id']} cid={cid} -> {want}: "
                      f"{r.status_code} {r.text[:150]}")
            time.sleep(0.04)
    print(f"\n[commit] PATCH {ok} 成功 / {fail} 失败")


if __name__ == "__main__":
    main()
