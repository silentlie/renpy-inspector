"""HTTP, auth, generation and interaction-thread coverage for undo/redo."""
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


class EditHistoryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        Path(self.temp.name, 'index.html').write_text('<html>test</html>')
        self.store = ModuleType('store')
        self.store.score = 2
        self.thread_names = []

        def provider():
            self.thread_names.append(threading.current_thread().name)
            return self.store

        controller = Inspector()
        controller.bind(provider, lambda: {})
        self.bridge = InspectorBridge(controller, self.temp.name)
        self.bridge.configure_variable_editing(True)
        self.bridge.start()
        self.assertTrue(self.bridge.running, self.bridge.error)
        self.addCleanup(self.bridge.stop)
        self.url = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.game_thread = threading.current_thread().name
        self.thread_names[:] = []

    def request(self, method, path, payload=None, token=None):
        headers = {'X-Inspector-Token': self.bridge.token if token is None else token}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        req = Request(self.url + path, method=method, headers=headers, data=data)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode('ascii'))
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode('ascii'))
            except ValueError:
                return error.code, None

    def threaded(self, method, path, payload=None):
        result = []
        thread = threading.Thread(target=lambda: result.append(
            self.request(method, path, payload)))
        thread.start()
        time.sleep(0.06)
        self.bridge.tick()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertTrue(all(name == self.game_thread for name in self.thread_names))
        self.thread_names[:] = []
        return result[0]

    def edit_score(self, value):
        query = urlencode({'scope': 'store',
                           'path': json.dumps([['attribute', 'score']])})
        code, target = self.threaded('GET', '/api/v1/edit-target?' + query)
        self.assertEqual(code, 200)
        payload = {'scope': 'store', 'path': [['attribute', 'score']],
                   'generation': target['generation'], 'expected': target['expected'],
                   'type': target['type'], 'text': str(value)}
        code, result = self.threaded('PUT', '/api/v1/edit', payload)
        self.assertEqual(code, 200)
        self.assertTrue(result['applied'])
        return result

    def history_action(self, action, snapshot):
        entry_id = snapshot['undo_entry_id'] if action == 'undo' else snapshot['redo_entry_id']
        return self.threaded('PUT', '/api/v1/edit-history', {
            'action': action, 'generation': snapshot['generation'],
            'entry_id': entry_id,
        })

    def test_http_edit_undo_redo_and_generation_advance(self):
        edited = self.edit_score(17)
        self.assertEqual(self.store.score, 17)
        first = edited['edit_history']
        self.assertTrue(first['can_undo'])
        self.assertEqual(first['entries'][-1]['before'], '2')
        self.assertEqual(first['entries'][-1]['after'], '17')

        status, undone = self.history_action('undo', first)
        self.assertEqual(status, 200)
        self.assertTrue(undone['applied'])
        self.assertEqual(self.store.score, 2)
        self.assertEqual(undone['generation'], first['generation'] + 1)
        self.assertFalse(undone['edit_history']['can_undo'])
        self.assertTrue(undone['edit_history']['can_redo'])
        self.assertEqual(undone['edit_history']['entries'][-1]['status'], 'undone')

        status, redone = self.history_action('redo', undone['edit_history'])
        self.assertEqual(status, 200)
        self.assertTrue(redone['applied'])
        self.assertEqual(self.store.score, 17)
        self.assertEqual(redone['generation'], undone['generation'] + 1)
        self.assertTrue(redone['edit_history']['can_undo'])
        self.assertFalse(redone['edit_history']['can_redo'])
        self.assertEqual(redone['edit_history']['entries'][-1]['status'], 'applied')
        snapshot = json.loads(self.bridge.cached_bytes)
        self.assertEqual(snapshot['edit_history'], redone['edit_history'])
        self.assertTrue(any(event.get('signal') == 'undo' for event in snapshot['runtime']['events']))
        self.assertTrue(any(event.get('signal') == 'redo' for event in snapshot['runtime']['events']))

    def test_same_generation_external_write_conflicts_and_retires_entry(self):
        edited = self.edit_score(17)
        self.store.score = 99
        status, response = self.history_action('undo', edited['edit_history'])
        self.assertEqual(status, 409)
        self.assertEqual(self.store.score, 99)
        self.assertEqual(response['edit_history']['entries'][-1]['status'], 'conflicted')
        self.assertFalse(response['edit_history']['can_undo'])

    def test_new_edit_after_undo_discards_redo_branch(self):
        edited = self.edit_score(17)
        status, undone = self.history_action('undo', edited['edit_history'])
        self.assertEqual(status, 200)
        self.assertEqual(self.store.score, 2)
        newer = self.edit_score(23)
        self.assertEqual(self.store.score, 23)
        history = newer['edit_history']
        self.assertFalse(history['can_redo'])
        self.assertEqual(history['entries'][-2]['status'], 'superseded')
        self.assertEqual(history['entries'][-1]['status'], 'applied')

    def test_load_reset_clears_history_and_stale_generation_cannot_undo(self):
        edited = self.edit_score(17)
        self.bridge.invalidate(reason='after_load')
        self.assertEqual(self.bridge.edit_history.snapshot(self.bridge.generation)['entries'], [])
        status, response = self.history_action('undo', edited['edit_history'])
        self.assertEqual(status, 409)
        self.assertEqual(self.store.score, 17)
        self.assertEqual(response['edit_history']['entries'], [])

    def test_auth_validation_and_disabled_by_default(self):
        self.assertEqual(self.request('PUT', '/api/v1/edit-history', {
            'action': 'undo', 'generation': 0, 'entry_id': 1}, token='wrong')[0], 401)
        self.assertEqual(self.request('POST', '/api/v1/edit-history', {
            'action': 'undo', 'generation': 0, 'entry_id': 1})[0], 405)
        self.assertEqual(self.request('PUT', '/api/v1/edit-history', {
            'action': 'execute', 'generation': 0, 'entry_id': 1})[0], 400)
        self.bridge.configure_variable_editing(False)
        self.assertEqual(self.request('PUT', '/api/v1/edit-history', {
            'action': 'undo', 'generation': 0, 'entry_id': 1})[0], 403)
        self.assertEqual(self.store.score, 2)


if __name__ == '__main__':
    unittest.main()
