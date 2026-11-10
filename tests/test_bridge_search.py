"""Bounded read-only search and reveal behaviour (game-thread + HTTP)."""
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

from renpy_inspector.bridge_search import (
    build_search_results, build_reveal_chain, validate_search_request,
    SEARCH_VISIT_LIMIT, SEARCH_RESULT_LIMIT)
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


def sample_providers():
    root = ModuleType('store')
    root.player = {'stats': {'health': 75, 'xp': 22}}
    root.private_data = {'__secret': 'not exposed', 'public': 2}
    root.loop = {}
    root.loop['self'] = root.loop
    for index in range(930):
        setattr(root, 'field_{:04d}'.format(index), index)
    persistent = {'persistent_hp': 100}
    return root, {'store': lambda: root, 'persistent': lambda: persistent}


class SearchCoreTests(unittest.TestCase):
    def setUp(self):
        self.root, self.providers = sample_providers()

    def test_search_finds_unloaded_root_beyond_first_page(self):
        found = build_search_results(self.providers, 'store', 'field_0900')
        self.assertTrue(any('field_0900' in item['name'] for item in found['results']))
        self.assertGreater(found['scanned'], 80)
        self.assertLessEqual(found['scanned'], SEARCH_VISIT_LIMIT)

    def test_find_nested_and_persistent_without_evaluating_code(self):
        found = build_search_results(self.providers, 'all', 'health')
        self.assertTrue(any('health' in node['path'] for node in found['results']))
        self.assertLessEqual(len(found['results']), SEARCH_RESULT_LIMIT)
        persist = build_search_results(self.providers, 'all', 'persistent_hp')
        self.assertTrue(any(n['scope'] == 'persistent' for n in persist['results']))

    def test_reveal_returns_typed_ancestors_with_valid_keys(self):
        chain = build_reveal_chain(self.providers, 'store', (
            ('attribute', 'player'), ('key', 'stats'), ('key', 'health')))
        self.assertEqual(len(chain['chain']), 3)
        self.assertEqual(chain['chain'][-1]['preview'], '75')
        self.assertEqual([len(json.loads(n['key'])[1]) for n in chain['chain']], [1, 2, 3])

    def test_security_validation_and_invisible_paths(self):
        for arguments in [('store', 'x'), ('unknown', 'xp'), ('store', ' '*3),
                          ('store', 'ab\ncd'), ('store', 'x'*65)]:
            with self.subTest(args=arguments), self.assertRaises(ValueError):
                validate_search_request(*arguments)
        for path in [
            (('attribute', '__class__'),), (('attribute', 'missing'),),
            (('attribute', 'loop'), ('key', 'self')),
            (('attribute', 'player'), ('key', '__nonexistent')),
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_reveal_chain(self.providers, 'store', path)

    def test_search_never_calls_user_properties_or_repr(self):
        class Sneaky(object):
            @property
            def health(self):
                raise AssertionError('Property must not execute')
            def __repr__(self):
                raise AssertionError('repr must not execute')
        self.root.sneaky = Sneaky()
        found = build_search_results(self.providers, 'store', 'health')
        self.assertTrue(all('sneaky.health' not in item['path'] for item in found['results']))
        self.assertTrue(any('health' in item['name'] for item in found['results']))

    def test_limits_are_reported_not_hidden(self):
        self.root.extra_nested = {'container': {'health': 5}}
        for idx in range(1250):
            setattr(self.root, 'field_{:04d}'.format(idx), idx)
        result = build_search_results(self.providers, 'store', 'unlikely_xyz_pattern')
        self.assertTrue(result['limited'])
        self.assertLessEqual(result['scanned'], SEARCH_VISIT_LIMIT)


class SearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        Path(self.dir.name, 'index.html').write_text('<html>local</html>')
        self.root = ModuleType('store')
        self.root.player = {'stats': {'health': 44}}
        self.calls = []
        def provider():
            self.calls.append(threading.current_thread().name)
            return self.root
        self.inspector = Inspector()
        self.inspector.bind(provider, lambda: {})
        self.bridge = InspectorBridge(self.inspector, self.dir.name)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.base = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.thread = threading.current_thread().name
        self.calls[:] = []

    def req(self, endpoint, params, token=None, origin=None):
        headers = {'X-Inspector-Token': self.bridge.token if token is None else token}
        if origin:
            headers['Origin'] = origin
        req = Request(self.base + endpoint + '?' + urlencode(params), headers=headers)
        try:
            with urlopen(req, timeout=5) as r:
                return (r.status, json.loads(r.read().decode('ascii')))
        except HTTPError as e:
            return (e.code, None)

    def tick_request(self, endpoint, params):
        outputs = []
        worker = threading.Thread(target=lambda: outputs.append(self.req(endpoint, params)))
        worker.start()
        time.sleep(.12)
        self.assertEqual(self.calls, [])  # network thread did not inspect game
        self.assertEqual(len(self.bridge.pending_pages), 1)
        self.bridge.tick()
        worker.join(4.0)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.calls, [self.thread])
        return outputs[0]

    def test_authenticated_search_on_game_thread(self):
        status, payload = self.tick_request('/api/v1/search',
                                            {'scope': 'all', 'q': 'health'})
        self.assertEqual(status, 200)
        self.assertEqual(payload['results'][0]['preview'], '44')
        self.assertGreater(payload['captured_at'], 0)

    def test_authenticated_reveal_on_game_thread(self):
        status, payload = self.tick_request('/api/v1/reveal',
           {'scope': 'store', 'path': json.dumps([
                ['attribute', 'player'], ['key', 'stats'], ['key', 'health']])})
        self.assertEqual(status, 200)
        self.assertEqual(len(payload['chain']), 3)

    def test_reject_wrong_token_origin_and_untrusted_paths(self):
        invalid = {'scope': 'store', 'q': '__'}
        self.assertEqual(self.req('/api/v1/search', invalid, token='nope')[0], 401)
        self.assertEqual(self.req('/api/v1/search', invalid,
                                  origin='https://evil.invalid')[0], 403)
        self.assertEqual(self.req('/api/v1/search', {'scope':'store', 'q':'a'})[0], 400)
        self.assertEqual(self.req('/api/v1/reveal', {'scope':'store',
            'path':json.dumps([['attribute', '__class__']])})[0], 400)


if __name__ == '__main__':
    unittest.main()
