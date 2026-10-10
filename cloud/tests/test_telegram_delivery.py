"""Isolated transport tests: no network, credentials, server, or real message."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import health
from external_watchdog import telegram_delivery as D, wd_notify as W
import requests

ENV = dict(TELEGRAM_RELAY_URL='https://relay.invalid',
           TELEGRAM_RELAY_API_KEY='sb_publishable_test', TELEGRAM_RELAY_SECRET='notify-only',
           TELEGRAM_BOT_TOKEN='123:secret-token', TELEGRAM_CHAT_ID='42',
           TELEGRAM_API_BASE='https://proxy.invalid')


def response(data, status=200):
    r = Mock(status_code=status)
    r.json.return_value = data
    return r


class DeliveryTests(unittest.TestCase):
    def run_case(self, sequence, expected, routes, env=ENV):
        # Both public entrypoints must traverse the same concrete HTTP routes.
        for entry in (lambda: health._telegram('body', 'title'),
                      lambda: W._telegram('title', 'body')):
            with self.subTest(entry=entry), patch.dict(os.environ, env, clear=True), \
                 patch.object(health, 'channel_enabled', return_value=True), \
                 patch.object(D.requests, 'post', side_effect=sequence) as post, \
                 patch.object(D.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()) as log:
                self.assertEqual(entry(), expected)
                actual = [('receipt' if 'receipt' in c.args[0] else
                           'relay' if 'enqueue' in c.args[0] else
                           'proxy' if 'proxy.invalid' in c.args[0] else 'official')
                          for c in post.call_args_list]
                self.assertEqual(actual, routes)
                self.assertNotIn('secret-token', log.getvalue())
                self.assertNotIn('notify-only', log.getvalue())
                for call in post.call_args_list:
                    self.assertFalse(call.kwargs['allow_redirects'])

    def test_relay_confirmed(self):
        self.run_case([response({'ok':True,'request_id':7}),
                       response({'delivered':True})], True, ['relay','receipt'])

    def test_relay_failure_proxy_success(self):
        self.run_case([response({'ok':False}), response({'ok':True})],
                      True, ['relay','proxy'])

    def test_proxy_unreachable_official_success(self):
        self.run_case([requests.ConnectionError('relay'), requests.ConnectionError('proxy'),
                       response({'ok':True})], True, ['relay','proxy','official'])

    def test_official_failure(self):
        self.run_case([response({},503), response({'ok':False}), response({},403)],
                      False, ['relay','proxy','official'])

    def test_total_network_outage(self):
        self.run_case([requests.ConnectionError('offline secret-token')]*3,
                      False, ['relay','proxy','official'])

    def test_queued_is_not_delivery(self):
        self.run_case([response({'ok':True,'request_id':7})]+
                      [response({'pending':True,'delivered':False})]*4+
                      [response({'ok':False})]*2, False,
                      ['relay']+['receipt']*4+['proxy','official'])

    def test_failed_receipt_falls_back(self):
        self.run_case([response({'ok':True,'request_id':7}),
                       response({'delivered':False,'pending':False}), response({'ok':True})],
                      True, ['relay','receipt','proxy'])

    def test_pending_then_confirmed(self):
        self.run_case([response({'ok':True,'request_id':7}), response({'pending':True}),
                       response({'delivered':True})], True, ['relay','receipt','receipt'])

    def test_malformed_and_secret_logs(self):
        bad = response({}); bad.json.side_effect=ValueError('123:secret-token')
        self.run_case([bad, response([]), requests.Timeout('123:secret-token')],
                      False, ['relay','proxy','official'])

    def test_relay_does_not_need_bot_credentials(self):
        self.run_case([response({'ok':True,'request_id':7}),response({'delivered':True})],
                      True,['relay','receipt'], {k:v for k,v in ENV.items() if 'BOT' not in k and 'CHAT' not in k})

    def test_watchdog_never_uses_database_or_ops_credentials(self):
        env = {'NEXT_PUBLIC_SUPABASE_URL':'https://relay.invalid',
               'SUPABASE_SERVICE_ROLE_KEY':'high-key', 'CROWD_OPS_SECRET':'broad-secret'}
        with patch.dict(os.environ,env,clear=True), patch.object(D.requests,'post') as post:
            self.assertIsNone(D.send_telegram('title','body'))
            post.assert_not_called()

    def test_legacy_jwt_and_publishable_headers(self):
        for key, bearer in [('eyJtest',True),('sb_publishable_test',False)]:
            with patch.dict(os.environ,{**ENV,'TELEGRAM_RELAY_API_KEY':key},clear=True), \
                 patch.object(D.requests,'post',side_effect=[response({'ok':True,'request_id':7}),response({'delivered':True})]) as post:
                self.assertTrue(D.send_telegram('t','m'))
                self.assertEqual('Authorization' in post.call_args.kwargs['headers'],bearer)

    def test_official_deduplicated(self):
        self.run_case([response({'ok':False}),response({'ok':False})],False,
                      ['relay','official'], {**ENV,'TELEGRAM_API_BASE':'https://api.telegram.org/'})

    def test_cooldown_only_on_delivery(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(health,'STATE_F',Path(tmp)/'state.json'), \
             patch.object(health,'_telegram',return_value=False):
            health.alert('m',key='outage')
            self.assertTrue(health.should_send('outage'))
            with patch.object(health,'_telegram',return_value=True):
                health.alert('m',key='outage')
            self.assertFalse(health.should_send('outage'))

    def test_outbox_survives_outage_and_retries(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(W,'HERE',Path(tmp)), \
             patch.object(W,'OUTBOX',Path(tmp)/'pending.json'), patch.object(W,'load_env'), \
             patch.object(W,'_telegram',return_value=False):
            self.assertFalse(W.send('t','m')); W.send('t','m')
            self.assertEqual(json.loads(W.OUTBOX.read_text()),[['t','m']])
            self.assertEqual(W.OUTBOX.stat().st_mode & 0o777,0o600)
            W.flush_pending()
            self.assertEqual(len(W._pending()),1)
            with patch.object(W,'_telegram',return_value=True):
                W.flush_pending()
            self.assertEqual(W._pending(),[])

    def test_disabled_channel(self):
        with patch.object(health,'channel_enabled',return_value=False),patch.object(D.requests,'post') as post:
            self.assertIsNone(health._telegram('m','t')); post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
