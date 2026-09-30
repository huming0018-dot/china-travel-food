#!/usr/bin/env python3
# batch5_fill.py — 确定性填充 restaurants.selling_points（+ 保守补 fact_claims 候选）
# 规则：只用库内已采证据（signature_dishes / evidence_summary quotes / restaurant_awards / reviews），
#       不联网、不臆造；point 文案均为库内已有菜名/权威获奖信息/已写定的语义描述原句。
# 用法：容器内  python3 batch5_fill.py            # dry-run
#               python3 batch5_fill.py --apply   # 写库 + 回读
import argparse, json, os, re, sys
sys.path.insert(0, '/app/pipeline')
import common as C

# ---------- 拉全量 ----------
rests = C.fetch_all('restaurants',
    'id,name,status,selling_points,fact_claims,signature_dishes,evidence_summary,'
    'semantic_description,chain_type,central_kitchen,premade_risk,food_safety', page=1000)
awards = C.fetch_all('restaurant_awards',
    'restaurant_id,award_type,level,year,is_current,source_url,source_name', page=1000)
reviews = C.fetch_all('reviews', 'restaurant_id,source_url', page=1000)

aw_by = {}
for a in awards:
    if a.get('is_current'):
        aw_by.setdefault(a['restaurant_id'], []).append(a)
rv_by = {}
for x in reviews:
    if x.get('source_url'):
        rv_by.setdefault(x['restaurant_id'], []).append(x['source_url'])

# ---------- 工具 ----------
GENERIC_DISH = re.compile(r'(套餐|创意料理|无国界|融合菜|菜系|料理店|餐厅$)')
# 非菜品词（服务形式/环境/递菜方式）——招牌菜字段历史混入
NON_DISH = re.compile(r'(递菜|木桨|氛围|环境|服务|夜景|打卡|拍照)')
PLACEHOLDER_URL = re.compile(r'(dianping\.com/?$|trip\.com/?$|meituan\.com/?$|dianping\.com/search|^https?://[^/]+/?$)')

def parse_quotes(ev):
    try:
        d = json.loads(ev or '')
        if isinstance(d, dict) and isinstance(d.get('quotes'), list):
            return [q for q in d['quotes'] if isinstance(q, dict)]
    except Exception:
        pass
    return []

def repair_dishes(sd):
    """修复 ['["品鉴套餐"', '"无国界料理"]'] 这类片段数组。"""
    if not sd:
        return []
    frag = [d for d in sd if isinstance(d, str) and (d.startswith('[') or d.endswith(']')
            or (d.startswith('"') and d.endswith('"')))]
    if frag and len(frag) == len(sd):
        blob = ''.join(frag)
        try:
            v = json.loads(blob)
            if isinstance(v, list):
                return [str(x) for x in v]
        except Exception:
            pass
    return [str(d) for d in sd]

def clean_dishes(dishes):
    out = []
    for d in dishes:
        d = d.strip().strip('"').strip()
        if len(d) < 2:
            continue
        if GENERIC_DISH.search(d) or NON_DISH.search(d):
            continue
        out.append(d)
    return out

def award_point(a):
    t = a.get('award_type'); lv = a.get('level') or ''; yr = a.get('year') or ''
    if t == 'michelin_star':
        point = f'米其林{lv}（{yr}）'
    elif t == 'black_pearl':
        point = f'黑珍珠{lv}（{yr}）'
    elif t == 'bib_gourmand':
        point = f'米其林必比登推介（{yr}）'
    else:
        return None
    return point

# experience 抽取：在 semantic_description / evidence_summary 文本里找已写定的原句片段
EXP_RULES = [
    (re.compile(r'板前[^，。；]{0,8}席[^，。；]{0,6}'), 'experience'),
    (re.compile(r'仅约?[一二两三四五六七八九十\d]{1,3}\s*席'), 'experience'),
    (re.compile(r'吧台[^，。；]{0,8}(席|位)[^，。；]{0,4}'), 'experience'),
    (re.compile(r'[Oo]makase|OMAKASE'), 'experience'),
    (re.compile(r'预约制|需预约|接受预订?|须订位'), 'experience'),
    (re.compile(r'夜宵|深夜食堂|营业至\s*\d{1,2}\s*点'), 'experience'),
    (re.compile(r'露[台天][^，。；]{0,6}|景观位|屋顶[^，。；]{0,4}|江景'), 'atmosphere'),
    (re.compile(r'备长炭|炭火现烤|现杀现烤?|现点现[炒做]|每日空运|当天现[杀拆做]'), 'technique'),
]

def normalize_point(clause):
    cl = clause.strip()
    if re.fullmatch(r'[Oo]makase|OMAKASE', cl):
        return '主厨 Omakase 套餐'
    if cl in ('预约制', '需预约', '接受预订', '接受预定', '须订位'):
        return '需预约订位'
    if cl in ('夜宵', '深夜食堂'):
        return '夜宵/深夜营业'
    return cl

def extract_exp(text, quotes):
    """返回 [(point_text, type, source_url)]"""
    if not text:
        return []
    found = []
    used = set()
    for rx, typ in EXP_RULES:
        m = rx.search(text)
        if not m:
            continue
        clause = m.group(0).strip('，。；、 ')
        if len(clause) < 2 or clause in used:
            continue
        used.add(clause)
        # 找来源：该片段是否出现在某条 quote 原文里
        url = None
        for q in quotes:
            if clause in (q.get('quote') or ''):
                url = q.get('url'); break
        found.append((normalize_point(clause), typ, url))
    return found

# ---------- 构建 plan ----------
plan = []
for r in rests:
    rid = r['id']
    if r.get('selling_points'):   # 幂等：已有内容跳过
        continue
    quotes = parse_quotes(r.get('evidence_summary'))
    quote_urls = [q['url'] for q in quotes if q.get('url')]
    rev_urls = rv_by.get(rid, [])
    first_url = (quote_urls + rev_urls + [None])[0]

    points = []
    seen = set()
    # 1) signature dishes（最多2条）
    dishes = clean_dishes(repair_dishes(r.get('signature_dishes')))
    for d in dishes[:2]:
        points.append({'point': d, 'type': 'signature_dish', 'source_url': first_url})
        seen.add(d)
    # 2) award（1条）
    for a in aw_by.get(rid, []):
        p = award_point(a)
        if p and p not in seen:
            points.append({'point': p, 'type': 'award',
                           'source_url': a.get('source_url') or first_url})
            seen.add(p)
            break
    # 3) experience（最多2条）
    text = (r.get('semantic_description') or '')
    for clause, typ, url in extract_exp(text, quotes)[:2]:
        if clause not in seen:
            points.append({'point': clause, 'type': typ, 'source_url': url or first_url})
            seen.add(clause)
    points = points[:5]
    if points:
        plan.append({'id': rid, 'name': r['name'], 'points': points,
                     'n_quotes': len(quotes), 'n_reviews': len(rev_urls)})

# ---------- fact_claims 候选（保守：仅方向与列值一致、URL 为真实文章） ----------
CLAIM_RX = [
    (re.compile(r'(全国[^，。；]{0,10}(连锁|门店)|连锁品牌|上海[^，。；]{0,6}(多)?分店|\d+\s*家门店)'), 'chain_type'),
    (re.compile(r'(没有?预制|不做预制|无预制菜|拒绝预制|料包)'), 'premade_risk'),
    (re.compile(r'(中央厨房|中央工厂|加工中心)'), 'central_kitchen'),
]
MEDIA_HOST = re.compile(r'(timeoutshanghai|36kr|news\.cn|xinhuanet|sina\.|timeouts\.com)')

claim_plan = []
for r in rests:
    rid = r['id']
    existing = {(c.get('type'), c.get('source_url')) for c in (r.get('fact_claims') or [])}
    cols = {'chain_type': r.get('chain_type'), 'central_kitchen': r.get('central_kitchen'),
            'premade_risk': r.get('premade_risk'), 'food_safety': r.get('food_safety')}
    added = []
    for q in parse_quotes(r.get('evidence_summary')):
        qt = q.get('quote') or ''; url = q.get('url') or ''
        if not url or PLACEHOLDER_URL.search(url):
            continue
        for rx, ctype in CLAIM_RX:
            if not rx.search(qt):
                continue
            val = cols.get(ctype)
            if not val or val == '无' and ctype != 'food_safety':
                continue
            if ctype == 'premade_risk' and val not in ('低',):
                continue
            if ctype == 'central_kitchen' and val != '无':
                continue  # UGC 说"不预制"只支持'无'方向；'确认'方向已有权威流程
            if ctype == 'chain_type' and val not in ('小型连锁',):
                continue  # UGC 泛泛说连锁，只对小型连锁补证
            key = (ctype, url)
            if key in existing:
                continue
            conf = 'medium' if MEDIA_HOST.search(url) else 'low'
            added.append({'type': ctype, 'value': val, 'confidence': conf,
                          'date': q.get('date') or '', 'source_url': url,
                          'quote': qt[:200]})
    if added:
        merged = list(r.get('fact_claims') or []) + added
        claim_plan.append({'id': rid, 'name': r['name'], 'add': added,
                           'merged_len': len(merged)})

# ---------- 输出 ----------
print(f'=== selling_points plan: {len(plan)} 店待写 ===')
from collections import Counter
tc = Counter(p['type'] for x in plan for p in x['points'])
print('point type 分布:', dict(tc))
nopoint = 1482 - len(plan)
print('无点可写（证据为空）店数:', nopoint)
for x in plan[:12]:
    print(f"  id={x['id']} {x['name']}")
    for p in x['points']:
        print(f"     - [{p['type']}] {p['point']}  <{p['source_url']}>")
# 无URL样例
no_url = [x for x in plan if not any(p['source_url'] for p in x['points'])]
print('完全无 source_url 的店数:', len(no_url))

print()
print(f'=== fact_claims 候选: {len(claim_plan)} 店 ===')
for x in claim_plan:
    print(f"  id={x['id']} {x['name']} -> +{len(x['add'])} claims")
    for c in x['add']:
        print(f"     - {c['type']}={c['value']} ({c['confidence']}) {c['source_url']}")
        print(f"       quote: {c['quote'][:120]}")

if '--apply' in sys.argv or os.environ.get('BATCH5_APPLY') == '1':
    print('\n=== APPLY selling_points ===')
    for x in plan:
        body = {'selling_points': x['points']}
        resp = C.req('PATCH', f"/restaurants?id=eq.{x['id']}", json=body)
        resp.raise_for_status()
    got = C.fetch_all('restaurants', 'id,selling_points', page=1000)
    nonempty = [g for g in got if g.get('selling_points')]
    print(f'回读：selling_points 非空店数 = {len(nonempty)} / {len(got)}')
    print('样例:', json.dumps(nonempty[0]['selling_points'], ensure_ascii=False)[:300])

    print('\n=== APPLY fact_claims candidates（仅方向保守集合）===')
    for x in claim_plan:
        cur = C.fetch_all('restaurants', 'id,fact_claims', extra=f"id=eq.{x['id']}")[0]
        merged = (cur.get('fact_claims') or []) + x['add']
        resp = C.req('PATCH', f"/restaurants?id=eq.{x['id']}", json={'fact_claims': merged})
        resp.raise_for_status()
        print(f"  ✓ id={x['id']} {x['name']} claims -> {len(merged)}")
    got2 = C.fetch_all('restaurants', 'id,fact_claims', page=1000)
    fc_rows = [g for g in got2 if g.get('fact_claims')]
    print(f'回读：fact_claims 有主张店数 = {len(fc_rows)}, 总条数 = {sum(len(g["fact_claims"]) for g in fc_rows)}')
