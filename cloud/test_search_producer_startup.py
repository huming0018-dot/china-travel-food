"""Full producer import and --help startup with real local dependencies, offline."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

BOOT = r'''
import pathlib, runpy, socket, sys
cloud = pathlib.Path(sys.argv[1])
sys.path[:0] = [str(cloud), str(cloud / 'vendor' / 'pipeline')]
import requests
def forbidden(*args, **kwargs):
    raise AssertionError('network access is forbidden in startup verification')
requests.sessions.Session.request = forbidden
socket.create_connection = forbidden
socket.socket.connect = forbidden
mode = sys.argv[2]
if mode == 'help':
    sys.argv = [str(cloud / 'serp_producer.py'), '--help']
    try:
        runpy.run_path(str(cloud / 'serp_producer.py'), run_name='__main__')
    except SystemExit as exc:
        assert exc.code == 0, exc.code
else:
    import serp_producer as producer
    import common, findings_extractor
    assert pathlib.Path(common.__file__).resolve() == cloud / 'vendor' / 'pipeline' / 'common.py'
    assert pathlib.Path(findings_extractor.__file__).resolve() == cloud / 'findings_extractor.py'
    assert {'bing', 'ddg'} <= {name for name, fn in producer.ENGINES}
    if mode == 'missing-bs4':
        import builtins
        original = builtins.__import__
        def importing(name, *args, **kwargs):
            if name == 'bs4' or name.startswith('bs4.'):
                raise ModuleNotFoundError('fixture: bs4 unavailable')
            return original(name, *args, **kwargs)
        builtins.__import__ = importing
        class Response:
            status_code = 200
            text = '<html></html>'
        producer._get = lambda *args, **kwargs: Response()
        assert producer.search_bing('fixture') == (None, 'bing err ModuleNotFoundError')
        assert producer.search_ddg('fixture') == (None, 'ddg err ModuleNotFoundError')
    print('IMPORT_OK', mode)
'''


class ProducerStartup(unittest.TestCase):
    def run_startup(self, mode):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # No inherited credentials, proxy configuration or production paths.
            env = {'PATH': os.environ.get('PATH', ''), 'HOME': temp,
                   'FOOD_DATA_DIR': str(root / 'data'),
                   'FOOD_APP_DIR': str(root / 'missing-app'), 'SERP_PROXY': '0'}
            result = subprocess.run([sys.executable, '-I', '-c', BOOT, str(HERE), mode],
                                    cwd=temp, env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'data' / 'post_record').is_dir())
            self.assertEqual(list((root / 'data' / 'post_record').iterdir()), [])
            return result

    def test_full_import_real_dependencies_without_network(self):
        self.assertIn('IMPORT_OK import', self.run_startup('import').stdout)

    def test_real_cli_help_starts_without_collection(self):
        self.assertIn('--incremental', self.run_startup('help').stdout)

    def test_missing_bs4_is_explicitly_error_return_not_old_exception(self):
        self.assertIn('IMPORT_OK missing-bs4', self.run_startup('missing-bs4').stdout)


if __name__ == '__main__':
    unittest.main()
