"""Exercise the actual copied consumer without network, credentials or DB writes."""
import json
import io
import urllib.error
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx2 as httpx
from agent_model_access import create_client

# Legacy common reads .env at import: point only at an empty fixture directory.
with tempfile.TemporaryDirectory() as empty:
    os.environ['FOOD_APP_DIR'] = empty
    import fleet_grid_run as consumer
import model_providers as MP

class Migration(unittest.TestCase):
    def test_real_consumer_request_and_result_match_old_chat(self):
        payload={'id':'fixture','object':'chat.completion','created':0,'model':'fixture',
            'choices':[{'index':0,'message':{'role':'assistant','content':'[{"name":"fixture"}]'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':4,'completion_tokens':2,'total_tokens':6}}
        p=SimpleNamespace(name='qwen',api_key='NOT_REAL',base_url='https://fixture.invalid/v1',
            supports_web=True,spec={'web_search_kind':'qwen_enable_search'})
        old_requests=[]; new_requests=[]
        class OldResponse:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return json.dumps(payload).encode()
        def old_send(req,timeout):
            old_requests.append(json.loads(req.data)); return OldResponse()
        def handler(req):
            new_requests.append(json.loads(req.content)); return httpx.Response(200,json=payload)
        def client_factory(**kw):
            return create_client(**kw,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch.object(MP,'web_search_enabled',return_value=True), patch.object(MP.urllib.request,'urlopen',old_send):
            before=MP.chat(p,'fixture','fixture prompt')
        with patch.object(MP,'web_search_enabled',return_value=True), patch.object(consumer,'create_client',client_factory), patch.object(MP,'chat',side_effect=AssertionError('old call forbidden')):
            after=consumer.call_one(MP,p,'fixture','fixture prompt')
        self.assertEqual(old_requests,new_requests)
        self.assertEqual(after,{**before,'identity':'qwen/fixture'})
    def test_http_401_failure_matches_legacy_contract(self):
        detail = json.dumps({'error': {'message': 'denied ' + 'x' * 300}}).encode()
        p = SimpleNamespace(name='qwen', api_key='NOT_REAL', base_url='https://fixture.invalid/v1',
                            supports_web=True, spec={'web_search_kind': 'qwen_enable_search'})
        def old_send(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {}, io.BytesIO(detail))
        def handler(req):
            return httpx.Response(401, content=detail, headers={'content-type': 'application/json'})
        def client_factory(**kw):
            return create_client(**kw, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch.object(MP, 'web_search_enabled', return_value=True), patch.object(MP.urllib.request, 'urlopen', old_send):
            before = MP.chat(p, 'fixture', 'fixture prompt')
        with patch.object(MP, 'web_search_enabled', return_value=True), patch.object(consumer, 'create_client', client_factory), patch.object(MP, 'chat', side_effect=AssertionError('old call forbidden')):
            after = consumer.call_one(MP, p, 'fixture', 'fixture prompt')
        self.assertEqual(after, {**before, 'identity': 'qwen/fixture'})
        self.assertEqual(after['error'], 'HTTP 401: ' + detail.decode()[:200])

    def test_connection_failure_preserves_legacy_fields(self):
        p = SimpleNamespace(name='qwen', api_key='NOT_REAL', base_url='https://fixture.invalid/v1',
                            supports_web=False, spec={'web_search_kind': 'qwen_enable_search'})
        def handler(req):
            raise httpx.ConnectError('fixture unavailable', request=req)
        def client_factory(**kw):
            return create_client(**kw, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch.object(MP.urllib.request, 'urlopen', side_effect=OSError('fixture unavailable')):
            before = MP.chat(p, 'fixture', 'fixture prompt')
        with patch.object(consumer, 'create_client', client_factory), patch.object(MP, 'chat', side_effect=AssertionError('old call forbidden')):
            after = consumer.call_one(MP, p, 'fixture', 'fixture prompt')
        # SDK changes diagnostic wording, not the consumer's result contract.
        before['identity'] = 'qwen/fixture'
        self.assertEqual(set(after), set(before))
        self.assertEqual({k: v for k, v in after.items() if k != 'error'},
                         {k: v for k, v in before.items() if k != 'error'})
        self.assertTrue(after['error'])
        self.assertLessEqual(len(after['error']), 200)

    def test_authorization_filter_still_excludes_unapproved_models(self):
        p=SimpleNamespace(models=['not-authorized'])
        with patch.object(MP,'load_providers',return_value=[p]),patch.object(consumer,'_FLEET_FULL',False):
            tasks,notes=consumer.api_tasks()
        self.assertIsNone(tasks)
        self.assertTrue(notes)
    def test_parser_unchanged(self):
        self.assertEqual(consumer._extract_json('```json\n[{"name":"fixture"}]\n```'),{'name':'fixture'})

if __name__=='__main__': unittest.main()
