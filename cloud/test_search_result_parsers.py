"""Offline HTML contracts and real producer call sites; never run collection."""
import ast
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from search_result_parsers import parse_bing_html, parse_ddg_html

BING = '<li class="b_algo"><h2><a href="https://example.org/article">Title</a></h2><div class="b_caption"><p>Snippet</p></div></li>'
DDG = '<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa%3Fx%3D1&rut=x">Title</a><a class="result__snippet">Snippet</a></div>'


def consumer_functions():
    # Compile the real function definitions, excluding project startup (mkdir,
    # database imports and proxy configuration). No copied implementation.
    tree = ast.parse((HERE / 'serp_producer.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in ('search_bing', 'search_ddg')]
    scope = {'parse_bing_html': parse_bing_html, 'parse_ddg_html': parse_ddg_html}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'serp_producer.py', 'exec'), scope)
    return scope


class SearchParsing(unittest.TestCase):
    def test_contracts_without_project_imports(self):
        with patch.dict(sys.modules, {'common': None, 'findings_extractor': None}):
            self.assertEqual(parse_bing_html(BING), [dict(source_url='https://example.org/article', source_title='Title', snippet='Snippet', source_host='example.org')])
            self.assertEqual(parse_ddg_html(DDG)[0]['source_url'], 'https://example.org/a?x=1')

    def test_empty_invalid_limit_and_fallback(self):
        for parser in (parse_bing_html, parse_ddg_html):
            self.assertEqual(parser('<html>no results</html>'), [])
        self.assertEqual(len(parse_bing_html(BING * 12)), 8)
        self.assertEqual(len(parse_ddg_html(DDG * 12)), 8)
        self.assertEqual(parse_bing_html(BING.replace('https://example.org/article', '/relative')), [])
        self.assertEqual(parse_ddg_html('<div class="result"><a class="result__a" href="javascript:x">bad</a></div>'), [])
        self.assertEqual(parse_bing_html(BING.replace('<div class="b_caption"><p>Snippet</p></div>', ''))[0]['snippet'], 'Title')

    def test_actual_consumers_delegate_and_preserve_http_failure(self):
        scope = consumer_functions()
        for engine, html in [('bing', BING), ('ddg', DDG)]:
            parser = Mock(return_value=[{'proof': engine}])
            scope['parse_' + engine + '_html'] = parser
            scope['_get'] = Mock(return_value=types.SimpleNamespace(status_code=200, text=html))
            self.assertEqual(scope['search_' + engine]('query'), ([{'proof': engine}], None))
            parser.assert_called_once_with(html)
            scope['_get'].return_value.status_code = 429
            self.assertEqual(scope['search_' + engine]('query'), (None, engine + ' http 429'))
            self.assertEqual(parser.call_count, 1)

    def test_parser_exception_retains_consumer_error_contract(self):
        scope = consumer_functions()
        scope['_get'] = Mock(return_value=types.SimpleNamespace(status_code=200, text=''))
        scope['parse_bing_html'] = Mock(side_effect=ValueError('fixture'))
        self.assertEqual(scope['search_bing']('query'), (None, 'bing err ValueError'))


if __name__ == '__main__':
    unittest.main()
