"""Run: python -m unittest -v test_opening_hours_boundary (from cloud)."""
import ast
import importlib.util
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
PIPE = HERE / 'vendor' / 'pipeline'
sys.path.insert(0, str(PIPE))
import opening_hours_parser as P

class HoursBoundaryTests(unittest.TestCase):
    def test_pure_import(self):
        code = f"""
import sys
sys.path.insert(0, {str(PIPE)!r})
class Block:
 def find_spec(self, fullname, *args):
  if fullname in ('common', 'opening_hours_collector', 'requests', 'health', 'map_helpers'):
   raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
import opening_hours_parser as p
assert p.build_opening_hours('周末 11:00-22:00')[1] == '仅周末'
"""
        subprocess.run([sys.executable, '-I', '-c', code], check=True)

    def test_contract(self):
        self.assertEqual(P.build_opening_hours(''), (None, None, 'none'))
        self.assertEqual(P.build_opening_hours('周二休'), ({}, '周二休', 'low'))
        hours, days, confidence = P.build_opening_hours('周五至周一 11：00—22：00')
        self.assertEqual(set(hours), {'周五', '周六', '周日', '周一'})
        self.assertEqual((days, confidence), ('周五至周一', 'high'))
        self.assertEqual(P.build_opening_hours('工作日 11:00-14:00,17:00-22:00')[0]['周一'], '11:00-14:00; 17:00-22:00')
        self.assertEqual(P.extract_time_ranges('11点到22点'), [('11:00', '22:00')])

    def test_evidence(self):
        self.assertEqual(P.parse_evidence_quotes({'quotes': [{'quote': '周末'}, '11:00-22:00']}), '周末 11:00-22:00')
        self.assertEqual(P.parse_evidence_quotes('not json'), 'not json')
        self.assertEqual(P.parse_evidence_quotes(None), '')

    def test_consumer_uses_parser(self):
        tree = ast.parse((HERE / 'cloud_hours_fill.py').read_text())
        imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        self.assertIn('opening_hours_parser', [n.module for n in imports])
        self.assertNotIn('opening_hours_collector', [n.module for n in imports])
        # Execute the actual consumer parsing function, without loading DB/map clients.
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parse_hours_text']
        ns = {'DAYS_CN': P.DAYS_CN, 'build_opening_hours': P.build_opening_hours}
        exec(compile(ast.Module(body=body, type_ignores=[]), '<consumer>', 'exec'), ns)
        self.assertEqual(ns['parse_hours_text']('全天')[0], dict.fromkeys(P.DAYS_CN, '00:00-24:00'))
        self.assertEqual(ns['parse_hours_text']('周末 11:00-22:00')[1], '仅周末')
        self.assertEqual(ns['parse_hours_text']('无营业信息'), (None, None))

    def test_compatibility_exports(self):
        # Load only import declarations for this boundary, avoiding batch DB setup.
        tree = ast.parse((PIPE / 'opening_hours_collector.py').read_text())
        imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == 'opening_hours_parser']
        ns = {}
        exec(compile(ast.Module(body=imports, type_ignores=[]), '<compat>', 'exec'), ns)
        for name in ('DAYS_CN', 'DAYS_SHORT', 'parse_evidence_quotes', 'extract_time_ranges', 'extract_closed_day', 'extract_day_range', 'build_opening_hours'):
            self.assertIs(ns[name], getattr(P, name))

if __name__ == '__main__':
    unittest.main()
