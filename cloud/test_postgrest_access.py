"""Synthetic transport only: never connect to a database or load credentials."""
import unittest
from unittest.mock import Mock, patch
import requests
import common_core as core
import postgrest_access as db


def response(rows=(), status=200):
    result = Mock(status_code=status)
    result.json.return_value = list(rows)
    return result


class AccessBoundary(unittest.TestCase):
    def test_headers_and_missing_key_contract(self):
        with patch.object(core, '_api_key', return_value='fixture'):
            self.assertEqual(core.headers(False), dict(apikey='fixture',
                Authorization='Bearer fixture', **{'Content-Type': 'application/json'}))
        with patch.object(core, '_api_key', return_value=''):
            with self.assertRaisesRegex(RuntimeError, '缺少密钥'):
                core.headers()

    def test_real_facade_uses_access_module_and_keeps_response(self):
        result = response()
        with patch.object(core, '_supabase_base', return_value='https://fixture.invalid/rest/v1'), \
             patch.object(core, 'headers', return_value={'fixture': 'header'}), \
             patch.object(core._requests, 'request', return_value=result) as send, \
             patch.object(db, 'request', wraps=db.request) as boundary:
            self.assertIs(core.req('PATCH', '/items?id=eq.7', False, json={'x': 1}), result)
            boundary.assert_called_once()
            send.assert_called_once_with('PATCH', 'https://fixture.invalid/rest/v1/items?id=eq.7',
                headers={'fixture': 'header'}, timeout=45, json={'x': 1})

    def test_retry_and_existing_timeout_semantics(self):
        good = response()
        send = Mock(side_effect=[response(status=429), requests.ConnectionError('fixture'), good])
        sleep = Mock()
        result = db.request('GET', '/items', base_url='https://fixture.invalid',
                            get_headers=lambda: {}, send=send, sleep=sleep, timeout=7)
        self.assertIs(result, good)
        self.assertEqual([c.kwargs['timeout'] for c in send.call_args_list], [7, 45, 45])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_nonretry_status_returns_and_exhaustion_raises(self):
        result = response(status=401)
        sleep = Mock()
        self.assertIs(db.request('GET', '/items', base_url='', get_headers=lambda: {},
            send=lambda *a, **k: result, sleep=sleep), result)
        sleep.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'GET /items 连续失败'):
            db.request('GET', '/items', base_url='', get_headers=lambda: {},
                       send=Mock(side_effect=requests.ConnectionError('fixture')),
                       sleep=sleep, retries=2)

    def test_real_pagination_keeps_query_and_pacing(self):
        pages = [response([{'id': 1}, {'id': 2}]), response([{'id': 3}])]
        with patch.object(core, 'req', side_effect=pages) as request, \
             patch.object(core._time, 'sleep') as sleep, \
             patch.object(db, 'fetch_all', wraps=db.fetch_all) as boundary:
            self.assertEqual(core.fetch_all('items', 'id', 2, False, 'id.desc', 'active=eq.true'),
                             [{'id': 1}, {'id': 2}, {'id': 3}])
            boundary.assert_called_once()
            self.assertEqual([c.args for c in request.call_args_list], [
                ('GET', '/items?select=id&limit=2&offset=0&order=id.desc&active=eq.true'),
                ('GET', '/items?select=id&limit=2&offset=2&order=id.desc&active=eq.true')])
            self.assertTrue(all(c.kwargs == {'use_service': False} for c in request.call_args_list))
            sleep.assert_called_once_with(.12)
            for page in pages:
                page.raise_for_status.assert_called_once()

    def test_empty_page_and_http_error(self):
        with patch.object(core, 'req', return_value=response()):
            self.assertEqual(core.fetch_all('items'), [])
        bad = response()
        bad.raise_for_status.side_effect = requests.HTTPError('fixture')
        with patch.object(core, 'req', return_value=bad):
            with self.assertRaises(requests.HTTPError):
                core.fetch_all('items')


if __name__ == '__main__':
    unittest.main()
