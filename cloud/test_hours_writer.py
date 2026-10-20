"""Verify conditional writes and independent existing-fact protection."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from hours_evidence import evidence

class WriterTests(unittest.TestCase):
    def load_gate(self):
        fake=types.ModuleType('common_core')
        fake.log=lambda *a, **k: None
        gate=types.ModuleType('data_gate')
        gate.validate=lambda *a: []
        with patch.dict(sys.modules, common_core=fake, data_gate=gate):
            spec=importlib.util.spec_from_file_location('tested_gate', pathlib.Path(__file__).with_name('gate_apply.py'))
            obj=importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
        return obj, fake
    def test_null_predicate_and_readback(self):
        g,c=self.load_gate(); calls=[]
        value=evidence('每日 11:00-22:00','https://example.org/store','official_restaurant','exact_name_and_address')
        c.req=lambda method,url,**k: calls.append((url,k)) or types.SimpleNamespace(status_code=204)
        c.fetch_all=lambda *a,**k:[{'id':1,'opening_hours':value}]
        plan={'label_patches':{'1':{'opening_hours':value}}}
        with tempfile.TemporaryDirectory() as td:
            g.LEDGER=pathlib.Path(td)
            n,err,_=g.apply_plan(plan)
        self.assertEqual((n,err),(1,0))
        self.assertIn('opening_hours=is.null&status=eq.active', calls[0][0])
        self.assertIn('opening_hours',plan['label_patches']['1'])
    def test_concurrent_fact_not_reported_success(self):
        g,c=self.load_gate()
        value=evidence('每日 11:00-22:00','https://example.org/store','official_restaurant','exact_name_and_address')
        c.req=lambda *a,**k:types.SimpleNamespace(status_code=204)
        c.fetch_all=lambda *a,**k:[{'id':1,'opening_hours':{'raw':'human verified'}}]
        with tempfile.TemporaryDirectory() as td:
            g.LEDGER=pathlib.Path(td)
            n,err,_=g.apply_plan({'label_patches':{'1':{'opening_hours':value}}})
        self.assertEqual((n,err),(0,1))
    def test_invalid_candidate_never_writes(self):
        g,c=self.load_gate()
        c.req=lambda *a,**k: self.fail('unexpected write')
        with tempfile.TemporaryDirectory() as td:
            g.LEDGER=pathlib.Path(td)
            n,err,_=g.apply_plan({'label_patches':{'1':{'opening_hours':{'raw':'guess'}}}})
        self.assertEqual((n,err),(0,1))

if __name__=='__main__': unittest.main()
