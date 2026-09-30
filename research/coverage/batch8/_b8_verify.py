import sys, json
sys.path.insert(0,"/app/pipeline")
import common as C

# re-pull rc + count target leaves
rc = C.fetch_all("restaurant_cuisines","restaurant_id,cuisine_id,is_primary",page=1000,order_col="restaurant_id")
from collections import defaultdict
cnt=defaultdict(set)
for r in rc: cnt[r["cuisine_id"]].add(r["restaurant_id"])
targets={85:"日料根",236:"乌冬root",273:"赞岐",274:"咖喱乌冬",275:"手打乌冬",261:"荞麦root",270:"冷荞麦",271:"天妇罗荞麦",272:"十割二八",301:"面包root",309:"日式面包"}
print("=== POST leaf counts (active all links) ===")
for cid,nm in targets.items():
    print(f"  [{cid}] {nm}: {len(cnt.get(cid,[]))}")

# verify new rows
for rid in [2007,2008,2009]:
    r = C.req("GET",f"/restaurants?id=eq.{rid}&select=id,name,name_en,status,address,price_avg,location,phone,opening_hours").json()
    links = C.req("GET",f"/restaurant_cuisines?restaurant_id=eq.{rid}&select=cuisine_id,is_primary").json()
    print(f"\nrid={rid}: {r[0]['name']} | en={r[0].get('name_en')} | status={r[0]['status']} | price={r[0].get('price_avg')}")
    print("   addr:", r[0].get("address"))
    print("   location:", r[0].get("location"), "| phone:", r[0].get("phone"), "| hours:", r[0].get("opening_hours"))
    print("   cids:", sorted([l["cuisine_id"] for l in links]))
