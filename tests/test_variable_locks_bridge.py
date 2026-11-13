"""HTTP, game-thread and edit/undo enforcement tests for variable locks."""
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


class VariableLocksHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        Path(self.temp.name, 'index.html').write_text('<html>test</html>')
        self.store = ModuleType('store')
        self.store.score = 2
        self.store.profile = {'hp': 10}
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

    def simultaneous(self, requests):
        results = [None] * len(requests)
        threads = []
        for index, (method, path, payload) in enumerate(requests):
            thread = threading.Thread(target=lambda i=index, m=method, p=path, body=payload:
                                      results.__setitem__(i, self.request(m, p, body)))
            threads.append(thread)
            thread.start()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            with self.bridge.lock:
                if len(self.bridge.pending_pages) >= len(requests):
                    break
            time.sleep(0.01)
        with self.bridge.lock:
            self.assertGreaterEqual(len(self.bridge.pending_pages), len(requests))
        self.bridge.tick()
        for thread in threads:
            thread.join(4)
            self.assertFalse(thread.is_alive())
        self.assertTrue(all(name == self.game_thread for name in self.thread_names))
        self.thread_names[:] = []
        return results

    def target(self, path=None):
        path = path or [['attribute', 'score']]
        query = urlencode({'scope': 'store', 'path': json.dumps(path)})
        status, data = self.threaded('GET', '/api/v1/edit-target?' + query)
        self.assertEqual(status, 200)
        return data

    def lock(self, action, target, path=None):
        path = path or [['attribute', 'score']]
        return self.threaded('PUT', '/api/v1/locks', {
            'action': action, 'scope': 'store', 'path': path,
            'generation': target['generation'],
        })

    def edit(self, target, value, path=None):
        path = path or [['attribute', 'score']]
        return self.threaded('PUT', '/api/v1/edit', {
            'scope': 'store', 'path': path, 'generation': target['generation'],
            'expected': target['expected'], 'type': target['type'], 'text': str(value),
        })

    def test_lock_blocks_inspector_edit_but_does_not_advance_game_generation(self):
        target = self.target()
        status, locked = self.lock('lock', target)
        self.assertEqual(status, 200)
        self.assertTrue(locked['locked'])
        self.assertTrue(locked['changed'])
        self.assertEqual(locked['generation'], target['generation'])
        self.assertEqual(self.store.score, 2)
        self.assertTrue(self.bridge.variable_locks.is_locked(
            'store', (('attribute', 'score'),)))

        status, rejected = self.edit(target, 17)
        self.assertEqual(status, 423)
        self.assertEqual(self.store.score, 2)
        self.assertIn('locked', rejected['error'].lower())

        current = self.target()
        self.assertTrue(current['locked'])
        self.assertEqual(current['text'], '2')
        status, unlocked = self.lock('unlock', current)
        self.assertEqual(status, 200)
        self.assertFalse(unlocked['locked'])
        self.assertTrue(unlocked['changed'])
        self.assertEqual(unlocked['generation'], target['generation'])

        current = self.target()
        status, applied = self.edit(current, 17)
        self.assertEqual(status, 200)
        self.assertTrue(applied['applied'])
        self.assertEqual(self.store.score, 17)

    def test_python_dictionary_boolean_integer_alias_cannot_bypass_lock(self):
        self.store.flags = {True: 'guarded'}
        bool_path = [['attribute', 'flags'], ['key', True]]
        target = self.target(bool_path)
        self.assertTrue(target['editable'])
        self.assertEqual(self.lock('lock', target, bool_path)[0], 200)

        # Python resolves dict[True] and dict[1] to the same stored entry.
        int_alias_path = [['attribute', 'flags'], ['key', 1]]
        status, rejected = self.edit(target, 'changed', int_alias_path)
        self.assertEqual(status, 423)
        self.assertEqual(self.store.flags[True], 'guarded')
        self.assertIn('locked', rejected['error'].lower())

        # Either typed spelling must also be able to release that same lock.
        status, unlocked = self.lock('unlock', target, int_alias_path)
        self.assertEqual(status, 200)
        self.assertFalse(unlocked['locked'])

    def test_lock_blocks_undo_without_retiring_history_then_unlock_allows_it(self):
        target = self.target()
        status, edited = self.edit(target, 17)
        self.assertEqual(status, 200)
        history = edited['edit_history']
        current = self.target()
        status, locked = self.lock('lock', current)
        self.assertEqual(status, 200)

        undo = self.threaded('PUT', '/api/v1/edit-history', {
            'action': 'undo', 'generation': history['generation'],
            'entry_id': history['undo_entry_id'],
        })
        self.assertEqual(undo[0], 423)
        self.assertEqual(self.store.score, 17)
        self.assertTrue(self.bridge.edit_history.snapshot(self.bridge.generation)['can_undo'])

        status, unlocked = self.lock('unlock', current)
        self.assertEqual(status, 200)
        self.assertFalse(unlocked['locked'])
        retry = self.threaded('PUT', '/api/v1/edit-history', {
            'action': 'undo', 'generation': history['generation'],
            'entry_id': history['undo_entry_id'],
        })
        self.assertEqual(retry[0], 200)
        self.assertEqual(self.store.score, 2)

    def test_unrelated_edit_undo_and_redo_preserve_locks(self):
        nested_path = [['attribute', 'profile'], ['key', 'hp']]
        nested = self.target(nested_path)
        self.assertTrue(nested['editable'])
        self.assertEqual(self.lock('lock', nested, nested_path)[0], 200)
        score = self.target()
        status, edited = self.edit(score, 17)
        self.assertEqual(status, 200)
        self.assertTrue(self.bridge.variable_locks.is_locked(
            'store', (('attribute', 'profile'), ('key', 'hp'))))
        history = edited['edit_history']
        undo = self.threaded('PUT', '/api/v1/edit-history', {
            'action': 'undo', 'generation': history['generation'],
            'entry_id': history['undo_entry_id'],
        })
        self.assertEqual(undo[0], 200)
        self.assertTrue(self.bridge.variable_locks.is_locked(
            'store', (('attribute', 'profile'), ('key', 'hp'))))
        redo = self.threaded('PUT', '/api/v1/edit-history', {
            'action': 'redo', 'generation': undo[1]['generation'],
            'entry_id': undo[1]['edit_history']['redo_entry_id'],
        })
        self.assertEqual(redo[0], 200)
        self.assertTrue(self.bridge.variable_locks.is_locked(
            'store', (('attribute', 'profile'), ('key', 'hp'))))

    def test_lock_does_not_intercept_game_script_mutations(self):

        target = self.target()
        self.assertEqual(self.lock('lock', target)[0], 200)
        # A normal game script assignment is outside the inspector lock system.
        self.store.score = 99
        self.assertTrue(self.bridge.variable_locks.is_locked(
            'store', (('attribute', 'score'),)))
        self.bridge.publish()  # Background monitoring runs on the game thread.
        cached = json.loads(self.bridge.cached_bytes.decode('ascii'))
        self.assertTrue(cached['locks']['entries'][0]['stale'])
        fresh = self.target()
        self.assertTrue(fresh['locked'])
        self.assertTrue(fresh['lock_stale'])
        self.assertEqual(fresh['lock_stale_reason'], 'value_changed')
        self.assertEqual(fresh['text'], '99')
        self.assertEqual(self.store.score, 99)

    def test_locked_path_can_be_unlocked_after_game_changes_it_to_unsupported_type(self):
        target = self.target()
        self.assertEqual(self.lock('lock', target)[0], 200)
        self.store.score = object()
        changed = self.target()
        self.assertFalse(changed['editable'])
        self.assertTrue(changed['locked'])
        self.assertTrue(changed['lock_stale'])
        self.assertEqual(changed['lock_stale_reason'], 'target_unavailable')
        status, unlocked = self.lock('unlock', changed)
        self.assertEqual(status, 200)
        self.assertFalse(unlocked['locked'])
        self.assertFalse(self.bridge.variable_locks.is_locked(
            'store', (('attribute', 'score'),)))

    def test_stale_lock_blocks_writes_until_explicit_refresh_or_unlock(self):
        target = self.target()
        self.assertEqual(self.lock('lock', target)[0], 200)
        self.store.score = 99
        self.bridge.publish()
        changed = self.target()
        self.assertTrue(changed['locked'])
        self.assertTrue(changed['lock_stale'])

        status, denied = self.edit(changed, 100)
        self.assertEqual(status, 423)
        self.assertTrue(denied['lock_stale'])
        self.assertEqual(self.store.score, 99)

        status, refreshed = self.lock('refresh', changed)
        self.assertEqual(status, 200)
        self.assertTrue(refreshed['locked'])
        self.assertFalse(refreshed['lock_stale'])
        self.assertEqual(refreshed['action'], 'refresh')

        current = self.target()
        self.assertTrue(current['locked'])
        self.assertFalse(current['lock_stale'])
        self.assertEqual(self.lock('unlock', current)[0], 200)
        current = self.target()
        self.assertEqual(self.edit(current, 100)[0], 200)
        self.assertEqual(self.store.score, 100)

    def test_stale_lock_does_not_hide_external_conflict_from_undo(self):
        target = self.target()
        status, edited = self.edit(target, 17)
        self.assertEqual(status, 200)
        history = edited['edit_history']
        current = self.target()
        self.assertEqual(self.lock('lock', current)[0], 200)
        self.store.score = 99

        undo = self.threaded('PUT', '/api/v1/edit-history', {
            'action': 'undo', 'generation': history['generation'],
            'entry_id': history['undo_entry_id'],
        })
        self.assertEqual(undo[0], 423)
        self.assertTrue(undo[1]['lock_stale'])
        self.assertTrue(undo[1]['edit_history']['can_undo'])
        self.assertEqual(self.store.score, 99)

        current = self.target()
        self.assertTrue(current['lock_stale'])
        self.assertEqual(self.lock('refresh', current)[0], 200)
        current = self.target()
        self.assertEqual(self.lock('unlock', current)[0], 200)
        undo = self.threaded('PUT', '/api/v1/edit-history', {
            'action': 'undo', 'generation': history['generation'],
            'entry_id': history['undo_entry_id'],
        })
        self.assertEqual(undo[0], 409)
        self.assertEqual(undo[1]['code'], 'history_value_changed')
        self.assertEqual(self.store.score, 99)
        self.assertEqual(undo[1]['edit_history']['entries'][0]['status'], 'conflicted')

    def test_two_concurrent_browser_writes_from_one_generation_apply_at_most_once(self):
        target = self.target()
        payload_a = {
            'scope': 'store', 'path': [['attribute', 'score']],
            'generation': target['generation'], 'expected': target['expected'],
            'type': target['type'], 'text': '17',
        }
        payload_b = dict(payload_a, text='18')
        results = self.simultaneous([
            ('PUT', '/api/v1/edit', payload_a),
            ('PUT', '/api/v1/edit', payload_b),
        ])
        self.assertEqual(sorted(result[0] for result in results), [200, 409])
        self.assertIn(self.store.score, (17, 18))
        history = self.bridge.edit_history.snapshot(self.bridge.generation)
        self.assertEqual(len(history['entries']), 1)
        self.assertTrue(history['can_undo'])
        self.assertEqual(history['generation'], self.bridge.generation)

    def test_concurrent_lock_and_edit_cannot_both_succeed(self):
        target = self.target()
        lock_payload = {
            'action': 'lock', 'scope': 'store',
            'path': [['attribute', 'score']], 'generation': target['generation'],
        }
        edit_payload = {
            'scope': 'store', 'path': [['attribute', 'score']],
            'generation': target['generation'], 'expected': target['expected'],
            'type': target['type'], 'text': '17',
        }
        results = self.simultaneous([
            ('PUT', '/api/v1/locks', lock_payload),
            ('PUT', '/api/v1/edit', edit_payload),
        ])
        statuses = sorted(result[0] for result in results)
        self.assertEqual(statuses[0], 200)
        self.assertIn(statuses[1], (409, 423))
        self.assertFalse(statuses == [200, 200])
        if self.bridge.variable_locks.is_locked('store', (('attribute', 'score'),)):
            self.assertEqual(self.store.score, 2)
        else:
            self.assertEqual(self.store.score, 17)

    def test_repeated_load_and_rollback_cycles_clear_locks_and_history(self):
        for index, reason in enumerate(('after_load', 'legacy_rollback', 'after_load')):
            target = self.target()
            status, edited = self.edit(target, 10 + index)
            self.assertEqual(status, 200)
            current = self.target()
            self.assertEqual(self.lock('lock', current)[0], 200)
            old_generation = self.bridge.generation
            self.bridge.invalidate(reason=reason)
            self.assertGreater(self.bridge.generation, old_generation)
            snapshot = json.loads(self.bridge.cached_bytes.decode('ascii'))
            self.assertEqual(snapshot['locks']['entries'], [])
            self.assertEqual(snapshot['edit_history']['entries'], [])
            self.assertFalse(self.bridge.variable_locks.is_locked(
                'store', (('attribute', 'score'),)))
            stale = self.edit(current, 55)
            self.assertEqual(stale[0], 409)
            self.assertEqual(stale[1]['code'], 'generation_changed')

    def test_load_rollback_and_edit_disable_clear_locks(self):

        target = self.target()
        self.assertEqual(self.lock('lock', target)[0], 200)
        self.bridge.invalidate(reason='after_load')
        cached = json.loads(self.bridge.cached_bytes.decode('ascii'))
        self.assertEqual(cached['locks']['entries'], [])
        self.assertFalse(self.bridge.variable_locks.is_locked(
            'store', (('attribute', 'score'),)))
        stale_unlock = self.lock('unlock', target)
        self.assertEqual(stale_unlock[0], 409)

        fresh = self.target()
        self.assertEqual(self.lock('lock', fresh)[0], 200)
        self.bridge.invalidate(reason='legacy_rollback')
        self.assertEqual(self.bridge.variable_locks.snapshot()['entries'], [])
        self.bridge.configure_variable_editing(False)
        self.assertEqual(self.bridge.variable_locks.snapshot()['entries'], [])
        self.assertEqual(self.request('PUT', '/api/v1/locks', {
            'action': 'lock', 'scope': 'store',
            'path': [['attribute', 'score']], 'generation': self.bridge.generation,
        })[0], 403)

    def test_only_existing_editable_store_primitives_can_be_locked(self):
        target = self.target([['attribute', 'profile']])
        self.assertFalse(target['editable'])
        self.assertEqual(self.lock('lock', target, [['attribute', 'profile']])[0], 422)
        self.assertEqual(self.request('PUT', '/api/v1/locks', {
            'action': 'lock', 'scope': 'persistent',
            'path': [['key', 'score']], 'generation': self.bridge.generation,
        })[0], 400)

    def test_auth_method_and_payload_validation(self):
        payload = {'action': 'lock', 'scope': 'store',
                   'path': [['attribute', 'score']], 'generation': 0}
        self.assertEqual(self.request('PUT', '/api/v1/locks', payload, token='wrong')[0], 401)
        self.assertEqual(self.request('POST', '/api/v1/locks', payload)[0], 405)
        self.assertEqual(self.request('PUT', '/api/v1/locks', dict(payload, action='execute'))[0], 400)
        self.assertEqual(self.request('PUT', '/api/v1/locks', dict(payload, extra='x'))[0], 400)
        self.assertEqual(self.threaded('PUT', '/api/v1/locks', payload)[0], 200)


if __name__ == '__main__':
    unittest.main()
