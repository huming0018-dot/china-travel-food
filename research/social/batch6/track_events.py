import sys, json, os, hashlib, time
sys.path.insert(0,"/app/pipeline")
import common as C
APPLY = os.environ.get("BATCH6_APPLY")=="1"
TODAY="2026-09-30"

EVENTS = [
 {"title":"新荣记古北「荣小馆」新店即将启幕",
  "category":"new_restaurant","event_date":"2026-02-06","chef_id":14,"confidence":"mid","status":"rumor",
  "tags":["集团扩张","新店预告"],"event_subtype":"新店预告",
  "summary":"新荣记旗下荣小馆上海古北新店将于2026年启幕，由中河建设ZHDC承建，定位烟火家常、松弛质感。",
  "sources":[{"url":"https://www.iesdouyin.com/share/video/7603669773947342089","date":"2026-02-06","title":"全新新荣记「荣小馆」上海古北即将启幕","author":"中河建设ZHDC","platform":"抖音"}]},
 {"title":"新荣记×CCD郑中设计 落子上海首店，板前「荣焰」成新品全球首发",
  "category":"new_restaurant","event_date":"2026-08-20","chef_id":14,"confidence":"mid","status":"rumor",
  "tags":["集团扩张","新店预告"],"event_subtype":"新店预告",
  "summary":"继深圳雍熙荣·新荣记板前「荣焰」成为新荣记新品全球首发之所后，CCD与新荣记再度携手落子上海，打造新荣记系列上海首店。",
  "sources":[{"url":"https://www.iesdouyin.com/share/video/7675989876952550656","date":"2026-08-20","title":"CCD×新荣记「荣焰」…落子上海","author":"CCD郑中设计","platform":"抖音"}]},
 {"title":"新荣记虹桥店推板前铁板烧omakase（上海唯一，约13800元）",
  "category":"menu_change","event_date":"2026-01-08","chef_id":14,"confidence":"mid","status":"verified",
  "tags":["新品类","板前铁板"],"event_subtype":"新品上线",
  "summary":"新荣记在虹桥店上线板前铁板烧omakase，为上海门店独有，人均约13800元，属集团高端板前品类延伸。",
  "sources":[{"url":"https://www.iesdouyin.com/share/video/7593013826242467465","date":"2026-01-08","title":"新荣记板前铁板，上海唯一","author":"抖音探店","platform":"抖音"}]},
 {"title":"甬府·北外滩 × A.Wong × 菁禧荟 六手联弹晚宴（翁拥军/Andrew Wong/杜建青）",
  "category":"guest_chef","event_date":"2026-08-20","chef_id":15,"related_restaurant_id":None,"confidence":"high","status":"verified",
  "tags":["客座联弹","六手联弹"],"event_subtype":"客座联名",
  "summary":"甬府主厨翁拥军、伦敦米其林二星Andrew Wong(A.Wong)、菁禧荟主厨杜建青三地主厨首度联袂，于上海甬府·北外滩呈献六手联弹晚宴，对话宁波菜、中餐与潮州菜。",
  "sources":[{"url":"https://m.weibo.cn/detail/5334019446410351","date":"2026-08-20","title":"甬府·北外滩、A.Wong与菁禧荟首度联袂六手联弹","author":"TK饕客","platform":"微博"}]},
 {"title":"甬府翁拥军谈门店分层：北外滩抓年轻客、砍半包间改明档",
  "category":"menu_change","event_date":"2026-09-29","chef_id":15,"confidence":"high","status":"verified",
  "tags":["集团战略","门店改造"],"event_subtype":"门店调整",
  "summary":"翁拥军提出餐饮存量深耕下的门店分层：锦江店守传统、北外滩店抓年轻客；并在甬府小鲜砍掉约半包间改明档，让食客与食材直接对话，吸引年轻客群。",
  "sources":[{"url":"https://m.21jingji.com/article/20260929/herald/2bb29c17bfcacb70fabf89b0930ae3a1_zaker.html","date":"2026-09-29","title":"餐饮进入存量深耕阶段…翁拥军案例","author":"21世纪经济报道","platform":"21财经"},
             {"url":"http://news.qq.com/rain/a/20260930A02E8K00","date":"2026-09-30","title":"什么样的餐厅值得消费者买单","author":"腾讯新闻","platform":"腾讯"}]},
]

CHEF_PATCH = {14:3, 15:2, 16:1, 1:0}  # chef_id -> media_mentions count this run

def fp(e):
    return hashlib.md5((e["title"]+e["event_date"]).encode()).hexdigest()[:24]

for e in EVENTS:
    e["scope"]="local"; e["city"]="上海"; e["dedup_fingerprint"]=fp(e)

print("=== DRY RUN: 将插入 food_events", len(EVENTS), "条 ===")
for e in EVENTS:
    print(f"  [{e['category']}] {e['title']} | chef={e['chef_id']} | {e['event_date']} | {e['status']}")
print("=== 将 PATCH chefs last_tracked_at=",TODAY,"===")
for cid,m in CHEF_PATCH.items():
    print(f"  chef {cid}: last_tracked_at={TODAY} media_mentions={m}")

if not APPLY:
    print("[DRY-RUN] BATCH6_APPLY=1 写入"); sys.exit(0)

# 幂等：先按 dedup_fingerprint 查重
existing = C.fetch_all("food_events","dedup_fingerprint,title",order_col="id")
have={r["dedup_fingerprint"] for r in existing}
ins=0
for e in EVENTS:
    if e["dedup_fingerprint"] in have:
        print("skip dup:", e["title"]); continue
    payload={k:v for k,v in e.items()}
    r=C.req("POST","/food_events",json=payload)
    if r.status_code in (200,201): ins+=1
    else: print("[POST FAIL]",r.status_code,r.text[:200],file=sys.stderr)
    time.sleep(0.1)
print(f"food_events 新增 {ins} 条")

# PATCH chefs
ok=0
for cid,m in CHEF_PATCH.items():
    r=C.req("PATCH",f"/chefs?id=eq.{cid}",json={"last_tracked_at":TODAY,"media_mentions":m})
    if r.status_code in (200,204): ok+=1
    else: print("[PATCH CHEF FAIL]",cid,r.status_code,r.text[:150],file=sys.stderr)
print(f"chefs PATCH ok={ok}/{len(CHEF_PATCH)}")

# 回读
rv=C.req("GET",f"/chefs?select=id,name,last_tracked_at,media_mentions&id=in.({','.join(map(str,CHEF_PATCH))})")
print("回读:",json.dumps(rv.json(),ensure_ascii=False,default=str))
fe=C.req("GET",f"/food_events?select=id,title,chef_id,status&event_date=gte.2026-01-01&order=id.desc&limit=10")
print("近期events回读:",json.dumps(fe.json(),ensure_ascii=False,default=str))
