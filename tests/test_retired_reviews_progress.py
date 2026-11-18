import contextlib,importlib.util,io,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
class Progress(unittest.TestCase):
 def run_main(self,old_rev,current_rev):
  notifier=types.ModuleType('notifier');notifier.info=Mock(return_value=True);notifier.action=Mock();notifier.resolve=Mock()
  with patch.dict('sys.modules',{'notifier':notifier}):
   spec=importlib.util.spec_from_file_location('review_progress',ROOT/'cloud/progress_broadcast.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
  c={'active':4,'rev':current_rev,'xhs':5,'ver_stores':2,'ge2':1}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);state=root/'progress_state.json';state.write_text(json.dumps({'rev':old_rev,'ts':100,'last_growth_ts':1,'stall_open':True}))
   (root/'_cookie_pool_state.json').write_text(json.dumps({'accounts':{'account_A':{'status':'ok'}}}))
   with patch.object(p,'DATA',root),patch.object(p,'STATE_P',state),patch.object(p,'live_counts',return_value=c),patch.object(p,'apify_cost_line',return_value='费用保留'),patch.object(p.time,'time',return_value=10000),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(p.main(),0)
   saved=json.loads(state.read_text())
  notifier.info.assert_called_once();notifier.action.assert_not_called();notifier.resolve.assert_not_called()
  text=notifier.info.call_args.args[0];self.assertIn('账号：A=ok',text);self.assertIn('费用保留',text)
  self.assertEqual(saved,{'rev':current_rev,'ts':10000});return text
 def test_stale_raw_and_unchanged_count_only_heartbeat(self):
  self.assertIn('+0条',self.run_main(10,10))
 def test_growth_is_count_change_not_retired_incident_resolution(self):
  self.assertIn('+3条',self.run_main(10,13))
 def test_startup_switch_removed_batch_preserved(self):
  compose=(ROOT/'cloud/docker-compose.yml').read_text();self.assertNotIn('RUN_ON_START=',compose);self.assertIn('BATCH=15',compose)
  self.assertIn(' BATCH ',(ROOT/'cloud/entrypoint.sh').read_text());self.assertIn('BATCH',(ROOT/'cloud/production_runner.py').read_text())
if __name__=='__main__':unittest.main()
