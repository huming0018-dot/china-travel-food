"""Offline contracts for text tool and its real map-matching consumer."""
import importlib
import pathlib
import sys
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
PIPE = HERE / 'vendor' / 'pipeline'
sys.path.insert(0, str(PIPE if PIPE.exists() else HERE))
sys.path.insert(0, str(HERE))


class TextBoundary(unittest.TestCase):
    def test_tool_and_real_map_consumer_do_not_import_database_common(self):
        sys.modules.pop('map_helpers', None)
        sys.modules.pop('text_normalization', None)
        with patch.dict(sys.modules, {'common': None}):
            text = importlib.import_module('text_normalization')
            maps = importlib.import_module('map_helpers')
            self.assertIs(maps.cjk_norm, text.cjk_norm)
            self.assertIs(maps.addr_core, text.addr_core)
            self.assertEqual(maps.cjk_sim('本舖・菓子', '本铺果子'), 0.95)
            self.assertEqual(maps.addr_core_sim('南京路123号', '南京路123号'), 1.0)
            candidates = [dict(title='本铺果子', address='南京路123号', lng=121.47, lat=31.23)]
            self.assertIs(maps.pick_best(candidates, '本舖・菓子', '南京路123号')[0], candidates[0])

    def test_exact_text_contract_without_optional_opencc(self):
        import text_normalization as text
        with patch.object(text, '_t2s', None):
            self.assertEqual(text.cjk_unify('菓舖寛沢麺'), '果铺宽泽面')
            self.assertEqual(text.cjk_norm(' A & 本舖（菓子）+ '), 'a本铺果子')
            self.assertEqual(text.norm_name('A & 本舖（菓子）+'), 'a&本舖菓子+')
            self.assertEqual(text.cjk_norm(None), '')
            self.assertEqual(text.addr_core(None), '')
            self.assertEqual(text.addr_core('南京路123号（商场）'), '南京路123号')
            for value in ('本舖', 'A + B', '', '麺屋・黒'):
                self.assertEqual(text.cjk_norm(text.cjk_norm(value)), text.cjk_norm(value))

    def test_optional_converter_precedes_matching_mapping(self):
        import text_normalization as text
        class Converter:
            def convert(self, value):
                return value.replace('舊', '菓')
        with patch.object(text, '_t2s', Converter()):
            self.assertEqual(text.cjk_unify('舊'), '果')


if __name__ == '__main__':
    unittest.main()
