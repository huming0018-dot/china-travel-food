#!/usr/bin/env python3
"""Legacy caller adapter to v4. No task_queue fallback and no participant ratings."""
import argparse
import json
from pathlib import Path
from crowd_v4 import tasks, rpc


def publish(pack_items, pack_size=6, target='notes', kpi_min=5, quota_day=20, source='qa', pack_type=None):
    if target == 'review': raise ValueError('Participant ratings were removed in v4')
    created = []
    for payload in tasks(pack_items, target=kpi_min):
        payload['source_key'] = source + ':' + payload['source_key']
        if pack_type == 'keyword': payload['store_name'] = None
        result = rpc('publish', payload)
        created.append({'task_id': result['id'], 'table': 'crowd_v4.tasks'})
    return created


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stores'); ap.add_argument('--keywords'); ap.add_argument('--kpi',type=int,default=5)
    ap.add_argument('--pack-size',type=int,default=6); ap.add_argument('--quota',type=int,default=20)
    ap.add_argument('--target',choices=['notes','both'],default='notes'); ap.add_argument('--apply',action='store_true')
    args=ap.parse_args(); path=args.stores or args.keywords
    if not path: ap.error('--stores or --keywords required')
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(data,dict): data=data.get('stores') or data.get('keywords')
    if args.apply: print(json.dumps(publish(data,kpi_min=args.kpi,pack_type='store' if args.stores else 'keyword')))
    else: print(json.dumps(list(tasks(data,target=args.kpi)),ensure_ascii=False,indent=2))
