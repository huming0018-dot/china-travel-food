"""Offline intake appraisal: real modules; network/browser/process boundaries isolated."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / 'cloud/vendor/pipeline'
sys.path[:0] = [str(ROOT/'cloud'), str(PIPE)]
with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {
        'FOOD_APP_DIR':d, 'FOOD_DATA_DIR':d, 'FOOD_PIPELINE_DIR':str(PIPE)}, clear=True):
    import common as C
    import candidate_apply as A
    import cloud_discover as D
    import cloud_ready as R
    import discovery_engine as E

POI = {'title':'月光面包店', 'address':'徐汇区测试路10号', 'biz_type':'diner',
       'lng':121.43, 'lat':31.19, 'cost':60, 'tel':'021-61234567'}
CANDIDATE = {'brand':'月光面包店', 'verdict':'admit*', 'in_db':False,
             'diner_voices':{'人甲':'可颂口感好'}, 'independent_sources':2}


class CandidateIntakeSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        for target in ['requests.sessions.Session.request','socket.socket','subprocess.run','common.req','common.fetch_all','common.headers']:
            self.start(patch(target,side_effect=AssertionError('external IO forbidden')))
        self.start(patch.object(A,'DISC_DIR',self.path))
        self.start(patch.object(A.AF,'AMAP_KEY','fixture-only'))
        self.start(patch.object(A.AF,'amap_text',return_value=[dict(POI)]))
        self.start(patch.object(C,'fetch_all',return_value=[{'id':4,'name':'面包'}]))
        self.start(patch.object(C,'req',return_value=Mock(json=lambda: [])))
        self.start(patch.object(C,'headers',return_value={}))
        self.start(patch.object(A.time,'sleep'))
        self.posts = []
        self.post_status = 201
        self.tag_status = 201
        self.start(patch('requests.post',side_effect=self.post))
        self.write_candidate(CANDIDATE)

    def start(self,p):
        r=p.start(); self.addCleanup(p.stop); return r

    def write_candidate(self,p):
        (self.path/'candidates_bread.jsonl').write_text(json.dumps(p))

    def post(self,url,**kw):
        self.posts.append((url,kw['json']))
        status = self.tag_status if url.endswith('/restaurant_cuisines') else self.post_status
        return Mock(status_code=status,text='fixture rejection' if status>=400 else '',json=lambda:[{'id':123}])

    def apply(self,commit=True):
        with patch.object(sys,'argv',['candidate_apply','--category','bread']+(['--commit'] if commit else [])), contextlib.redirect_stdout(io.StringIO()):
            return A.main()

    def discover(self):
        for name,value in [('DISC_DIR',self.path),('STATE_F',self.path/'state.json'),('RAW',self.path/'raw.jsonl')]:
            self.start(patch.object(D,name,value))
        self.start(patch.object(R,'open_ready_browser',return_value=(Mock(),'fixture')))
        self.start(patch.object(E.DiscoveryEngine,'__init__',return_value=None))
        self.start(patch.object(E.DiscoveryEngine,'run',return_value={'status':'saturated'}))
        self.start(patch.object(D.health,'alert'))
        def process(argv,**kwargs):
            # Gate output is the supplied fixture. Execute the actual apply main in-process;
            # its normal None return corresponds to Python script exit status 0.
            if Path(argv[1]).name == 'candidate_apply.py':
                with patch.object(sys,'argv',argv[1:]):
                    result=A.main()
                return subprocess.CompletedProcess(argv,0 if result is None else result)
            if Path(argv[1]).name != 'admission_gate.py':
                raise AssertionError(argv)
            return subprocess.CompletedProcess(argv,0)
        with patch.object(D.subprocess,'run',side_effect=process), patch.object(sys,'argv',['cloud_discover','--category','bread']), contextlib.redirect_stdout(io.StringIO()):
            D.main()
        return json.loads(D.STATE_F.read_text())

    def test_normal_commit_posts_restaurant_then_cuisine(self):
        self.apply()
        self.assertEqual(len(self.posts),2)
        self.assertEqual(self.posts[0][1]['name'],'月光面包店')
        self.assertEqual(self.posts[0][1]['price_avg'],60)
        self.assertEqual(self.posts[1][1],{'restaurant_id':123,'cuisine_id':4})

    def test_dry_run_has_no_database_writes(self):
        self.apply(commit=False); self.assertEqual(self.posts,[])

    def test_no_diner_hold_and_existing_record_do_not_insert(self):
        self.write_candidate(dict(CANDIDATE,diner_voices={}))
        self.apply(); self.assertEqual(self.posts,[])
        self.write_candidate(CANDIDATE)
        with patch.object(C,'req',return_value=Mock(json=lambda:[{'id':9,'address':POI['address']}])):
            self.apply()
        self.assertEqual(self.posts,[])

    def test_failed_insert_does_not_write_cuisine(self):
        self.post_status=500; self.apply()
        self.assertEqual(len(self.posts),1)

    def test_normal_consumer_closure(self):
        state=self.discover()
        self.assertIn('bread',state['done']); self.assertEqual(len(self.posts),2)

    @unittest.expectedFailure
    def test_failed_insert_must_not_complete_category(self):
        self.post_status=500
        self.assertNotIn('bread',self.discover()['done'])

    @unittest.expectedFailure
    def test_missing_key_must_not_complete_category(self):
        with patch.object(A.AF,'AMAP_KEY',''):
            self.assertNotIn('bread',self.discover()['done'])

    @unittest.expectedFailure
    def test_failed_tag_must_not_complete_category(self):
        self.tag_status=500
        self.assertNotIn('bread',self.discover()['done'])

    @unittest.expectedFailure
    def test_retry_after_failed_tag_repairs_the_missing_tag(self):
        self.tag_status=500
        self.apply()
        self.tag_status=201
        with patch.object(C,'req',return_value=Mock(json=lambda:[{'id':123,'address':POI['address']}])):
            self.apply()
        self.assertEqual(sum(url.endswith('/restaurant_cuisines') for url,_ in self.posts),2)

    @unittest.expectedFailure
    def test_equal_high_scoring_branches_are_ambiguous(self):
        other=dict(POI,address='徐汇区另一条路20号',title='月光面包店（西店）')
        self.assertEqual(A.pick_new_poi([dict(POI,title='月光面包店（东店）'),other],'月光面包店'),'AMBIG')

    @unittest.expectedFailure
    def test_yield_result_is_handled_without_crashing(self):
        with patch.object(A.AF,'amap_text',return_value='YIELD'):
            self.apply()
        self.assertEqual(self.posts,[])


if __name__ == '__main__':
    unittest.main()
