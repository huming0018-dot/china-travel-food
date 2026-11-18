import ast,importlib.util,json,pathlib,random,subprocess,sys,types,unittest
P=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(P))
import production_policy as policy
def ev(host,kind='ugc'):return {'url':'https://'+host+'/review','kind':kind,'quote':'原始记录'}
class PolicyTests(unittest.TestCase):
 def test_explicit_contracts(self):
  self.assertIsNone(policy.adjudicate({})['production_model'])
  self.assertEqual(policy.adjudicate({'license_packaged_only':True,'license_hot_cook':False})['production_model'],'外购成品·无堂食厨房')
  self.assertIsNone(policy.adjudicate({'premade_packet_evidence':[ev('a.test')]})['production_model'])
  self.assertEqual(policy.adjudicate({'fresh_wok_evidence':[ev('a.test'),ev('b.test')]})['production_model'],'现炒现做')
  self.assertEqual(policy.adjudicate({'premade_packet_evidence':[ev('a.test'),ev('b.test')]})['production_model'],'预制料理包·复热')
  self.assertEqual(policy.adjudicate({'central_kitchen_license':True,'license_hot_cook':True})['production_model'],'中央厨房·门店加工')
 def test_known_policy_boundary_not_independence_proof(self):
  # 旧设计明确 max(域名数,证据类数)，不是本次发明/修复。
  n,hosts=policy.n_independent_ev([ev('a.test','ugc'),ev('a.test','news')])
  self.assertEqual(n,2);self.assertEqual(hosts,['a.test'])
 def test_no_io_import(self):
  result=subprocess.run([sys.executable,'-I','-S','-B','-c','import sys;sys.path.insert(0,'+repr(str(P))+');import production_policy as p;assert p.adjudicate({})["production_model"] is None;assert "common_core" not in sys.modules;assert "requests" not in sys.modules'],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_original_module_real_import_and_output_adapter(self):
  # 只替换外部I/O依赖，原 production_model_probe 整模块真实导入。
  originals={}
  for name in ('common_core','ingest','model_providers','serp_producer'):
   originals[name]=sys.modules.get(name);sys.modules[name]=types.ModuleType(name)
  try:
   calls=[];ing=sys.modules['ingest']
   ing.valid_source_url=lambda u:u.startswith('https://')
   ing.supersede=lambda *a,**k:calls.append(('supersede',a,k))
   ing.append_finding=lambda *a,**k:(calls.append(('append',a,k)) or True)
   spec=importlib.util.spec_from_file_location('policy_probe_adapter',P/'production_model_probe.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   self.assertIs(m.adjudicate,policy.adjudicate)
   sig={'fresh_wok_evidence':[ev('a.test'),ev('b.test')]}
   v=m.adjudicate(sig);self.assertEqual(m.write_findings('测试',[1],v),6)
   self.assertEqual(len([x for x in calls if x[0]=='supersede']),3)
   self.assertEqual(m.write_findings('测试',[1],policy.adjudicate({})),0)
  finally:
   for name,old in originals.items():
    if old is None:sys.modules.pop(name,None)
    else:sys.modules[name]=old
if __name__=='__main__':unittest.main(verbosity=2)
