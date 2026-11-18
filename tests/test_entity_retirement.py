import ast
import contextlib
import io
import pathlib
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / 'cloud/vendor/pipeline/entity_dedup.py'

class RetirementTest(unittest.TestCase):
    def load(self):
        c = types.ModuleType('common')
        c.fetch_all = lambda *a, **kw: []
        c.cjk_norm = lambda value: str(value or '').lower().replace(' ', '')
        c.req = lambda *a, **kw: self.fail('unexpected request')
        with patch.dict(sys.modules, {'common': c}):
            return runpy.run_path(str(PATH)), c

    def test_write_functions_absent(self):
        module, _ = self.load()
        for name in ('migrate_child_row', 'migrate_children', 'composite_filter', 'snapshot_members'):
            self.assertNotIn(name, module)

    def test_apply_rejected_before_reads(self):
        module, c = self.load()
        c.fetch_all = lambda *a, **kw: self.fail('apply read before rejection')
        with patch.object(sys, 'argv', ['entity_dedup.py', '--apply']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as err:
                module['main']()
        self.assertNotEqual(err.exception.code, 0)

    def test_default_plan_read_only(self):
        module, _ = self.load()
        with tempfile.TemporaryDirectory() as d, patch.object(sys, 'argv', ['entity_dedup.py', '--plan', str(pathlib.Path(d)/'plan.json')]), contextlib.redirect_stdout(io.StringIO()) as out:
            module['main']()
            self.assertIn('REVIEW ONLY', out.getvalue())
            self.assertTrue((pathlib.Path(d)/'plan.json').exists())

    def test_no_write_request_calls(self):
        tree = ast.parse(PATH.read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'req']
        self.assertTrue(calls)
        self.assertTrue(all(isinstance(n.args[0], ast.Constant) and n.args[0].value == 'GET' for n in calls))

    def test_patrol_consumer(self):
        module, _ = self.load()
        tree = ast.parse((ROOT/'cloud/cloud_patrol.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'check_entities_full')
        env = {'ED': types.SimpleNamespace(**module)}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'patrol', 'exec'), env)
        self.assertEqual(env['check_entities_full']([]), (0,0,[]))

    def test_one_off_writer_removed(self):
        self.assertFalse((ROOT/'cloud/vendor/pipeline/closed_relocate.py').exists())

if __name__ == '__main__': unittest.main()
