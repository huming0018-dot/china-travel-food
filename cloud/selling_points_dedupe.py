#!/usr/bin/env python3
# 清理：同一店内 point 文本互为子串的，只保留更长那条（幂等）
import sys
sys.path.insert(0, '/app/pipeline')
import common as C

rows = C.fetch_all('restaurants', 'id,selling_points', page=1000)
fixed = 0
for r in rows:
    sp = r.get('selling_points')
    if not sp:
        continue
    pts = sorted(sp, key=lambda p: -len(p.get('point','')))
    keep = []
    for p in pts:
        t = p.get('point','')
        if any(t and t in k.get('point','') and t != k.get('point','') for k in keep):
            continue
        keep.append(p)
    if len(keep) != len(sp):
        C.req('PATCH', f"/restaurants?id=eq.{r['id']}", json={'selling_points': keep}).raise_for_status()
        fixed += 1
print('dedupe fixed rows:', fixed)
got = C.fetch_all('restaurants', 'id,selling_points', page=1000)
sp = [g for g in got if g.get('selling_points')]
print('readback selling_points non-empty:', len(sp), '/', len(got))
g1381 = C.fetch_all('restaurants', 'id,name,selling_points', extra='id=eq.1381')[0]
import json
print('1381:', json.dumps(g1381['selling_points'], ensure_ascii=False))
