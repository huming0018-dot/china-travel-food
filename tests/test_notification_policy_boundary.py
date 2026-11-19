"""Offline extraction contract; no notification service or database access."""
import ast
import json
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLOUD = ROOT / 'cloud'
sys.path.insert(0, str(CLOUD))

class Boundary(unittest.TestCase):
    def test_tool_exists_without_business_or_transport_imports(self):
        p = CLOUD / 'notification_policy.py'
        self.assertTrue(p.is_file(), 'generic delivery policy must be extracted from food adapter')
        tree = ast.parse(p.read_text())
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertFalse(imports, 'policy is pure orchestration with injected dependencies')
        self.assertNotIn('上海', p.read_text())
        self.assertNotIn('telegram', p.read_text().lower())
        self.assertNotIn('仍待处理', p.read_text())

    def test_non_food_consumer_and_failed_delivery_do_not_advance_ledger(self):
        from notification_policy import NotificationPolicy
        ledger, sent = {}, []
        success = [False]
        def save(value): ledger.clear(); ledger.update(copy.deepcopy(value))
        def deliver(head, body): sent.append((head, body)); return success[0]
        policy = NotificationPolicy(
            load=lambda: copy.deepcopy(ledger), save=save, deliver=deliver,
            render=lambda level, body, **kw: ('build-service/' + level, body),
            render_nudge=lambda body, n, total: f"{body} [build reminder {n}/{total}]",
            clock=lambda: 500, digest=lambda body: body)
        self.assertFalse(policy.warn('build failed', 'job-1', 60))
        self.assertEqual(ledger, {})
        success[0] = True
        self.assertTrue(policy.warn('build failed', 'job-1', 60))
        self.assertFalse(policy.warn('changed', 'job-1', 60))
        self.assertEqual(sent, [('build-service/WARN', 'build failed')] * 2)
        self.assertEqual(ledger['job-1']['state'], 'open')
        self.assertTrue(policy.action('deploy', 'job-2', 'approve', (0,)))
        self.assertTrue(policy.action('deploy', 'job-2', 'approve', (0,)))
        self.assertEqual(sent[-1], ('build-service/ACTION', 'deploy [build reminder 1/1]'))

    def test_adapter_matches_frozen_legacy_sequences(self):
        # Golden output captured from main 1dddf6e5, with fixed clock and fake delivery.
        fake_health = types.ModuleType('health')
        fake_health._telegram = lambda *a: self.fail('network delivery forbidden')
        with patch.dict(sys.modules, {'health': fake_health}):
            spec = importlib.util.spec_from_file_location('food_notifier', CLOUD / 'notifier.py')
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        def run(mod):
            ledger, sends, results = {}, [], []
            now, success = [1000], [True]
            def save(value): ledger.clear(); ledger.update(copy.deepcopy(value))
            def deliver(head, body): sends.append((head,body)); return success[0]
            with patch.object(mod, '_load', side_effect=lambda: copy.deepcopy(ledger)), patch.object(mod, '_save', side_effect=save), patch.object(mod, '_deliver', side_effect=deliver), patch.object(mod, '_now_str', return_value='fixed'), patch.object(mod.time, 'time', side_effect=lambda: now[0]):
                def invoke(method, *args, **kw): results.append(getattr(mod,method)(*args,**kw))
                invoke('info','body',cadence=10); invoke('info','body2',cadence=10)
                now[0]+=10; invoke('info','body2',cadence=10)
                invoke('warn','warn',key='w',cooldown=10); invoke('warn','changed',key='w',cooldown=10)
                now[0]+=10; success[0]=False; invoke('warn','failed',key='w',cooldown=10)
                success[0]=True; invoke('warn','retry',key='w',cooldown=10)
                invoke('resolve','unknown',key='missing')
                invoke('action','act',key='a',action_text='do',nudge_schedule=(2,3))
                invoke('action','act',key='a',action_text='do',nudge_schedule=(2,3))
                now[0]+=2; invoke('action','act',key='a',action_text='do',nudge_schedule=(2,3))
                now[0]+=3; invoke('action','act',key='a',action_text='do',nudge_schedule=(2,3))
                now[0]+=99; invoke('action','act',key='a',action_text='do',nudge_schedule=(2,3))
                invoke('resolve','done',key='a'); invoke('resolve','done',key='a')
                invoke('action','act',key='a',action_text='do')
            return results, sends, ledger
        before = json.loads((ROOT / 'tests' / 'notification_policy_legacy.json').read_text())
        after = run(mod)
        self.assertEqual(json.loads(json.dumps(after)), before)
        self.assertEqual(after[0], [True,False,True,True,False,False,True,False,True,False,True,True,False,True,False,False])

if __name__ == '__main__': unittest.main()
