#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prefill_governance.py — 填充前数据治理 / 本地化负面清单（机制优先、可溯、可逆）。

为什么存在（用户第二大意见：缺本地化；并要求 Apify 填充前先清洗）：
  旧 chain_audit/negative_audit 主要靠"人工品牌词表 + 库内分店计数"，会漏掉
  ① 只入库 1 家分店、但实为连锁/预制的品牌（苹果花园 id1853 被判独立店）；
  ② 评论里已暴露"工业味/预制/统一配送"的店。结果污染店留在榜单、还会白白花钱去 Apify 验证。

机制（信号发现候选 → 模型封闭裁决 → 沉淀注册表；不靠人工枚举）：
  1. 确定性信号：库内分店数 / 已设 chain 字段 / 评论工业信号(需佐证) / 已知品牌 / 业态。
  2. 候选 = 触发任一规则的店；输出 candidates.json 交模型在【封闭标签集】内裁决：
       INDUSTRIAL 标准化/预制/非本地化连锁 → 隐藏 + 不填充
       QUALITY    多店但现做的高端/优质集团(新荣记/大董/甬府/鼎泰丰) → 保留可填充
       INDEPENDENT 本地独立店 → 保留可填充
       UNCERTAIN  证据不足 → 暂不付费填充
  3. 裁决写入 governance_registry.json（长期复用，未来只对新候选裁决，省 token）。
  4. plan/apply：只 PATCH chain_type/central_kitchen/premade_risk（is_chain_standardized 由 DB 派生），
     生成"值得填充"队列 worth_fill.json（active、非标准化、pr!=高、缺真实口味证据）。

用法：
  python3 prefill_governance.py candidates
  python3 prefill_governance.py plan   --decisions governance_decisions.json
  python3 prefill_governance.py apply
"""
import argparse, collections, json, os, pathlib, re, sys
import common as C

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", os.getcwd()))
REG = DATA / "governance_registry.json"
CAND = DATA / "governance_candidates.json"
PLAN = DATA / "governance_plan.json"
WORTH = DATA / "worth_fill.json"
INDUSTRIAL_TAG_ID = 258

# ---- 已知"标准化/预制/非本地化"品牌（确定性预标；可被注册表/裁决覆盖）----
NEGATIVE = [
 "星巴克","瑞幸","manner","costa","tims","苹果花园","85度","面包新语","巴黎贝甜?","蜜雪冰城",
 "茶百道","古茗","沪上阿姨","书亦","一点点","coco","快乐柠檬","贡茶","奈雪","喜茶","乐乐茶",
 "麦当劳","肯德基","汉堡王","必胜客","华莱士","赛百味","德克士","塔斯汀","米村拌饭","小菜园",
 "费大厨","农耕记","老乡鸡","乡村基","真功夫","永和大王","吉野家","食其家","松屋","杨国福",
 "张亮麻辣烫","呷哺呷哺","望湘园","外婆家","绿茶餐厅","盖饭邦","味千","和府捞面","陈香贵",
 "张拉拉","马记永?","霸王茶姬","seesaw","%m?","peets","皮爷",
]
NEG_RE = re.compile("|".join(re.escape(x.rstrip("?")) for x in NEGATIVE), re.I)
# ---- 高端/优质"现做多店"集团白名单（多店但 ck=无 pr=无，不隐藏）----
QUALITY = ["新荣记","荣府宴","大董","小大董","甬府","菁禧荟","鹿园","鲁采","福和慧","鼎泰丰",
           "一风堂","老干杯","晟永兴","黑珍珠?","遇外滩","淮扬府","玉芝兰","新荣记?"]
QUAL_RE = re.compile("|".join(re.escape(x.rstrip("?")) for x in QUALITY), re.I)

STRONG = re.compile(r"预制菜|预制|料理包|中央厨房|工业味|工业化|统一配送|复热|半成品|科技与狠活|料包|冷冻")
CHAINW = re.compile(r"连锁|标准化|分店|到处都有|加盟店")

def brand_core(n):
    n = re.sub(r"[（(].*?[)）]", "", n or "")
    n = re.split(r"[·・•]", n)[0]
    return C.cjk_norm(n)

def load_reg():
    return json.loads(REG.read_text(encoding="utf-8")) if REG.exists() else {}
def save_reg(d):
    REG.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

def build():
    R = C.fetch_all("restaurants",
        "id,name,name_en,status,chain_type,central_kitchen,premade_risk,is_chain_standardized,district")
    V = C.fetch_all("reviews","restaurant_id,content,source_platform,aspect_taste,trust_level")
    act = [r for r in R if r["status"]=="active"]
    # taste evidence per shop
    taste = collections.Counter()
    for v in V:
        if v.get("aspect_taste") and (v.get("trust_level") in ("high","mid",None)):
            taste[v["restaurant_id"]] += 1
    # industrial review signals
    strong = collections.Counter(); chainw = collections.Counter()
    iquotes = collections.defaultdict(list)
    for v in V:
        c = v.get("content") or ""
        if STRONG.search(c):
            strong[v["restaurant_id"]] += 1
            if len(iquotes[v["restaurant_id"]]) < 3:
                m = STRONG.search(c); s=max(0,m.start()-12); iquotes[v["restaurant_id"]].append(c[s:m.end()+18])
        if CHAINW.search(c): chainw[v["restaurant_id"]] += 1
    # branch counts
    bc = collections.defaultdict(list)
    for r in act: bc[brand_core(r["name"])].append(r["id"])
    reg = load_reg()
    cands = []
    for r in act:
        rid=r["id"]; nm=r["name"] or ""; ne=r.get("name_en") or ""
        if str(rid) in reg: continue
        nb = len(bc[brand_core(nm)])
        neg = bool(NEG_RE.search(nm) or NEG_RE.search(ne))
        qual = bool(QUAL_RE.search(nm) or QUAL_RE.search(ne))
        ns, nc = strong[rid], chainw[rid]
        reasons=[]
        if neg and not qual: reasons.append("known_negative_brand")
        if qual: reasons.append("known_quality_group")
        if nb>=2: reasons.append(f"db_branches={nb}")
        if ns>=2: reasons.append(f"strong_industrial_reviews={ns}")
        if ns>=1 and (nb>=2 or neg): reasons.append("industrial+chain_corroboration")
        # also surface currently-independent shops with a single strong signal in a chain-prone format handled at adjudication
        if reasons:
            cands.append({"id":rid,"name":nm,"name_en":ne,"chain_type":r.get("chain_type"),
                "central_kitchen":r.get("central_kitchen"),"premade_risk":r.get("premade_risk"),
                "std":r.get("is_chain_standardized"),"branches":nb,"strong_reviews":ns,
                "chain_reviews":nc,"taste_evidence":taste[rid],"reasons":reasons,
                "iquotes":iquotes.get(rid,[])})
    out={"n_active":len(act),"n_std":sum(1 for r in act if r.get("is_chain_standardized")),
         "candidates":cands}
    CAND.write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
    print(f"active={len(act)} already_std={out['n_std']} new_candidates={len(cands)}")
    cc=collections.Counter(x["reasons"][0] for x in cands)
    print("候选首因:",dict(cc))
    return out

def plan(dec_path):
    dec=json.loads(pathlib.Path(dec_path).read_text(encoding="utf-8"))
    reg=load_reg()
    for k,v in dec.items():
        reg[str(k)] = v if isinstance(v,dict) else {"label":v}
    save_reg(reg)
    cd=json.loads(CAND.read_text(encoding="utf-8"))
    R=C.fetch_all("restaurants","id,name,status,chain_type,central_kitchen,premade_risk,is_chain_standardized")
    Rmap={r["id"]:r for r in R}
    patches={}; labels={}
    for k,info in reg.items():
        labels[int(k)]=info.get("label")
    for k,info in reg.items():
        rid=int(k); lab=info.get("label"); r=Rmap.get(rid)
        if not r or r["status"]!="active": continue
        cur=(r.get("chain_type"),r.get("central_kitchen"),r.get("premade_risk"))
        if lab=="INDUSTRIAL":
            # 已派生 std=true 的连锁无需改动；仅给漏标（std=false）的污染店打标。
            if not r.get("is_chain_standardized"):
                ct=info.get("chain_type","大型连锁"); ck=info.get("central_kitchen","确认"); pr=info.get("premade_risk","高")
                patches[rid]={"chain_type":ct,"central_kitchen":ck,"premade_risk":pr}
        elif lab=="QUALITY":
            # 多店但现做：只强制 ck=无、pr=无（使 std 派生为 false、可填充）；chain_type 维持原描述。
            tgt={"central_kitchen":"无","premade_risk":"无"}
            cur_present={"central_kitchen":r.get("central_kitchen"),"premade_risk":r.get("premade_risk")}
            if cur_present!=tgt: patches[rid]=tgt
        elif lab=="INDEPENDENT":
            if cur!=("独立店","无","无"): patches[rid]={"chain_type":"独立店","central_kitchen":"无","premade_risk":"无"}
    # worth-fill queue
    V=C.fetch_all("reviews","restaurant_id,aspect_taste,trust_level")
    taste=collections.Counter()
    for v in V:
        if v.get("aspect_taste"): taste[v["restaurant_id"]]+=1
    worth=[]
    for r in R:
        if r["status"]!="active": continue
        lab=labels.get(r["id"])
        if lab in ("INDUSTRIAL","UNCERTAIN"): continue
        if r.get("is_chain_standardized") or r.get("premade_risk")=="高": continue
        if taste[r["id"]]>=2: continue
        worth.append({"id":r["id"],"name":r["name"],"taste_evidence":taste[r["id"]],"label":lab or "INDEPENDENT"})
    WORTH.write_text(json.dumps(worth,ensure_ascii=False,indent=1),encoding="utf-8")
    out={"n_patches":len(patches),"patches":patches,"worth_fill":len(worth),
         "label_counts":dict(collections.Counter(labels.values()))}
    PLAN.write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
    print("裁决分布:",dict(collections.Counter(labels.values())))
    print("待PATCH:",len(patches))
    print("值得填充队列(缺>=2口味证据):",len(worth))
    print("\n样例 PATCH:")
    for rid,p in list(patches.items())[:15]:
        print("  ",rid,Rmap[rid]["name"],"->",p)
    return out

def apply():
    p=json.loads(PLAN.read_text(encoding="utf-8"))
    n=0
    for rid,patch in p["patches"].items():
        resp=C.req("PATCH",f"/restaurants?id=eq.{rid}",json=patch)
        if resp.status_code in (200,204): n+=1
        else: print("FAIL",rid,resp.status_code,resp.text[:120])
    print(f"PATCH 完成 {n}/{len(p['patches'])}")
    print("值得填充队列:",p["worth_fill"])

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cmd",choices=["candidates","plan","apply"])
    ap.add_argument("--decisions",default="governance_decisions.json")
    a=ap.parse_args()
    if a.cmd=="candidates": build()
    elif a.cmd=="plan": plan(a.decisions)
    else: apply()
