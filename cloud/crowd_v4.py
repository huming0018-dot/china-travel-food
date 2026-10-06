#!/usr/bin/env python3
"""v4 operator entry: dry-run by default; reuses common_core. No task_queue fallback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def rpc(action, payload):
    import common_core as core  # Existing cloud dependency; dry-run/export helpers remain stdlib-only.
    url = core.config('NEXT_PUBLIC_SUPABASE_URL', '').rstrip('/')
    key = core.config('SUPABASE_SERVICE_ROLE_KEY', '')
    if not url.startswith('https://') or not url.endswith('.supabase.co') or not key:
        raise ValueError('Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the operator environment')
    try:
        response = core.req('POST', '/rpc/crowd_v4_admin', json={'p_action': action, 'p_payload': payload}, retries=1, timeout=30)
    except RuntimeError:
        raise RuntimeError(f'Backend connection failed: {action}') from None
    if not response.ok:
        raise RuntimeError(f'Backend rejected {action}: HTTP {response.status_code}')
    return response.json()


def tasks(records, target=5, city='上海'):
    for item in records:
        if isinstance(item, str): item = {'name': item}
        name = (item.get('name') or item.get('store_name') or '').strip()
        if not 2 <= len(name) <= 100: raise ValueError('Each task requires a store name (2–100 characters)')
        query = item.get('query') or f'{city} {name}'
        if not 2 <= len(query) <= 120: raise ValueError('Invalid query')
        restaurant_id = item.get('restaurant_id')
        # Exact name/known branch identity, never a random pack sequence.
        identity = json.dumps([query, restaurant_id], ensure_ascii=False, separators=(',', ':'))
        yield {'source_key': 'need_ugc:' + hashlib.sha256(identity.encode()).hexdigest(), 'query': query,
               'store_name': name, 'restaurant_id': restaurant_id, 'anchor_terms': item.get('anchor_terms') or [name], 'target': target}


def load(path):
    text = Path(path).read_text(encoding='utf-8')
    if Path(path).suffix == '.jsonl': return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict): data = data.get('stores', data.get('shops'))
    if not isinstance(data, list): raise ValueError('Input must be a JSON array or JSONL')
    return data


def atomic(path, text):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def export(path):
    path = Path(path)
    existing = {x['proof_id']: x for x in load(path)} if path.exists() else {}
    # Re-fetching verified records is idempotent and repairs gaps after delayed reviews.
    after, count = 0, 0
    while True:
        incoming = rpc('export', {'after_id': after})
        if not incoming: break
        existing.update({x['proof_id']: x for x in incoming}); count += len(incoming)
        after = max(x['proof_id'] for x in incoming)
    atomic(path, ''.join(json.dumps(existing[key], ensure_ascii=False) + '\n' for key in sorted(existing)))
    return {'exported': count, 'total': len(existing)}


def verified_pages(name, path):
    """Evidence input for build_bridge; original text, never participant ratings."""
    if not Path(path).exists(): return [], []
    pages, urls = [], []
    for proof in load(path):
        if proof.get('store_name') != name: continue
        record = proof.get('record', {})
        text = record.get('evidence', {}).get('text', '')
        quote = proof.get('verified_quote')
        url = record.get('standard', {}).get('url', '')
        if not quote or quote not in text or not proof.get('source_checked_at') or not url.startswith('https://www.xiaohongshu.com/explore/'): continue
        if url in urls: continue
        pages.append(f'【众包已核验证据 {url}】\n{text}')
        urls.append(url)
        if len(urls) == 6: break
    return pages, urls


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    publish = sub.add_parser('publish'); publish.add_argument('file'); publish.add_argument('--city', default='上海'); publish.add_argument('--target', type=int, default=5)
    publish.add_argument('--apply', action='store_true')
    admin = sub.add_parser('admin'); admin.add_argument('action', choices=['approve','suspend','review','pay','list']); admin.add_argument('--payload-file', required=True); admin.add_argument('--apply', action='store_true')
    out = sub.add_parser('export'); out.add_argument('file')
    cycle = sub.add_parser('cycle'); cycle.add_argument('--directory', type=Path, default=Path(os.environ.get('FOOD_DATA_DIR', '/app/data')) / 'coverage'); cycle.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.command == 'publish':
        if not 1 <= args.target <= 20: ap.error('--target must be 1–20')
        payloads = list(tasks(load(args.file), args.target, args.city))
        if args.apply:
            for payload in payloads: rpc('publish', payload)
            print(json.dumps({'processed':len(payloads)}))
        else: print(json.dumps(payloads, ensure_ascii=False, indent=2))
    elif args.command == 'admin':
        payload = json.loads(Path(args.payload_file).read_text(encoding='utf-8'))
        if args.apply or args.action == 'list': print(json.dumps(rpc(args.action, payload), ensure_ascii=False, indent=2))
        else: print(json.dumps({'action':args.action,'payload':payload,'dry_run':True}, ensure_ascii=False, indent=2))
    elif args.command == 'export': print(json.dumps(export(args.file)))
    else:
        source = args.directory / 'need_ugc.jsonl'
        payloads = list(tasks(load(source))) if source.exists() else []
        if not args.apply:
            print(json.dumps({'tasks': payloads, 'export_file': str(args.directory / 'crowd_v4_verified.jsonl'), 'dry_run': True}, ensure_ascii=False)); return
        for payload in payloads: rpc('publish', payload)
        report = export(args.directory / 'crowd_v4_verified.jsonl'); report['processed_tasks'] = len(payloads)
        print(json.dumps(report))


if __name__ == '__main__': main()
