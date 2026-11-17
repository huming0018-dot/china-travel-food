"""Offline contract checks. Run from cloud: python -m unittest -v test_entity_matching_boundary."""
import builtins
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

PIPE = Path(__file__).resolve().parent / 'vendor' / 'pipeline'
if not PIPE.exists():  # standalone review bundle
    PIPE = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))
import entity_matching as core
import entity_match as adapter

ROWS = [
    {'id': 'a', 'name': '青松饭馆（美罗城店）', 'status': 'active', 'address': '天钥桥路100号'},
    {'id': 'b', 'name': '青松饭馆（环球港店）', 'status': 'active', 'address': '中山北路200号'},
    {'id': 'c', 'name': '明月小馆', 'status': 'active'},
]

class BoundaryTests(unittest.TestCase):
    def test_no_database_import_for_core_or_compatibility(self):
        code = """
import builtins, sys
original = builtins.__import__
def guarded(name, *a, **kw):
    if name in ('common', 'requests'):
        raise AssertionError('unexpected IO dependency: ' + name)
    return original(name, *a, **kw)
builtins.__import__ = guarded
import entity_matching, entity_match
assert entity_matching.EntityIndex([]).match_id('missing') is None
assert entity_match.EntityIndex is entity_matching.EntityIndex
"""
        subprocess.run([sys.executable, '-c', code], cwd=PIPE, check=True)

    def test_branch_resolution_and_roundup(self):
        idx = core.EntityIndex(ROWS)
        self.assertEqual(idx.match_id('青松饭馆（美罗城店）'), 'a')
        self.assertEqual(idx.disambiguate({'a', 'b'}, [], '在中山北路200号吃饭'), ('b', '正文地址'))
        self.assertEqual(idx.disambiguate({'a', 'b'}, [], ''), (None, '多分店待核'))
        self.assertEqual(idx.anchor_note({'title': '美食合集', 'desc': '青松饭馆和明月小馆都好吃'}, '明月小馆'), (None, '合集'))
        self.assertEqual(idx.anchor_note({'desc': '商家：明月小馆\n鲜嫩好吃'}, '其他'), ('c', '显式商家'))

    def test_compatibility_and_lazy_cache(self):
        calls = []
        fake = types.ModuleType('common')
        fake.fetch_all = lambda *args: calls.append(args) or ROWS
        adapter._INDEX = None
        try:
            with patch.dict(sys.modules, {'common': fake}):
                first = adapter.get_index()
                self.assertIs(adapter.get_index(), first)
                self.assertIsNot(adapter.get_index(force=True), first)
            self.assertEqual(calls, [('restaurants', 'id,name,status,district,address')] * 2)
            for name in ('SQ', 'strip_branch', 'MALLS', 'clean_content', 'taste_sent', 'is_question', 'EntityIndex'):
                self.assertIs(getattr(adapter, name), getattr(core, name))
        finally:
            adapter._INDEX = None

    def test_real_converter_writes_review_offline(self):
        fake = types.ModuleType('common')
        fake.fetch_all = lambda *a: ROWS
        fake.quote_has_substance = lambda body: True  # database/domain adapter boundary only
        adapter._INDEX = None
        original_open = builtins.open
        with tempfile.TemporaryDirectory() as td:
            data = Path(td)
            xdir = data / 'research/atlas/xhs'
            xdir.mkdir(parents=True)
            record = {'name': '明月小馆', 'notes': [{'title': '明月小馆', 'desc': '明月小馆的鱼肉鲜嫩好吃', 'author': '甲', 'url': 'fixture://note', 'date': '2026-01-02'}]}
            (xdir / 'raw_xhs.jsonl').write_text(json.dumps(record), encoding='utf-8')
            def local_open(path, *args, **kwargs):
                if str(path) == '/tmp/xhs_to_reviews.lock':
                    path = data / 'test.lock'
                return original_open(path, *args, **kwargs)
            with patch.dict(sys.modules, {'common': fake}), patch.dict(os.environ, {'FOOD_DATA_DIR': td}), patch('builtins.open', local_open):
                ns = runpy.run_path(str(PIPE / 'xhs_to_reviews.py'), run_name='__main__')
                ns['_lk'].close()
            rows = [json.loads(line) for line in (xdir / 'raw_reviews.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['restaurant_id'], 'c')
            self.assertEqual(rows[0]['visit_date'], '2026-01-02')
            self.assertEqual((xdir / 'unmatched_shops.jsonl').read_text(), '')
        adapter._INDEX = None

if __name__ == '__main__':
    unittest.main()
