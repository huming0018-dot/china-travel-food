"""Offline CLI contract; fixture DB reads, real pure text normalization, no collector."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PIPE = HERE if (HERE / 'evidence_pool.py').exists() else HERE / 'vendor' / 'pipeline'


def load(name):
    spec = importlib.util.spec_from_file_location(name, PIPE / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EvidencePoolEntry(unittest.TestCase):
    def setUp(self):
        self.reads = []
        self.tables = {
            'restaurants': [{'id': 1, 'name': '月舟小馆', 'status': 'active', 'district': '静安区'}],
            'cuisines': [], 'restaurant_cuisines': [],
            'reviews': [{'restaurant_id': 1, 'author_name': '食客甲', 'source_platform': 'xhs',
                         'trust_level': 'high', 'is_verified_diner': True,
                         'aspect_taste': 4, 'source_url': 'fixture:note1'}],
        }
        def fetch(table, *args, **kwargs):
            self.reads.append(table)
            return self.tables[table]
        common = types.ModuleType('common')
        common.cjk_norm = load('text_normalization').cjk_norm
        common.fetch_all = fetch
        # No database writer or network API is supplied.
        with patch.dict(sys.modules, {'common': common}):
            self.module = load('evidence_pool')

    def test_report_output_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(self.module, 'OUT_DIR', root), patch.object(self.module, 'DISC', root), \
                    patch.object(sys, 'argv', ['evidence_pool.py']), contextlib.redirect_stdout(io.StringIO()) as output:
                self.module.main()
            row = json.loads((root / 'pool.jsonl').read_text())
            self.assertEqual((row['rid'], row['n_real'], row['indep'], row['taste_real']), (1, 1, 1, 4.0))
            self.assertIn('不写数据库或收录新品牌', output.getvalue())
            self.assertNotIn('--commit', output.getvalue())

    def test_removed_commit_fails_before_io(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'not-created'
            with patch.object(self.module, 'OUT_DIR', target), patch.object(sys, 'argv', ['evidence_pool.py', '--commit']), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                self.module.main()
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(self.reads, [])
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
