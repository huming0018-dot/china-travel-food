"""Retired entrypoints cannot resume workers or candidate commits."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'cloud'),str(ROOT/'cloud/vendor/pipeline')]
with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'FOOD_APP_DIR':d,'FOOD_DATA_DIR':d},clear=True):
    import gap_runner as G
    import gap_pool as P
    import account_repair as A
    import cloud_router as R
    import pm_night_watch as N


class AutoIntakeRetirement(unittest.TestCase):
    def setUp(self):
        for t in ['requests.sessions.Session.request','socket.socket','subprocess.Popen','subprocess.run']:
            p=patch(t,side_effect=AssertionError('external IO forbidden'));p.start();self.addCleanup(p.stop)

    def test_runner_and_pool_report_paused_without_launching(self):
        with contextlib.redirect_stderr(io.StringIO()) as out:
            self.assertEqual(G.main(),2)
            self.assertEqual(P.main(),2)
        self.assertIn('已暂停',out.getvalue())
        for removed in ['run_category','worker_loop','auto_gate_apply','claim_next_category']:
            self.assertFalse(hasattr(G,removed))

    def test_seed_plan_is_still_consumable(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'plan.json'
            f.write_text(json.dumps([{'id':1,'name':'甲','lineage':[], 'queries':{'xhs':['词甲','词乙']}},
                                     {'id':2,'name':'乙','lineage':[], 'queries':{'xhs':['词乙','词丙']}}]))
            with patch.object(G,'PLAN_F',f), patch.object(G.resolver,'resolve',return_value=('bread','fixture')):
                work=G.category_worklist()
            self.assertEqual(work['bread']['seeds'],['词甲','词乙','词丙'])
            self.assertEqual(work['bread']['leaves'],[1,2])

    def test_account_repair_does_not_restart_pool(self):
        with tempfile.TemporaryDirectory() as d, patch.object(A,'ACCT_DIR',Path(d)), \
                patch.object(A,'_find_proc',return_value=[]), patch.object(A,'human_alert_if_needed'), \
                patch.object(A,'escalate_unknown_if_needed'), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(A.run(),({},False))
        self.assertIn('自动拉起已暂停',out.getvalue())

    def test_router_does_not_dispatch_gap_worker(self):
        with tempfile.TemporaryDirectory() as d, patch.object(R,'DATA',Path(d)), \
                patch.object(R,'xhs_usable_accounts',return_value=(1,{})), contextlib.redirect_stdout(io.StringIO()):
            target,why=R.decide()
        self.assertEqual(target,'');self.assertIn('已暂停',why)

    def test_supply_lca_and_no_common_ancestor_fallback(self):
        rows=[{'id':10,'name':'面包','parent_category':None,'dimension':'菜系'},
              {'id':11,'name':'可颂','parent_category':10,'dimension':'菜系'},
              {'id':12,'name':'贝果','parent_category':10,'dimension':'菜系'},
              {'id':99,'name':'其他根','parent_category':None,'dimension':'菜系'}]
        ledger=[dict(rows[0],leaf=False,n_active=8),dict(rows[1],leaf=True,target_n=3),
                dict(rows[2],leaf=True,target_n=4),dict(rows[3],leaf=True,target_n=2)]
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'ledger.json';f.write_text(json.dumps(ledger))
            with patch.object(G,'LEDGER_F',f), patch.object(G.resolver.C,'fetch_all',return_value=rows), \
                    patch.dict(G.resolver._CACHE,{'rows':None},clear=False):
                normal=G.category_supply('bread',{'bread':{'leaves':[11,12]}})
                fallback=G.category_supply('bread',{'bread':{'leaves':[11,99]}})
            self.assertEqual(normal,{'root_id':10,'root_name':'面包','n_active':8,'target':7,'met':True})
            self.assertEqual(fallback,{'root_id':10,'root_name':'面包','n_active':8,'target':5,'met':True})

    def test_night_watch_ignores_paused_pool_but_warns_real_faults(self):
        with patch.object(N,'log_age_minutes',return_value=0), patch.object(N,'tail_lines',return_value=[]), \
                patch.object(N,'proc_alive',side_effect=lambda name:name=='cron'):
            normal=N.health_checks()
        self.assertEqual(normal['hard'],[])
        with patch.object(N,'log_age_minutes',side_effect=lambda name:None if name=='watchdog.log' else 0), \
                patch.object(N,'tail_lines',return_value=[]), patch.object(N,'proc_alive',return_value=False), \
                patch.object(N.notifier,'warn') as warn:
            broken=N.health_checks();N.emit_hard(broken['hard'])
        self.assertEqual({k for k,_ in broken['hard']},{'proc:cron','stale:watchdog.log'})
        self.assertEqual({c.kwargs['key'] for c in warn.call_args_list},{'proc:cron','stale:watchdog.log'})

    def test_retired_bridge_and_remaining_consumers_do_not_auto_apply(self):
        self.assertFalse((ROOT/'cloud/unmatched_bridge.py').exists())
        for name in ['cloud_discover','cloud_bili_collect','gap_runner']:
            tree=ast.parse((ROOT/'cloud'/f'{name}.py').read_text())
            # Check runtime literals, excluding docstrings; no command construction may name the writer.
            for n in ast.walk(tree):
                if isinstance(n,ast.Call):
                    literals=[v.value for v in ast.walk(n) if isinstance(v,ast.Constant) and isinstance(v.value,str)]
                    self.assertFalse(any('candidate_apply.py' in v for v in literals),name)
        active=[x for x in (ROOT/'cloud/crontab.txt').read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')]
        self.assertFalse(any('gap_pool.py' in x or 'gap_runner.py' in x for x in active))


if __name__=='__main__':
    unittest.main()
