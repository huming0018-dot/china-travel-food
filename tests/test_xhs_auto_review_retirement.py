import hashlib,importlib.util,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('retired_router',ROOT/'cloud/cloud_router.py');R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
class Retirement(unittest.TestCase):
 def test_healthy_account_never_dispatches_reviews(self):
  with tempfile.TemporaryDirectory() as d,patch.object(R,'DATA',Path(d)),patch.object(R,'log'),patch.object(R,'xhs_usable_accounts',return_value=(1,{})):
   for marker in [False,True]:
    if marker:(Path(d)/'ALL_REVIEWS_DONE').touch()
    for tick in [1,2,3,100]:
     (Path(d)/'router_tick.txt').write_text(str(tick))
     self.assertEqual(R.decide()[0],'')
 def test_cooling_accounts_keep_michelin_policy(self):
  with tempfile.TemporaryDirectory() as d,patch.object(R,'DATA',Path(d)),patch.object(R,'log'),patch.object(R,'xhs_usable_accounts',return_value=(0,{})):
   self.assertEqual(R.decide()[0],'cloud_michelin_collect.py')
   f=Path(d)/'michelin_shanghai.json';f.write_text('{}');self.assertEqual(R.decide()[0],'')
   os.utime(f,(time.time()-25*3600,)*2);self.assertEqual(R.decide()[0],'cloud_michelin_collect.py')
 def test_entries_retired(self):
  self.assertFalse((ROOT/'cloud/run_batch.py').exists());self.assertFalse((ROOT/'cloud/vendor/pipeline/xhs_to_reviews.py').exists())
  for p in ['cloud/cloud_router.py','cloud/entrypoint.sh','cloud/watchdog.py','cloud/container_closure_audit.py']:
   s=(ROOT/p).read_text();self.assertNotIn('run_batch.py',s);self.assertNotIn('xhs_to_reviews',s)
 def test_other_cores_unchanged(self):
  for p,sha in [('entity_match.py','491482c9ab8ffd9ac9d1316f5c42451d9435453c'),('atlas_write.py','d98e69f98936420bf5acdd44007d9d0e0e6bc718'),('xhs_collect.py','9b206021fade1353b16ccee19613fae88a1275d1')]:
   b=(ROOT/'cloud/vendor/pipeline'/p).read_bytes();self.assertEqual(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),sha)
if __name__=='__main__':unittest.main()
