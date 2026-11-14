"""Authenticated HTTP preferences and direct favourites watch integration."""
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
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class FavoriteApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        Path(self.directory.name, 'index.html').write_text('<html>fixture</html>')
        self.store = ModuleType('store')
        self.store.player = {'stats': {'hp': 51}}
        self.workers = []
        def root():
            self.workers.append(threading.current_thread().name)
            return self.store
        self.inspector = Inspector()
        self.inspector.bind(root, lambda: {})
        self.bridge = InspectorBridge(self.inspector, self.directory.name)
        self.bridge.configure_favourites_directory(self.directory.name)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.base = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.origin_thread = threading.current_thread().name
        self.workers[:] = []
        self.location = {'scope': 'store', 'key': json.dumps([
            'store', [['attribute', 'player'], ['key', 'stats'], ['key', 'hp']]
        ], separators=(',', ':'))}

    def request(self, path, method='GET', body=None, token=None, origin=None):
        headers = {'X-Inspector-Token': self.bridge.token if token is None else token}
        if origin: headers['Origin'] = origin
        data = json.dumps(body).encode('utf-8') if body is not None else None
        if data is not None: headers['Content-Type'] = 'application/json'
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as e:
            if e.headers.get('Content-Type', '').startswith('application/json'):
                return e.code, json.load(e)
            return e.code, {}

    def test_saved_favourites_survive_restart_and_port_change(self):
        status, initial = self.request('/api/v1/favourites')
        self.assertEqual(status, 200)
        self.assertFalse(initial['initialized'])
        status, saved = self.request('/api/v1/favourites', 'PUT',
            {'version': 1, 'favourites': [self.location]})
        self.assertEqual(status, 200)
        self.assertEqual(len(saved['favourites']), 1)
        self.bridge.stop()
        self.bridge.start()
        self.base = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        status, recovered = self.request('/api/v1/favourites')
        self.assertEqual(status, 200)
        self.assertTrue(recovered['initialized'])
        self.assertEqual(recovered['favourites'], saved['favourites'])
        self.request('/api/v1/favourites', 'PUT', {'version': 1, 'favourites': []})
        self.assertEqual(self.request('/api/v1/favourites')[1]['favourites'], [])

    def test_untrusted_requests_cannot_write_preferences(self):
        self.assertEqual(self.request('/api/v1/favourites', 'PUT',
            {'version':1,'favourites':[self.location]}, token='wrong')[0], 401)
        self.assertEqual(self.request('/api/v1/favourites', 'PUT',
            {'version':1,'favourites':[self.location]}, origin='https://evil.invalid')[0], 403)
        self.assertEqual(self.request('/api/v1/favourites', 'PUT',
            {'version':1,'favourites':[{'scope':'store','key':'not JSON'}]})[0], 400)
        self.assertEqual(self.request('/api/v1/snapshot', 'PUT',
            {'version':1,'favourites':[]})[0], 405)
        self.assertFalse(self.request('/api/v1/favourites')[1]['initialized'])

    def test_revision_cas_prevents_stale_tabs_overwriting_pins(self):
        status, initial = self.request('/api/v1/favourites')
        self.assertEqual(initial['revision'], 0)
        status, first = self.request('/api/v1/favourites', 'PUT', {
            'version': 1, 'revision': 0, 'favourites': [self.location]})
        self.assertEqual(status, 200)
        self.assertEqual(first['revision'], 1)

        status, conflict = self.request('/api/v1/favourites', 'PUT', {
            'version': 1, 'revision': 0, 'favourites': []})
        self.assertEqual(status, 409)
        self.assertEqual(conflict['revision'], 1)
        self.assertEqual(conflict['favourites'], [self.location])

        status, second = self.request('/api/v1/favourites', 'PUT', {
            'version': 1, 'revision': conflict['revision'], 'favourites': []})
        self.assertEqual(status, 200)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['favourites'], [])
        self.bridge.stop()
        self.bridge.start()
        self.base = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.assertEqual(self.request('/api/v1/favourites')[1]['revision'], 2)

    def test_invalid_revisions_are_rejected_without_changing_file(self):
        for revision in [True, -1, 2 ** 53, '0', None]:
            status, unused = self.request('/api/v1/favourites', 'PUT', {
                'version': 1, 'revision': revision, 'favourites': [self.location]})
            self.assertEqual(status, 400)
        self.assertEqual(self.request('/api/v1/favourites')[1]['revision'], 0)

    def test_unicode_typed_paths_are_canonical_and_survive_reload(self):
        path = ['store', [['attribute', 'café']]]
        raw = {'scope': 'store', 'key': json.dumps(
            path, ensure_ascii=False, separators=(',', ':'))}
        canonical = {'scope': 'store', 'key': json.dumps(
            path, ensure_ascii=True, separators=(',', ':'))}
        status, saved = self.request('/api/v1/favourites', 'PUT', {
            'version': 1, 'revision': 0, 'favourites': [raw]})
        self.assertEqual(status, 200)
        self.assertEqual(saved['favourites'], [canonical])
        self.assertEqual(self.request('/api/v1/favourites')[1]['favourites'],
                         [canonical])
        self.bridge.stop()
        self.bridge.start()
        self.base = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.assertEqual(self.request('/api/v1/favourites')[1]['favourites'],
                         [canonical])

    def test_ascii_expansion_cannot_persist_unreadable_long_key(self):
        raw = {'scope': 'store', 'key': json.dumps(
            ['store', [['attribute', 'é' * 400]]],
            ensure_ascii=False, separators=(',', ':'))}
        self.assertLess(len(raw['key']), 2048)
        status, unused = self.request('/api/v1/favourites', 'PUT', {
            'version': 1, 'revision': 0, 'favourites': [raw]})
        self.assertEqual(status, 400)
        fresh = self.request('/api/v1/favourites')[1]
        self.assertEqual(fresh['revision'], 0)
        self.assertFalse(fresh['initialized'])

    def test_simultaneous_writes_have_single_cas_winner(self):
        results = []
        barrier = threading.Barrier(2)
        def worker():
            barrier.wait()
            results.append(self.request('/api/v1/favourites', 'PUT', {
                'version': 1, 'revision': 0, 'favourites': [self.location]}))
        workers = [threading.Thread(target=worker) for unused in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(5)
        self.assertEqual(sorted([status for status, unused in results]), [200, 409])
        self.assertEqual(self.request('/api/v1/favourites')[1]['revision'], 1)

    def test_legacy_favourites_file_is_migrated_on_first_revision_write(self):
        file_path = Path(self.directory.name, 'renpy-inspector-browser-favourites.json')
        file_path.write_text(json.dumps({'version': 1, 'favourites': [self.location]}))
        status, legacy = self.request('/api/v1/favourites')
        self.assertEqual(status, 200)
        self.assertEqual(legacy['revision'], 0)
        self.assertTrue(legacy['initialized'])
        status, saved = self.request('/api/v1/favourites', 'PUT', {
            'version': 1, 'revision': 0, 'favourites': [self.location]})
        self.assertEqual(status, 200)
        self.assertEqual(saved['revision'], 1)

    def test_direct_value_read_is_game_thread_only(self):
        path = [['attribute', 'player'], ['key', 'stats'], ['key', 'hp']]
        params = urlencode({'scope': 'store', 'path': json.dumps(path)})
        responses = []
        thread = threading.Thread(target=lambda: responses.append(
            self.request('/api/v1/value?' + params)))
        thread.start()
        time.sleep(0.12)
        self.assertEqual(self.workers, [])
        self.bridge.tick()
        thread.join(4.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(responses[0][0], 200)
        self.assertEqual(responses[0][1]['node']['preview'], '51')
        self.assertGreater(responses[0][1]['captured_at'], 0)
        self.assertEqual(self.workers, [self.origin_thread])
        self.store.player['stats']['hp'] = 77
        changed = []
        thread = threading.Thread(target=lambda: changed.append(
            self.request('/api/v1/value?' + params)))
        thread.start()
        time.sleep(0.12)
        self.bridge.tick()
        thread.join(4.0)
        self.assertEqual(changed[0][1]['node']['preview'], '77')

    def test_direct_value_auth_and_private_paths(self):
        path = urlencode({'scope': 'store',
                          'path':json.dumps([['attribute', '__class__']])})
        self.assertEqual(self.request('/api/v1/value?' + path)[0], 400)
        self.assertEqual(self.request('/api/v1/value?' + path,
            token='wrong')[0], 401)
        self.assertEqual(self.request('/api/v1/value?' + path,
            origin='https://evil.invalid')[0], 403)


if __name__ == '__main__':
    unittest.main()
