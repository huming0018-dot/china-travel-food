#!/usr/bin/env python3
# 本地生成器：读 _slug_name.json，产出在容器内 stdin 运行的确定性米其林对账脚本。
import json, pathlib

A = pathlib.Path(__file__).parent
sn = json.loads((A / "_slug_name.json").read_text(encoding="utf-8"))
sn["wang-lu"] = "望庐"

TEMPLATE = r'''
import sys, json, re, pathlib
sys.path.insert(0, "/app/pipeline")
import common as C
SLUG_NAME = __SLUGNAME__

_CN_NUM = {"零":"0","一":"1","二":"2","两":"2","三":"3","四":"4","五":"5","六":"6","七":"7","八":"8","九":"9"}
_STOP1 = {"the","la","le","da","de","yi","new","old","little","big","au","el","al","di","san"}
def _norm_digits(s):
    return re.sub(r"[零一二两三四五六七八九]{2,}", lambda m:"".join(_CN_NUM.get(c,c) for c in m.group(0)), s)
def core(s):
    s = re.sub(r"[（(].*?[)）]", "", s or "")
    return _norm_digits(C.cjk_norm(s))
def _han(s): return "".join(c for c in s if "一" <= c <= "鿿")
def _cjk_count(s): return len(_han(s))
def eligible(c):
    j=_cjk_count(c)
    return j>=2 or (j==1 and len(c)>=3) or (j==0 and len(c)>=4)
def slug_brand_cores(slug):
    s=re.sub(r"-\d{5,}$","",slug); parts=s.split("-"); keys=set()
    for n in (1,2,3):
        if len(parts)>=n:
            if n==1 and parts[0] in _STOP1: continue
            keys.add(core(" ".join(parts[:n])))
    return {k for k in keys if eligible(k)}
def make_matcher(rests):
    index={}
    for r in rests:
        for nm in (r["name"], r.get("name_en")):
            if nm: index.setdefault(core(nm), r)
    def match(cores):
        cores=[c for c in cores if c]
        for c in cores:
            if c in index: return index[c],"exact"
        strong, weak=[],[]
        for c in cores:
            ch=_han(c)
            if not eligible(c):
                if not ch and len(c)>=3:
                    for k,r in index.items():
                        nxt=k[len(c)] if len(k)>len(c) else ""
                        if k.startswith(c) and not ("a"<=nxt<="z"): strong.append(r)
                continue
            for k,r in index.items():
                k_han=_han(k); hit=False
                if ch and k_han and ch in k_han: hit="strong"
                elif c in k or k in c:
                    ratio=min(len(c),len(k))/max(len(c),len(k))
                    hit="strong" if (k.startswith(c) or ratio>=0.6) else ("weak" if ratio>=0.35 else False)
                if hit=="strong": strong.append(r)
                elif hit=="weak": weak.append(r)
        for c in cores:
            ch=_han(c)
            if len(ch)==1:
                starts=[r for k,r in index.items() if _han(k).startswith(ch)]
                if len(starts)==1: return starts[0],"strong"
                if starts: return starts[0],"weak"
        for c in cores:
            if _cjk_count(c)==0 and len(c)==3:
                heads=[r for k,r in index.items() if k.startswith(c) and not k[len(c):len(c)+1].isalpha()]
                if len(heads)==1: return heads[0],"strong"
        if strong: return strong[0],"strong"
        if weak: return weak[0],"weak"
        return None,"none"
    return match

rests=C.fetch_all("restaurants","id,name,name_en,status,district")
matcher=make_matcher(rests)
rows=[]; missing=[]; uncertain=[]
for slug,name in sorted(SLUG_NAME.items()):
    aliases=[core(name)] if name else []
    aliases+=list(slug_brand_cores(slug))
    m,conf=matcher(aliases)
    if not eligible(core(name)) and conf in ("none","weak"):
        conf="short" if conf=="none" else conf
    rows.append({"slug":slug,"name":name,"conf":conf,"id":m["id"] if m else None,"status":m["status"] if m else None})
    if conf=="none": missing.append({"slug":slug,"name":name})
    elif conf in ("weak","short"): uncertain.append({"slug":slug,"name":name,"reason":conf,"cand":m["name"] if m else None})
out={"total":len(SLUG_NAME),"missing":missing,"uncertain":uncertain}
pathlib.Path("/app/data/authority_reconcile.json").write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
hit=len(rows)-len(missing)-len(uncertain)
print("sitemap total",len(rows),"| in-db",hit,"| uncertain",len(uncertain),"| missing",len(missing))
for x in uncertain: print("  ?",x["name"],x["slug"],x["reason"],"cand=",x["cand"])
for x in missing: print("  X",x["name"],x["slug"])
'''
print(TEMPLATE.replace("__SLUGNAME__", json.dumps(sn, ensure_ascii=False)))
