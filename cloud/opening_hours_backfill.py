#!/usr/bin/env python3
"""Bounded, opt-in hours acquisition. Findings only; gate_apply owns DB writes."""
import argparse
import collections
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import requests
from hours_evidence import evidence

sys.path.insert(0, os.environ.get('FOOD_PIPELINE_DIR', '/app/pipeline'))
DATA = Path(os.environ.get('FOOD_DATA_DIR', '/app/data'))
UA = 'FoodAtlasHours/1.0'

def gaps(row):
    return [f for f in ('phone', 'price_avg', 'opening_hours', 'location')
            if row.get(f) is None or (f == 'phone' and not str(row.get(f) or '').strip())]

def audit(rows):
    active = [r for r in rows if r.get('status') == 'active']
    queue = [r for r in active if gaps(r)]
    hours = sum(r.get('opening_hours') is None for r in queue)
    return {'active': len(active), 'map_queue': len(queue), 'hours_missing': hours,
            'hours_fraction_in_queue': hours / len(queue) if queue else None,
            'patterns': dict(collections.Counter('+'.join(gaps(r)) for r in queue)),
            'note': 'review_count excluded; null hours only; malformed non-null values require separate review'}

def approved(source):
    u = urlsplit(source.get('url', ''))
    return (u.scheme == 'https' and u.hostname == source.get('approved_host')
            and not u.username and not u.password and not u.query
            and (u.port is None or u.port == 443)
            and source.get('access_review') == 'approved'
            and bool(source.get('rights_basis')) and bool(source.get('reviewed_by'))
            and source.get('platform') in ('official_restaurant', 'official_hotel', 'official_mall', 'licensed_merchant'))

class Budget:
    def __init__(self, limit):
        self.limit, self.used = limit, 0
    def take(self):
        if self.used >= self.limit:
            raise RuntimeError('request_budget')
        self.used += 1

def fetch(url, budget):
    budget.take()
    started = time.monotonic()
    # Reviewed exact hosts only; no redirects, cookies, authentication, or retry.
    with requests.get(url, headers={'User-Agent': UA}, timeout=(4, 10),
                      allow_redirects=False, stream=True) as r:
        if r.status_code != 200:
            raise RuntimeError('http_' + str(r.status_code))
        body = bytearray()
        for chunk in r.iter_content(8192):
            body.extend(chunk)
            if len(body) > 512_000 or time.monotonic() - started > 20:
                raise RuntimeError('response_limit')
        return body.decode(r.encoding or 'utf-8', errors='replace')

def source_hours(rest, source, budget):
    if not approved(source):
        return None, 'access_not_reviewed'
    url = source['url']
    u = urlsplit(url)
    robots = RobotFileParser()
    robots.parse(fetch(f'https://{u.netloc}/robots.txt', budget).splitlines())
    delay = robots.crawl_delay(UA) or robots.crawl_delay('*') or 1
    if not robots.can_fetch(UA, url) or delay > 5:
        return None, 'robots_hold'
    time.sleep(max(1, delay))
    page = fetch(url, budget)
    # Pre-reviewed exact page block avoids taking hotel-wide/mall-wide hours.
    # Blocks and quotes must literally occur; machine does not compose prose.
    block = source.get('restaurant_block', '')
    raw = source.get('hours_quote', '')
    name, addr = rest.get('name') or '', rest.get('address') or ''
    if not (block and block in page and name and addr and name in block and addr in block and raw and raw in block):
        return None, 'identity_or_quote_hold'
    return evidence(raw, url, source['platform'], 'exact_name_and_address'), 'source_checked'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rows', help='offline JSON snapshot; otherwise current active DB rows')
    ap.add_argument('--sources', help='reviewed source manifest JSON list')
    ap.add_argument('--collect', action='store_true', help='opt-in network, default audit only')
    ap.add_argument('--apply', action='store_true', help='append findings only; never write restaurants')
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--max-requests', type=int, default=40)
    a = ap.parse_args()
    if not 1 <= a.limit <= 30 or not 1 <= a.max_requests <= 60 or (a.apply and not a.collect):
        ap.error('pilot limit 1..30, request cap 1..60; apply requires collect')
    if a.rows:
        rows = json.loads(Path(a.rows).read_text())
    else:
        import common as C
        rows = C.fetch_all('restaurants', 'id,name,status,address,phone,price_avg,opening_hours,location,is_curated', extra='status=eq.active')
    report = audit(rows)
    if not a.collect:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    sources = json.loads(Path(a.sources).read_text()) if a.sources else []
    registry = collections.defaultdict(list)
    for src in sources:
        if approved(src):
            registry[int(src['restaurant_id'])].append(src)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / '_hours.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = DATA / '_hours_state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        budget = Budget(a.max_requests)
        pending = [r for r in rows if r.get('status') == 'active' and r.get('opening_hours') is None and registry[r['id']]]
        pending.sort(key=lambda r: (-bool(r.get('is_curated')), -len(gaps(r)), r['id']))
        checked = accepted = 0
        for rest in pending:
            if checked >= a.limit or budget.used >= budget.limit:
                break
            rid = str(rest['id'])
            st = state.get(rid, {})
            if st.get('attempts', 0) >= 3 or st.get('next_at', 0) > time.time():
                continue
            checked += 1
            candidates, outcomes = [], []
            for src in registry[rest['id']][:2]:
                try:
                    value, status = source_hours(rest, src, budget)
                except (requests.RequestException, RuntimeError, ValueError):
                    value, status = None, 'request_failed_or_budget'
                outcomes.append({'url': src['url'], 'status': status})
                if value:
                    candidates.append(value)
            from hours_evidence import resolve
            dec = resolve([{'value': v, 'source_url': v['source_url'], 'confidence': .9} for v in candidates])
            if dec['action'] == 'apply':
                accepted += 1
                if a.apply:
                    import ingest
                    v = dec['value']
                    ingest.append_finding(rest['id'], 'opening_hours', v, .9,
                                          '可信来源精确同店；只补NULL', v['source_url'], v['source_platform'])
            state[rid] = {'attempts': st.get('attempts', 0) + 1,
                          'next_at': time.time() + 30 * 86400, 'decision': dec['action'],
                          'why': dec['why'], 'outcomes': outcomes}
            # Crash-safe checkpoint after every restaurant. dry-run also spends real requests.
            tmp = state_path.with_suffix('.tmp')
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            os.replace(tmp, state_path)
            with (DATA / 'hours_decisions.jsonl').open('a') as f:
                f.write(json.dumps({'rid': rest['id'], 'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                                    'mode': 'findings' if a.apply else 'dry_run',
                                    'decision': dec, 'outcomes': outcomes}, ensure_ascii=False) + '\n')
        report.update(checked=checked, candidate_hours=accepted, requests=budget.used,
                      mode='findings' if a.apply else 'dry_run', db_writes=0)
        print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
