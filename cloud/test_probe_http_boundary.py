import importlib.util,io,json,os,pathlib,sys,tempfile,types,unittest,urllib.error
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent
def load(path,name):
 saved={}
 for dep in ('common_core','ingest','model_providers','serp_producer'):
  saved[dep]=sys.modules.get(dep);sys.modules[dep]=types.ModuleType(dep)
 try:
  sys.path.insert(0,str(path.parent))
  spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 finally:
  sys.path.remove(str(path.parent))
  for dep,v in saved.items():
   if v is None:sys.modules.pop(dep,None)
   else:sys.modules[dep]=v
M=load(ROOT/'production_model_probe.py','test_actual_probe')
class Response:
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def read(self):return json.dumps(self.data).encode()
class Tests(unittest.TestCase):
 def test_nonstream_tools_usage(self):
  seen=[];meter=[]
  def transport(req,timeout):
   seen.append((json.loads(req.data),timeout));return Response({'choices':[{'message':{'content':'ok','tool_calls':[{'id':'call'}]}}],'usage':{'total_tokens':4}})
  with patch.object(M.urllib.request,'urlopen',transport),patch.object(M,'meter_usage',lambda *a:meter.append(a)):
   out=M.chat_raw(types.SimpleNamespace(base_url='https://example.test',api_key='fake'),'model',[],tools=[{'type':'function'}],max_tokens=12,timeout=7,hard_cap=0)
  self.assertEqual(out['_usage'],{'total_tokens':4});self.assertEqual(seen[0][0]['stream'],False);self.assertEqual(seen[0][0]['max_tokens'],12);self.assertEqual(seen[0][1],7);self.assertEqual(len(meter),1)
 def test_setlimit_not_retried(self):
  error=urllib.error.HTTPError('https://example.test',429,'quota',{},io.BytesIO(b'{"error":{"code":"SetLimitExceeded"}}'))
  with patch.object(M.urllib.request,'urlopen',side_effect=error) as call,patch.object(M.time,'sleep') as sleep:
   with self.assertRaises(urllib.error.HTTPError):M.chat_raw(types.SimpleNamespace(base_url='https://example.test',api_key='fake'),'m',[])
  self.assertEqual(call.call_count,1);sleep.assert_not_called();self.assertEqual(error._ark_code,'SetLimitExceeded')
 def test_temporary_429_retries(self):
  err=urllib.error.HTTPError('https://example.test',429,'rate',{},io.BytesIO(b'{}'))
  with patch.object(M.urllib.request,'urlopen',side_effect=[err,Response({'choices':[{'message':{'content':'ok'}}]})]),patch.object(M.time,'sleep') as sleep,patch.object(M,'meter_usage'):
   self.assertEqual(M.chat_raw(types.SimpleNamespace(base_url='https://example.test',api_key='fake'),'m',[])['content'],'ok')
  sleep.assert_called_once_with(8)
 def test_model_policy(self):
  auth=M.REWARD_AUTHORIZED;p=types.SimpleNamespace(models=[*auth,'unapproved'])
  with patch.object(M,'_POOL',{'dead':{auth[0]}}),patch.dict(os.environ,{'PROD_MODEL':'unapproved'}):
   self.assertEqual(M.candidate_models(p),[auth[1]])
   self.assertNotIn('unapproved',M.extraction_models(p))
  with patch.object(M,'_POOL',{'dead':set(auth)}):self.assertEqual(M.candidate_models(p),auth)
 def test_cache_hit_and_failed_search_not_saved(self):
  with tempfile.TemporaryDirectory() as d,patch.object(M,'PROBE_CACHE_DIR',pathlib.Path(d)):
   ev=[{'raw':1,'results':[{'source_url':'https://example.test'}]}]
   with patch.object(M,'gather_evidence',return_value=ev) as gather:
    self.assertEqual(M.gather_evidence_cached('brand',1),ev)
    self.assertEqual(M.gather_evidence_cached('brand',8),ev)
    self.assertEqual(gather.call_count,1) # 旧策略仅品牌作键，不随query数量失效。
   with patch.object(M,'gather_evidence',return_value=[{'raw':0,'results':[]}]) as gather:
    M.gather_evidence_cached('failed');M.gather_evidence_cached('failed')
    self.assertEqual(gather.call_count,2)
 def test_meter_actual_local_ledger(self):
  with tempfile.TemporaryDirectory() as d,patch.object(M,'REPORT_DIR',pathlib.Path(d)),patch.object(M,'LLM_LEDGER',pathlib.Path(d)/'usage.jsonl'):
   M.meter_usage('m',{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5})
   self.assertEqual(json.loads((pathlib.Path(d)/'usage.jsonl').read_text())['total'],5)
 def test_model_pause_persistence(self):
  with tempfile.TemporaryDirectory() as d,patch.object(M,'_POOL_STATE_PATH',str(pathlib.Path(d)/'pool.json')),patch.object(M,'_POOL',{'dead':set()}):
   M.mark_model_dead('m');self.assertEqual(M._load_pool_state(),{'dead':{'m'}})
   M.clear_model_dead('m');self.assertEqual(M._load_pool_state(),{'dead':set()})
 def test_zero_cache_ttl(self):
  with tempfile.TemporaryDirectory() as d,patch.object(M,'PROBE_CACHE_DIR',pathlib.Path(d)),patch.object(M,'gather_evidence',return_value=[{'raw':1,'results':[]}]) as gather:
   M.gather_evidence_cached('zero');M.gather_evidence_cached('zero')
   self.assertEqual(gather.call_count,1)
   f=next(pathlib.Path(d).glob('*.json'));os.utime(f,(1,1))
   M.gather_evidence_cached('zero');self.assertEqual(gather.call_count,2)
if __name__=='__main__':unittest.main(verbosity=2)
