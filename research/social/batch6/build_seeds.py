import sys, json, os
sys.path.insert(0,"/app/pipeline")
import common as C
APPLY = os.environ.get("BATCH6_APPLY")=="1"

chefs = C.fetch_all("chefs","id,name,title,group_id,tracking_seeds,media_mentions,last_tracked_at",order_col="id")
# 列类型体检
print("TYPECHECK media_mentions sample types:", set(type(c.get("media_mentions")).__name__ for c in chefs))
print("TYPECHECK tracking_seeds sample types:", set(type(c.get("tracking_seeds")).__name__ for c in chefs))
print("raw row id1:", json.dumps({k:chefs[0][k] for k in ['id','name','tracking_seeds','media_mentions','last_tracked_at']}, ensure_ascii=False, default=str))

def priority(c):
    t=(c.get("title") or "")
    if c.get("group_id") is not None: return "high"
    if any(w in t for w in ["米其林","集团","创始人","董事长","教父","大师","MOF","星"]): return "high"
    return "normal"

plan=[]
for c in chefs:
    nm=c["name"]
    seed={
        "web_query": f"{nm} 上海 (新店 OR 离职 OR 客座 OR 获奖 OR 菜单发布)",
        "platforms": ["web","wechat_mp","bilibili"],
        "skip_login": ["weibo","zhihu","douyin"],
        "priority": priority(c),
        "topics": ["new_restaurant","departure","guest_chef","award","menu_change"]
    }
    plan.append((c["id"], nm, seed))

from collections import Counter
print("priority分布:", Counter(priority(c) for c in chefs))
print("样例 seed id1:", json.dumps(dict(plan[0][2]), ensure_ascii=False))
print("样例 seed id14(张勇):", json.dumps(dict([p for p in plan if p[1]=='张勇'][0][2]), ensure_ascii=False))
print(f"待建seed {len(plan)} 家")

if not APPLY:
    print("[DRY-RUN] BATCH6_APPLY=1 写 tracking_seeds"); sys.exit(0)

ok=fail=0
import time
for cid,nm,seed in plan:
    r=C.req("PATCH",f"/chefs?id=eq.{cid}",json={"tracking_seeds":seed})
    if r.status_code in (200,204): ok+=1
    else:
        fail+=1; print(f"[FAIL] {cid} {nm}: {r.status_code} {r.text[:150]}",file=sys.stderr)
    time.sleep(0.04)
# 回读
ids=",".join(str(p[0]) for p in plan)
rv=C.req("GET",f"/chefs?select=id,tracking_seeds&id=in.({ids})")
got={row["id"]:row.get("tracking_seeds") for row in rv.json()}
verified=sum(1 for cid,nm,seed in plan if got.get(cid)==seed)
print(f"tracking_seeds 写 ok={ok} fail={fail} 回读一致 {verified}/{len(plan)}")
