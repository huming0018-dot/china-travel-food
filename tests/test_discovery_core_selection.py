"""Offline core appraisal; expected failures preserve known contract gaps."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PIPE = Path(__file__).resolve().parents[1] / 'cloud/vendor/pipeline'
sys.path.insert(0, str(PIPE))
with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FOOD_APP_DIR': d}, clear=True):
    import common as C
    import discovery_keywords as K
    import admission_gate as G
    import social_discovery as D
    import discovery_engine as E


def note(url='https://example.invalid/1', text='可颂好吃酥脆', commenter='食客甲'):
    return {'title': '面包记录', 'author': '整理甲', 'url': url,
            'desc': 'Proust Moment：' + text,
            'comments': [{'name': commenter, 'text': 'Proust Moment ' + text}]}


class DiscoveryCoreSelection(unittest.TestCase):
    def setUp(self):
        for target in ['requests.sessions.Session.request', 'socket.socket', 'common.fetch_all', 'common.req']:
            p = patch(target, side_effect=AssertionError('external IO forbidden'))
            p.start(); self.addCleanup(p.stop)

    def gate(self, notes):
        with tempfile.TemporaryDirectory() as d:
            raw, out = Path(d)/'raw.jsonl', Path(d)/'out.jsonl'
            raw.write_text(json.dumps({'kind':'discover', 'category':'bread', 'query':'面包', 'notes':notes}))
            with patch.object(C, 'fetch_all', return_value=[]), patch.object(sys, 'argv',
                    ['gate','--raw',str(raw),'--category','bread','--out',str(out)]), contextlib.redirect_stdout(io.StringIO()):
                G.main()
            return [json.loads(x) for x in out.read_text().splitlines()]

    def test_query_matrix_is_nonempty_deterministic_and_unique(self):
        for category in K.all_categories():
            words = K.build_queries(category)
            self.assertTrue(words)
            self.assertEqual(words, K.build_queries(category))
            self.assertEqual(len(words), len(set(words)))

    def test_normal_raw_to_candidate_and_compiler_only_hold(self):
        p = self.gate([note()])[0]
        self.assertTrue(p['verdict'].startswith('admit'))
        self.assertEqual(p['independent_sources'], 2)
        self.assertFalse(p['in_db'])
        n = note(); n['comments'] = []
        self.assertEqual(self.gate([n])[0]['verdict'], 'hold')

    def test_obviously_negative_candidate_rejected(self):
        self.assertEqual(self.gate([note(text='可颂难吃避雷失望')])[0]['verdict'], 'reject')

    def test_engine_records_raw_expands_and_resumes(self):
        with tempfile.TemporaryDirectory() as d, patch.object(E, '_seed_queries', return_value=['面包']), \
                patch.object(D, '_gather_one_query', return_value=[dict(note(), desc='月光面包店：可颂好吃')]), \
                contextlib.redirect_stdout(io.StringIO()):
            eng = E.DiscoveryEngine(None,'bread',d,use_db=False)
            rep = eng.run(max_queries=1)
            self.assertEqual(rep['processed'],1)
            self.assertIn('月光面包店',eng.state['frontier_high'])
            self.assertEqual(json.loads(eng.raw_path.read_text())['kind'],'discover')
            again = E.DiscoveryEngine(None,'bread',d,use_db=False)
            self.assertEqual(again.state['visited'],['面包'])

    def test_empty_searches_stall_not_complete(self):
        with tempfile.TemporaryDirectory() as d, patch.object(E,'_seed_queries',return_value=['一','二','三','四']), \
                patch.object(D,'_gather_one_query',return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            eng = E.DiscoveryEngine(None,'bread',d,use_db=False)
            rep = eng.run(max_queries=4)
            self.assertEqual(rep['status'],'stalled')
            self.assertEqual(rep['processed'],3)
            self.assertEqual(rep['frontier_remaining'],1)

    @unittest.expectedFailure
    def test_lead_merging_preserves_repeated_occurrences(self):
        self.assertEqual(G.merge_leads({'moonbakery':3})['moonbakery'],3)

    @unittest.expectedFailure
    def test_same_commenter_across_notes_is_not_independent_twice(self):
        p = self.gate([note(),note(url='https://example.invalid/2')])[0]
        self.assertEqual(p['independent_sources'],2)

    @unittest.expectedFailure
    def test_explicit_bad_taste_does_not_meet_admission_threshold(self):
        p = self.gate([note(text='可颂不好吃')])[0]
        self.assertFalse(p['verdict'].startswith('admit'))


if __name__ == '__main__':
    unittest.main()
