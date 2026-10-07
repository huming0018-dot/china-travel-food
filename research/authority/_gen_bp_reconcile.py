#!/usr/bin/env python3
# 通用权威名单按名对账生成器：读 blackpearl_shanghai_full.json，产出容器内运行脚本。
import json, pathlib

A = pathlib.Path(__file__).parent
bp = json.loads((A / "blackpearl_shanghai_full.json").read_text(encoding="utf-8"))
recs = []
for key in ("three_diamond", "two_diamond", "one_diamond"):
    for r in bp.get(key, []):
        recs.append({"name": r.get("name", ""), "diamond": r.get("diamond"),
                     "cuisine": r.get("cuisine"), "district": r.get("district"),
                     "address": r.get("address")})

TEMPLATE = r'''
import sys, json, re, pathlib
sys.path.insert(0,"/app/pipeline")
import common as C
RECS = json.loads(r"""__RECS__""")
_CN_NUM={"零":"0","一":"1","二":"2","两":"2","三":"3","四":"4","五":"5","六":"6","七":"7","八":"8","九":"9"}
def _nd(s): return re.sub(r"[零一二两三四五六七八九]{2,}", lambda m:"".join(_CN_NUM.get(c,c) for c in m.group(0)), s)
def core(s):
    s=re.sub(r"[（(].*?[)）]","",s or "")
    # 去分店尾缀（新天地店/外滩店），权威名常带而库名不带
    s=re.sub(r"(店)$","",s)
    return _nd(C.cjk_norm(s))
def _han(s): return "".join(c for c in s if "一"<=c<="鿿")
def eligible(c):
    j=len(_han(c)); return j>=2 or (j==1 and len(c)>=3) or (j==0 and len(c)>=4)
def make_matcher(rests):
    index={}
    for r in rests:
        for nm in (r["name"], r.get("name_en")):
            if nm: index.setdefault(core(nm), r)
    def match(c0):
        if c0 in index: return index[c0],"exact"
        strong, weak=[],[]
        ch=_han(c0)
        if eligible(c0):
            for k,r in index.items():
                kh=_han(k); hit=False
                if ch and kh and ch in kh: hit="strong"
                elif c0 in k or k in c0:
                    ratio=min(len(c0),len(k))/max(len(c0),len(k))
                    hit="strong" if (k.startswith(c0) or ratio>=0.6) else ("weak" if ratio>=0.35 else False)
                if hit=="strong": strong.append(r)
                elif hit=="weak": weak.append(r)
        if len(ch)==1:
            starts=[r for k,r in index.items() if _han(k).startswith(ch)]
            if len(starts)==1: return starts[0],"strong"
            if starts: return starts[0],"weak"
        if strong: return strong[0],"strong"
        if weak: return weak[0],"weak"
        return None,"none"
    return match
rests=C.fetch_all("restaurants","id,name,name_en,status,district")
matcher=make_matcher(rests)
hit=[]; missing=[]; uncertain=[]
for r in RECS:
    c0=core(r["name"])
    m,conf=matcher(c0)
    if not eligible(c0) and conf in ("none","weak"): conf="short" if conf=="none" else conf
    if conf in ("exact","strong"): hit.append({**r,"id":m["id"],"status":m["status"]})
    elif conf in ("weak","short"): uncertain.append({**r,"reason":conf,"cand":m["name"] if m else None})
    else: missing.append(r)
out={"total":len(RECS),"hit":len(hit),"missing":missing,"uncertain":uncertain}
pathlib.Path("/app/data/blackpearl_reconcile.json").write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
print("blackpearl total",len(RECS),"| in-db",len(hit),"| uncertain",len(uncertain),"| missing",len(missing))
for x in missing: print("  X",x["name"],"|",x.get("cuisine"),x.get("district"))
for x in uncertain: print("  ?",x["name"],"~",x["cand"])
'''
print(TEMPLATE.replace("__RECS__", json.dumps(recs, ensure_ascii=False)))
