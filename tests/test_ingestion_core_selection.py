"""Offline selection evidence. Expected failures document defects, not fixes."""
import contextlib
import copy
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PIPELINE = Path(__file__).resolve().parents[1] / 'cloud/vendor/pipeline'
sys.path.insert(0, str(PIPELINE))
# Never read the developer's configured env file while importing the real common.
with tempfile.TemporaryDirectory() as empty, patch.dict(os.environ, {'FOOD_APP_DIR': empty}, clear=True):
    import common as C
    import stage1_validate as V
    import stage2_prepare as P
    import stage3_upsert as W


def raw_place():
    return {
        'name': '验收面馆', 'district': '徐汇区', 'address': '测试路100号一层',
        'price_avg': 60, 'form': '快餐简餐', 'signature_dishes': ['牛肉面', '煎饺'],
        'cuisine_paths': [['中餐', '川菜']], 'status': 'open',
        'lat': 31.2, 'lng': 121.4, 'phone_raw': None,
        'scores': {'objective': 80, 'diner': 70, 'taste': 90, 'endorsement': 60, 'soft_ad_penalty': 5},
        'evidence_summary': '牛肉面汤香面韧，煎饺外皮酥脆。' * 20,
        'evidence': {'diner_quotes': [
            {'source': '小红书', 'url': 'https://www.xiaohongshu.com/explore/a', 'quote': '牛肉面汤香面韧，煎饺外皮酥脆。'},
            {'source': '大众点评', 'url': 'https://www.dianping.com/shop/b', 'quote': '牛肉炖得软烂，面条仍有弹性。'}],
            'platform_scores': [{'platform':'点评', 'score':4.2, 'review_count':100}],
            'negative_signals':['排队时间长']},
        'sources': [{'title':'食客记录', 'url':'https://www.dianping.com/shop/b'},
                    {'title':'地址', 'url':'https://amap.com/place/c'}],
    }


TAGS = [
    {'id':1, 'name':'川菜', 'dimension':'菜系', 'parent_category':'中餐'},
    {'id':2, 'name':'快餐/简餐', 'dimension':'形式', 'parent_category':'正餐'},
    {'id':3, 'name':'午餐', 'dimension':'时段', 'parent_category':None},
    {'id':4, 'name':'晚餐', 'dimension':'时段', 'parent_category':None},
]


class IngestionSelection(unittest.TestCase):
    def setUp(self):
        # Fail on unexpected external IO, including adapter calls outside fixtures.
        for target in ['requests.sessions.Session.request', 'socket.socket', 'common.req', 'common.fetch_all']:
            p = patch(target, side_effect=AssertionError('external IO forbidden'))
            p.start(); self.addCleanup(p.stop)

    def prepare(self, record, restaurants=()):
        def read_table(table, *args, **kwargs):
            return copy.deepcopy({'restaurants':list(restaurants), 'cuisines':TAGS}[table])
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/'accepted.jsonl', Path(d)/'plan.json'
            C.write_jsonl(src, [record])
            with patch.object(C, 'fetch_all', side_effect=read_table), patch.object(P.time, 'sleep'), \
                 patch.object(sys, 'argv', ['stage2_prepare', '-i', str(src), '-o', str(dst), '--no-geocode']), \
                 contextlib.redirect_stdout(io.StringIO()):
                P.main()
            return json.loads(dst.read_text())[0]

    def test_normal_validation_preparation_and_default_dry_run(self):
        errors, warnings, record = V.validate(raw_place())
        self.assertEqual(errors, [])
        self.assertEqual(record['status'], 'active')
        self.assertEqual(record['scores']['total'], 73.0)
        plan = self.prepare(record)
        self.assertEqual(plan['action'], 'new')
        self.assertEqual(plan['cids_add'], [1,2,3,4])
        self.assertEqual(plan['missing_tags'], [])
        self.assertEqual(plan['fields']['location'], 'SRID=4326;POINT(121.4 31.2)')
        self.assertNotIn('score_total', plan['fields'])
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/'plan.json'; src.write_text(json.dumps([plan]))
            output = io.StringIO()
            with patch.object(sys, 'argv', ['stage3_upsert', '-i', str(src)]), contextlib.redirect_stdout(output):
                W.main()
            self.assertIn('DRY-RUN', output.getvalue())
            self.assertEqual(len(list(Path(d).iterdir())), 1)

    def test_missing_name_rejected_and_conflict_not_written(self):
        errors, _, clean = V.validate({})
        self.assertIsNone(clean); self.assertIn('name 为空', errors)
        result = W.write_one({'name':'冲突店','action':'conflict','fields':{}}, False)
        self.assertEqual(result['action'], 'skipped_conflict')

    def test_exact_existing_name_address_updates(self):
        _, _, record = V.validate(raw_place())
        plan = self.prepare(record, [{'id':12,'name':record['name'],'address':record['address'],'district':record['district']}])
        self.assertEqual((plan['action'], plan['restaurant_id']), ('update',12))

    def writer(self, price=60):
        calls = []
        class Response:
            status_code = 200
            text = ''
            def __init__(self, data): self.data = data
            def json(self): return self.data
            def raise_for_status(self): pass
        def request(method, path, **kw):
            calls.append((method,path,kw))
            if method == 'POST' and path == '/restaurants': return Response([{'id':12}])
            if method == 'GET' and path.startswith('/restaurant_cuisines?'): return Response([{'cuisine_id':1}])
            if method == 'GET' and path.startswith('/restaurants?id=eq.12&'):
                return Response([{'id':12,'name':'验收面馆','price_avg':price,'tier':'平价','score_total':73,
                                  'score_objective':80,'score_diner':70,'score_taste':90,'score_endorsement':60}])
            raise AssertionError((method,path))
        with patch.object(C,'req',side_effect=request):
            result = W.write_one({'name':'验收面馆','action':'new','fields':{'name':'验收面馆','price_avg':60},'cids_add':[1]}, False)
        return result, calls

    def test_writer_normal_response_and_existing_tag_not_reinserted(self):
        result, calls = self.writer()
        self.assertTrue(result['ok']); self.assertEqual(result['rid'],12)
        self.assertEqual([m for m,p,k in calls], ['POST','GET','GET','GET'])
        self.assertEqual(result['rc_added'], [])

    @unittest.expectedFailure
    def test_known_defect_nonfinite_score_must_be_rejected(self):
        raw = raw_place(); raw['scores']['taste'] = float('nan')
        errors, _, clean = V.validate(raw)
        self.assertIsNone(clean, 'NaN bypasses comparisons; it must not be accepted')

    @unittest.expectedFailure
    def test_known_defect_same_district_is_not_same_branch(self):
        _, _, record = V.validate(raw_place())
        plan = self.prepare(record, [{'id':99,'name':record['name'],'address':'另一条路900号','district':record['district']}])
        self.assertNotEqual(plan['action'], 'update', 'same name/district can be a different branch')

    @unittest.expectedFailure
    def test_known_defect_readback_price_mismatch_must_fail(self):
        result, _ = self.writer(price=999)
        self.assertFalse(result['ok'], 'matching name and nonempty derived fields do not prove the write matched')


if __name__ == '__main__':
    unittest.main()
