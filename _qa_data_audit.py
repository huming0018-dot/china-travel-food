#!/usr/bin/env python3
"""数据质量红队审计 — 直接查生产库，找所有能被攻击的点。"""
import os, sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "cloud"))
sys.path.insert(0, str(pathlib.Path(__file__).parent / "cloud" / "vendor" / "pipeline"))
import common as C
import requests

def q(sql):
    """用 service role 执行 SQL via PostgREST 不行，直接用 REST API 查。"""
    pass

BASE = C.BASE
H = C.headers(use_service=True)

def get(path):
    r = requests.get(BASE + path, headers=H, timeout=30)
    return r

def count(path):
    h = {**H, "Prefer": "count=exact", "Range": "0-0"}
    r = requests.get(BASE + path, headers=h, timeout=30)
    cr = r.headers.get("Content-Range", "")
    if "/" in cr:
        return int(cr.split("/")[-1])
    return len(r.json()) if r.status_code == 200 else 0

print("=" * 60)
print("数据质量红队审计报告")
print("=" * 60)

# 1. 总量
total = count("/restaurants?select=id")
active = count("/restaurants?select=id&status=eq.active")
closed = count("/restaurants?select=id&status=eq.closed")
reviews = count("/reviews?select=id")
cuisines = count("/cuisines?select=id")
rc = count("/restaurant_cuisines?select=restaurant_id")
print(f"\n【总量】")
print(f"  餐厅总数: {total}")
print(f"  营业中: {active}")
print(f"  已关店: {closed}")
print(f"  评论总数: {reviews}")
print(f"  菜系标签数: {cuisines}")
print(f"  餐厅-菜系关联数: {rc}")

# 2. 空值率
print(f"\n【关键字段空值率】")
fields = ["phone", "location", "address", "price_avg", "score_total",
          "score_taste", "opening_hours", "signature_dishes", "district"]
for f in fields:
    null_count = count(f"/restaurants?select=id&status=eq.active&{f}=is.null")
    pct = null_count / active * 100 if active else 0
    print(f"  {f}: {null_count}/{active} ({pct:.1f}%)")

# 3. 重复店名
print(f"\n【重复店名（营业中）】")
r = get("/restaurants?select=name&status=eq.active")
names = [x["name"] for x in r.json()]
from collections import Counter
dupes = {k: v for k, v in Counter(names).items() if v > 1}
print(f"  重复店名数: {len(dupes)}")
for name, cnt in sorted(dupes.items(), key=lambda x: -x[1])[:15]:
    print(f"    '{name}' x{cnt}")

# 4. 评分异常
print(f"\n【评分异常】")
r = get("/restaurants?select=id,name,score_total,score_taste,score_objective,score_diner,score_endorsement,price_avg&status=eq.active&order=score_total.desc&limit=20")
top = r.json()
print(f"  TOP20 总分:")
for x in top[:10]:
    print(f"    #{x['id']} {x['name'][:20]:20s} total={x.get('score_total')} taste={x.get('score_taste')} obj={x.get('score_objective')} diner={x.get('score_diner')} endors={x.get('score_endorsement')} price={x.get('price_avg')}")

# 评分=0 但有总分的
zero_taste = count("/restaurants?select=id&status=eq.active&score_total=not.is.null&score_taste=is.null")
print(f"\n  有总分但口味分为空: {zero_taste}")

# 5. 评论质量
print(f"\n【评论质量】")
r = get("/reviews?select=source_platform,trust_level,review_kind&limit=1000")
revs = r.json()
from collections import Counter
src = Counter(x.get("source_platform") for x in revs)
trust = Counter(x.get("trust_level") for x in revs)
kind = Counter(x.get("review_kind") for x in revs)
print(f"  来源分布: {dict(src)}")
print(f"  可信度分布: {dict(trust)}")
print(f"  类型分布: {dict(kind)}")

# 空内容评论
empty_rev = count("/reviews?select=id&content=is.null")
print(f"  空内容评论: {empty_rev}")

# 6. 价格异常
print(f"\n【价格异常】")
r = get("/restaurants?select=id,name,price_avg&status=eq.active&price_avg=not.is.null&order=price_avg.asc&limit=10")
cheap = r.json()
print(f"  最便宜10家:")
for x in cheap:
    print(f"    #{x['id']} {x['name'][:25]:25s} ¥{x.get('price_avg')}")
r = get("/restaurants?select=id,name,price_avg&status=eq.active&price_avg=not.is.null&order=price_avg.desc&limit=10")
expensive = r.json()
print(f"  最贵10家:")
for x in expensive:
    print(f"    #{x['id']} {x['name'][:25]:25s} ¥{x.get('price_avg')}")

# 7. 菜系覆盖
print(f"\n【菜系覆盖】")
r = get("/restaurants?select=id&status=eq.active")
all_ids = set(x["id"] for x in r.json())
r = get("/restaurant_cuisines?select=restaurant_id,cuisine_id&limit=2000")
tagged = set(x["restaurant_id"] for x in r.json())
untagged = all_ids - tagged
print(f"  有菜系标签: {len(tagged)}/{active}")
print(f"  无任何菜系标签: {len(untagged)}")
for rid in list(untagged)[:10]:
    rn = get(f"/restaurants?select=name&id=eq.{rid}").json()
    if rn:
        print(f"    #{rid} {rn[0]['name']}")

# 8. 数据新鲜度
print(f"\n【数据新鲜度】")
r = get("/restaurants?select=id,name,data_updated_at&status=eq.active&order=data_updated_at.asc&limit=5")
oldest = r.json()
print(f"  最久未更新5家:")
for x in oldest:
    print(f"    #{x['id']} {x['name'][:25]:25s} updated={x.get('data_updated_at')}")

# 9. 关店但还在推荐的
print(f"\n【关店数据】")
r = get("/restaurants?select=id,name,closed_date,closed_source&status=eq.closed&limit=20")
closed_list = r.json()
no_source = [x for x in closed_list if not x.get("closed_source")]
print(f"  关店总数: {closed}")
print(f"  关店但无来源依据: {len(no_source)}")

print("\n" + "=" * 60)
print("审计完成")
