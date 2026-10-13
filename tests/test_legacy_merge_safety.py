"""Offline regression: no credentials, network or production data."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / 'cloud/vendor/pipeline'
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(ROOT / 'cloud'))
os.environ['FOOD_PIPELINE_DIR'] = str(PIPE)
import merge_duplicates as M
import cloud_patrol as P

ROWS = [dict(id=i, name='同牌餐厅', location=f'POINT({121 + i * .0006} 31)', status='active') for i in range(1, 4)]

class LegacySafety(unittest.TestCase):
    def test_commit_rejected_before_any_io(self):
        with patch.object(sys, 'argv', ['merge_duplicates.py', '--commit']), patch.object(M.C, 'fetch_all') as fetch, patch.object(M.C, 'req') as req:
            with self.assertRaises(SystemExit) as e:
                M.main()
            self.assertEqual(e.exception.code, 2)
            fetch.assert_not_called()
            req.assert_not_called()

    def test_partial_failure_cannot_start(self):
        # Even a transport configured to return failure must never be called.
        with patch.object(M.C, 'req', side_effect=RuntimeError('HTTP 500')) as req:
            for call in (lambda: M.migrate(2, 1, []), lambda: M.fill_master(ROWS[0], ROWS[1:], [])):
                with self.assertRaisesRegex(RuntimeError, 'disabled'):
                    call()
            req.assert_not_called()

    def test_false_single_link_and_keep_conflict_are_review_only(self):
        self.assertGreater(M.dist_m(M.ll(ROWS[0]), M.ll(ROWS[2])), 100)
        self.assertTrue(M.find_clusters(ROWS, 100))
        with tempfile.TemporaryDirectory() as d:
            report = str(Path(d) / 'review.json')
            with patch.object(sys, 'argv', ['merge_duplicates.py', '--report', report]), patch.object(M.C, 'fetch_all', return_value=ROWS), patch.object(M.C, 'req') as req, patch.object(M, 'child_rows', return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                M.main()
            data = json.loads(Path(report).read_text())
            self.assertFalse(data['executable'])
            self.assertEqual(data['status'], 'REVIEW_ONLY')
            self.assertIn('keep not adjudicated', data['candidate_rule'])
            self.assertTrue(data['plan'])
            req.assert_not_called()
        # A historical keep decision cannot be overridden: all writes reject it too.
        with self.assertRaises(RuntimeError):
            M.migrate(2, 1, ['historical keep: 1,2'])

    def test_patrol_apply_never_calls_deleter(self):
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['cloud_patrol.py', '--apply']))
            stack.enter_context(patch.object(P, 'PATROL_DIR', Path(d)))
            stack.enter_context(patch.object(P.C, 'fetch_all', side_effect=lambda table, *a, **k: ROWS if table == 'restaurants' else []))
            req = stack.enter_context(patch.object(P.C, 'req', side_effect=AssertionError('unexpected REST write')))
            stack.enter_context(patch.object(P, 'check_entities_full', return_value=(0, 0, [])))
            stack.enter_context(patch.object(P.PC, 'run', return_value=[]))
            stack.enter_context(patch.object(P, 'check_chefs', return_value=([], [])))
            stack.enter_context(patch.object(P, 'check_freshness', return_value=[]))
            stack.enter_context(patch.object(P, 'thin_profiles', return_value=[]))
            stack.enter_context(patch.object(P, 'load_state', return_value={}))
            stack.enter_context(patch.object(P, 'save_state'))
            stack.enter_context(patch.object(P.CW, 'scan', return_value={'closed_triple_missing': [], 'active_with_closed_signal': [], 'stale_active': []}))
            stack.enter_context(patch.dict(sys.modules, {'health': types.SimpleNamespace(alert=lambda *a: None)}))
            run = stack.enter_context(patch.object(P, 'run_script', return_value='offline'))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            P.main()
            self.assertTrue(run.called)
            self.assertFalse(any('merge_duplicates.py' in str(c) for c in run.call_args_list))
            req.assert_not_called()
            plan = json.loads((Path(d) / 'entity_review.json').read_text())
            self.assertFalse(plan['executable'])
            self.assertFalse(plan['keep_adjudicated'])
            self.assertTrue(plan['candidates'])

if __name__ == '__main__':
    unittest.main()
