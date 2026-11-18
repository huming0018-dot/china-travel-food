"""Conservative hours parser and gate policy; no network or model calls."""
import datetime as dt
import json
import re

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

def parse_hours(raw):
    # Never infer weekdays, exceptions, last order, or reservation hours.
    if not isinstance(raw, str):
        return None
    m = re.fullmatch(r'\s*(?:每天|每日|周一至周日|Monday-Sunday|Mo-Su)\s*[:：]?\s*(\d{1,2}:\d{2})\s*[-–至]\s*(\d{1,2}:\d{2})\s*', raw)
    if not m:
        return None
    def clock(s):
        h, n = map(int, s.split(':'))
        if not (0 <= h <= 24 and 0 <= n < 60 and (h != 24 or n == 0)):
            raise ValueError('clock')
        return f'{h:02d}:{n:02d}'
    try:
        a, b = clock(m[1]), clock(m[2])
    except ValueError:
        return None
    if a == b or a == '24:00':
        return None
    return {'timezone': 'Asia/Shanghai', 'weekly': [
        {'day': d, 'opens': a, 'closes': b, 'overnight': b < a} for d in DAYS],
        'exceptions': [], 'exceptions_status': 'not_provided'}

def evidence(raw, url, platform, identity, captured_at=None):
    parsed = parse_hours(raw)
    if not parsed:
        return None
    return {'raw': raw, 'parsed': parsed, 'source_url': url,
            'source_platform': platform, 'identity': identity,
            'captured_at': captured_at or dt.datetime.now(dt.timezone.utc).isoformat(),
            'parser_version': 'hours-v1', 'conflict_record': {'decision': 'fill_null_only'}}

def resolve(rows, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    candidates = []
    for row in rows:
        v = row.get('value')
        if not isinstance(v, dict) or v.get('parser_version') != 'hours-v1':
            continue
        if v.get('source_platform') not in ('official_restaurant', 'official_hotel', 'official_mall', 'licensed_merchant'):
            continue
        if row.get('source_url') != v.get('source_url') or not str(v.get('source_url', '')).startswith('https://'):
            continue
        if v.get('identity') != 'exact_name_and_address' or v.get('parsed') != parse_hours(v.get('raw')) or not v.get('parsed'):
            continue
        try:
            age = now - dt.datetime.fromisoformat(v['captured_at'])
            if age.total_seconds() < 0 or age > dt.timedelta(days=30):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if float(row.get('confidence') or 0) < .8:
            continue
        candidates.append(v)
    signatures = {json.dumps(v['parsed'], sort_keys=True) for v in candidates}
    if len(signatures) > 1:
        return {'action': 'hold', 'value': None, 'why': '营业时间可信来源冲突，保持缺失'}
    if not candidates:
        return {'action': 'hold', 'value': None, 'why': '营业时间缺少新鲜结构化同店证据；旧 raw 不自动晋升'}
    chosen = max(candidates, key=lambda v: v['captured_at'])
    return {'action': 'apply', 'value': chosen, 'why': '同店可溯源营业时间，仅填 NULL'}
