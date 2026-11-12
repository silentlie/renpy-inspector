"""Full-value reads: game-thread safety, primitive caps and HTTP boundaries."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import ModuleType
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.bridge_paging import (
    MAX_FULL_VALUE_CHARS, build_full_value,
)
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class FullValueTests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType('store')
        self.store.description = 'Chapter 1\nLine 2: 🎭 <script>alert(1)</script>'
        self.store.long_text = 'A' * (MAX_FULL_VALUE_CHARS + 11)
        self.store.player = {'bio': 'First line\nSecond line'}
        self.store.score = 12345
        self.store.active = True
        self.store.empty = None
        self.store.huge = 1 << 4097
        self.store.reference = []
        self.store.reference.append(self.store.reference)
        self.providers = {'store': lambda: self.store, 'persistent': lambda: {'flag': False}}

    def full(self, *parts, scope='store'):
        return build_full_value(self.providers, scope, tuple(parts))

    def test_preserves_raw_multiline_unicode_and_html_as_text(self):
        value = self.full(('attribute', 'description'))
        self.assertEqual(value['kind'], 'string')
        self.assertEqual(value['text'], self.store.description)
        self.assertFalse(value['truncated'])
        self.assertEqual(value['length'], len(self.store.description))
        nested = self.full(('attribute', 'player'), ('key', 'bio'))
        self.assertEqual(nested['text'], 'First line\nSecond line')
        self.assertEqual(self.full(('key', 'flag'), scope='persistent')['text'], 'False')

    def test_enforces_budget_and_reports_exact_length(self):
        value = self.full(('attribute', 'long_text'))
        self.assertTrue(value['truncated'])
        self.assertEqual(value['length'], MAX_FULL_VALUE_CHARS + 11)
        self.assertEqual(len(value['text']), MAX_FULL_VALUE_CHARS)
        self.assertEqual(value['limit'], MAX_FULL_VALUE_CHARS)

    def test_builtin_scalars_without_unsafe_repr(self):
        self.assertEqual(self.full(('attribute', 'score'))['text'], '12345')
        self.assertEqual(self.full(('attribute', 'active'))['text'], 'True')
        self.assertEqual(self.full(('attribute', 'empty'))['kind'], 'null')
        self.assertEqual(self.full(('attribute', 'empty'))['text'], 'None')
        self.assertEqual(self.full(('attribute', 'huge'))['kind'], 'unsupported')
        self.assertIsNone(self.full(('attribute', 'huge'))['text'])

        class Hostile(object):
            @property
            def forbidden(self):
                raise AssertionError('property invoked')
            def __repr__(self):
                raise AssertionError('repr invoked')
            def __str__(self):
                raise AssertionError('str invoked')
        self.store.hostile = Hostile()
        value = self.full(('attribute', 'hostile'))
        self.assertEqual(value['kind'], 'unsupported')
        self.assertIsNone(value['text'])
        self.assertEqual(self.full(('attribute', 'reference'), ('index', 0))['kind'], 'unsupported')

    def test_missing_and_invalid_paths(self):
        self.assertEqual(self.full(('attribute', 'player'), ('key', 'lost'))['kind'], 'missing')
        self.assertEqual(self.full(('attribute', 'reference'), ('index', 0),
                                   ('index', 0))['kind'], 'missing')
        for path in ((), (('attribute', '__dict__'),), (('index', True),)):
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_full_value(self.providers, 'store', path)


class FullValueHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        Path(self.temp.name, 'index.html').write_text('<html>test</html>')
        self.store = ModuleType('store')
        self.store.full = 'Hello\n' + 'X' * 250
        self.calls = []
        def provider():
            self.calls.append(threading.current_thread().name)
            return self.store
        controller = Inspector()
        controller.bind(provider, lambda: {})
        self.bridge = InspectorBridge(controller, self.temp.name)
        self.bridge.start()
        self.assertTrue(self.bridge.running, self.bridge.error)
        self.addCleanup(self.bridge.stop)
        self.host = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.calls[:] = []
        self.main_thread = threading.current_thread().name

    def fetch(self, path, token=None, origin=None, method='GET'):
        query = urlencode({'scope': 'store', 'path': json.dumps(path)})
        headers = {'X-Inspector-Token': self.bridge.token if token is None else token}
        if origin:
            headers['Origin'] = origin
        req = Request(self.host + '/api/v1/full-value?' + query,
                      headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode('ascii'))
        except HTTPError as error:
            return error.code, None

    def test_authenticated_full_value_reads_only_on_game_thread(self):
        results = []
        thread = threading.Thread(target=lambda: results.append(
            self.fetch([['attribute', 'full']])))
        thread.start()
        time.sleep(0.08)
        self.assertEqual(self.calls, [])
        self.bridge.tick()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0][0], 200)
        self.assertEqual(results[0][1]['text'], self.store.full)
        self.assertEqual(self.calls, [self.main_thread])
        self.assertEqual(results[0][1]['generation'], self.bridge.generation)
        self.assertIsInstance(results[0][1]['captured_at'], float)

    def test_auth_origin_validation_and_read_only_methods(self):
        path = [['attribute', 'full']]
        self.assertEqual(self.fetch(path, token='incorrect')[0], 401)
        self.assertEqual(self.fetch(path, origin='https://foreign.test')[0], 403)
        self.assertEqual(self.fetch(path, method='POST')[0], 405)
        self.assertEqual(self.fetch([['attribute', '__dict__']])[0], 400)

    def test_load_invalidates_queued_full_value(self):
        results = []
        thread = threading.Thread(target=lambda: results.append(
            self.fetch([['attribute', 'full']])))
        thread.start()
        time.sleep(0.08)
        self.bridge.invalidate()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0][0], 409)


if __name__ == '__main__':
    unittest.main()
