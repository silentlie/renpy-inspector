"""Opt-in primitive editing: strict CAS, safe containers, HTTP and threading."""
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
from renpy_inspector.edit_values import (
    EditConflict, EditUnsupported, _scalar, apply_primitive_edit,
    inspect_edit_target, validate_edit_request,
)
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class EditValueTests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType('store')
        self.store.score = 2
        self.store.text = 'Snow ☃\nLiteral <script>'
        self.store.flags = {'enabled': True, 'items': [3, 4], 'immutable': (1, 2)}
        self.store.decimal = 1.25
        self.store.empty = None
        self.store.other = object()
        self.store.large = 1 << 513
        self.providers = {'store': lambda: self.store,
                          'persistent': lambda: {'score': 10}}

    def get(self, *path, scope='store'):
        return inspect_edit_target(self.providers, scope, tuple(path))

    def apply(self, path, target, text):
        return apply_primitive_edit(self.providers, 'store', tuple(path),
                                    target['expected'], target['type'], text)

    def test_existing_builtins_nested_dicts_and_lists(self):
        for path, new, getter in (
                ((('attribute', 'score'),), '19', lambda: self.store.score),
                ((('attribute', 'text'),), 'New\n☃', lambda: self.store.text),
                ((('attribute', 'flags'), ('key', 'enabled')), 'False',
                 lambda: self.store.flags['enabled']),
                ((('attribute', 'flags'), ('key', 'items'), ('index', 1)), '99',
                 lambda: self.store.flags['items'][1]),
                ((('attribute', 'decimal'),), '2.75', lambda: self.store.decimal)):
            with self.subTest(path=path):
                target = self.get(*path)
                self.assertTrue(target['editable'], target)
                self.assertTrue(self.apply(path, target, new)['applied'])
                self.assertEqual(getter(), {'19': 19, 'New\n☃': 'New\n☃',
                                            'False': False, '99': 99, '2.75': 2.75}[new])

    def test_compare_and_swap_prevents_stale_edits_in_same_generation(self):
        path = (('attribute', 'score'),)
        old = self.get(*path)
        self.store.score = 3
        with self.assertRaises(EditConflict):
            self.apply(path, old, '4')
        self.assertEqual(self.store.score, 3)
        new = self.get(*path)
        self.assertTrue(self.apply(path, new, '4')['applied'])
        with self.assertRaises(EditConflict):
            self.apply(path, new, '5')
        self.assertEqual(self.store.score, 4)

    def test_rejects_custom_mutation_surface_and_uneditable_primitives(self):
        class Hostile(object):
            def __repr__(self):
                raise AssertionError('unsafe repr')
            def __setattr__(self, name, value):
                raise AssertionError('unsafe setter')
        self.store.other = Hostile()
        self.store.custom = Hostile()
        self.assertFalse(self.get(('attribute', 'custom'))['editable'])
        self.assertFalse(self.get(('attribute', 'empty'))['editable'])
        self.assertFalse(self.get(('attribute', 'large'))['editable'])
        self.assertFalse(self.get(('attribute', 'flags'), ('key', 'immutable'),
                                  ('index', 0))['editable'])
        self.assertFalse(self.get(('attribute', 'custom'),
                                  ('attribute', 'value'))['editable'])
        self.assertFalse(self.get(('key', 'score'), scope='persistent')['editable'])
        self.assertEqual(self.store.flags['immutable'], (1, 2))

    def test_rejects_path_creation_type_change_noop_and_unsafe_input(self):
        path = (('attribute', 'score'),)
        target = self.get(*path)
        for text in ('0x10', 'True', '1.2', '1 << 2', '9' * 160):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                self.apply(path, target, text)
        self.assertEqual(self.store.score, 2)
        with self.assertRaises(ValueError):
            self.apply(path, target, '2')
        with self.assertRaises(ValueError):
            self.get(('attribute', '__dict__'))
        self.assertFalse(self.get(('attribute', 'no_such_variable'))['editable'])
        self.assertEqual(self.get(('attribute', 'no_such_variable'))['reason'],
                         'Variable is no longer visible')

    def test_signed_zero_float_edits_preserve_the_ieee_sign(self):
        path = (('attribute', 'decimal'),)
        self.store.decimal = 0.0
        positive = self.get(*path)
        self.assertTrue(self.apply(path, positive, '-0.0')['applied'])
        self.assertEqual(repr(self.store.decimal), '-0.0')
        negative = self.get(*path)
        self.assertTrue(self.apply(path, negative, '0.0')['applied'])
        self.assertEqual(repr(self.store.decimal), '0.0')

    def test_float_inf_boolean_and_unbounded_text_rejected(self):
        float_path = (('attribute', 'decimal'),)
        before = self.get(*float_path)
        with self.assertRaises(ValueError):
            self.apply(float_path, before, '1e999')
        bool_path = (('attribute', 'flags'), ('key', 'enabled'))
        before = self.get(*bool_path)
        with self.assertRaises(ValueError):
            self.apply(bool_path, before, 'false')
        self.store.text = 'T' * 1025
        self.assertFalse(self.get(('attribute', 'text'))['editable'])
        self.assertIsNone(_scalar(self.store.text))

    def test_http_payload_strict_schema_and_no_persistent(self):
        payload = {'scope': 'store', 'path': [['attribute', 'score']],
                   'generation': 0, 'expected': 'a' * 64,
                   'type': 'int', 'text': '3'}
        self.assertEqual(validate_edit_request(payload)[-1], '3')
        for override in (
                {'scope': 'persistent'},
                {'generation': True},
                {'path': [['attribute', '__class__']]},
                {'path': [['member', 'hidden']]},
                {'type': 'object'},
                {'expected': 'wrong'},
                {'text': 'a' * 1025}):
            invalid = dict(payload, **override)
            with self.subTest(override=override), self.assertRaises(ValueError):
                validate_edit_request(invalid)


class EditHTTPTests(unittest.TestCase):
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
        self.bridge.start()
        self.assertTrue(self.bridge.running, self.bridge.error)
        self.addCleanup(self.bridge.stop)
        self.url = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.game_thread = threading.current_thread().name
        self.thread_names[:] = []

    def request(self, method, path, payload=None, token=None, origin=None, host=None):
        headers = {'X-Inspector-Token': self.bridge.token if token is None else token}
        if origin is not None:
            headers['Origin'] = origin
        if host is not None:
            headers['Host'] = host
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
            except (ValueError, UnicodeError):
                return error.code, None

    def target_url(self):
        return '/api/v1/edit-target?' + urlencode(
            {'scope': 'store', 'path': json.dumps([['attribute', 'score']])})

    def run_threaded(self, method, path, payload=None):
        result = []
        thread = threading.Thread(target=lambda: result.append(
            self.request(method, path, payload)))
        thread.start()
        time.sleep(0.08)
        self.assertEqual(self.thread_names, [])  # HTTP does not read Store
        self.bridge.tick()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        return result[0]

    def test_disabled_by_default_for_get_and_put(self):
        self.assertFalse(self.bridge.editing_enabled)
        self.assertEqual(self.request('GET', self.target_url())[0], 403)
        self.assertEqual(self.request('PUT', '/api/v1/edit', {})[0], 403)
        self.assertEqual(self.store.score, 2)
        self.assertFalse(json.loads(self.bridge.cached_bytes)['capabilities']['primitive_edits'])

    def test_game_enabled_read_and_write_on_interaction_thread(self):
        self.bridge.configure_variable_editing(True)
        self.bridge.publish()
        self.thread_names[:] = []
        self.assertTrue(json.loads(self.bridge.cached_bytes)['capabilities']['primitive_edits'])
        code, target = self.run_threaded('GET', self.target_url())
        self.assertEqual(code, 200)
        self.assertEqual(self.thread_names, [self.game_thread])
        self.assertEqual(target['type'], 'int')
        self.assertTrue(target['editable'])
        self.thread_names[:] = []
        payload = {'scope': 'store', 'path': [['attribute', 'score']],
                   'generation': target['generation'], 'expected': target['expected'],
                   'type': target['type'], 'text': '34'}
        code, response = self.run_threaded('PUT', '/api/v1/edit', payload)
        self.assertEqual(code, 200)
        self.assertTrue(response['applied'])
        self.assertEqual(response['generation'], target['generation'] + 1)
        self.assertEqual(self.store.score, 34)
        self.assertTrue(self.thread_names)
        self.assertTrue(all(name == self.game_thread for name in self.thread_names))
        self.assertEqual(json.loads(self.bridge.cached_bytes)['scopes']['store'][0]['preview'], '34')
        timeline = json.loads(self.bridge.cached_bytes)['runtime']['events']
        self.assertTrue(any(e['kind'] == 'invalidation' and e['signal'] == 'edit' for e in timeline))
        self.thread_names[:] = []
        fresh_code, fresh_target = self.run_threaded('GET', self.target_url())
        self.assertEqual(fresh_code, 200)
        self.store.score = 35  # Simulate a game script assignment without an Inspector epoch.
        stale_payload = dict(payload, generation=fresh_target['generation'],
                              expected=fresh_target['expected'], text='36')
        conflict = self.run_threaded('PUT', '/api/v1/edit', stale_payload)
        self.assertEqual(conflict[0], 409)
        self.assertEqual(conflict[1]['code'], 'value_changed')
        self.assertEqual(conflict[1]['current_target']['text'], '35')
        self.assertEqual(conflict[1]['current_target']['generation'], self.bridge.generation)
        self.assertEqual(self.store.score, 35)

    def test_http_auth_origin_and_invalid_payload_fail_closed(self):
        self.bridge.configure_variable_editing(True)
        payload = {'scope': 'store', 'path': [['attribute', 'score']],
                   'generation': 0, 'expected': 'a' * 64,
                   'type': 'int', 'text': '4'}
        self.assertEqual(self.request('PUT', '/api/v1/edit', payload, token='wrong')[0], 401)
        self.assertEqual(self.request('PUT', '/api/v1/edit', payload,
                                      origin='https://evil.invalid')[0], 403)
        self.assertEqual(self.request('PUT', '/api/v1/edit', payload,
                                      host='evil.invalid')[0], 403)
        self.assertEqual(self.request('POST', '/api/v1/edit', payload)[0], 405)
        self.assertEqual(self.request('PUT', '/api/v1/edit', dict(payload, scope='persistent'))[0], 400)
        self.assertEqual(self.request('PUT', '/api/v1/edit', dict(payload, type='obj'))[0], 400)
        self.assertEqual(self.store.score, 2)

    def test_conflicts_without_generation_change_and_queued_load_reset(self):
        self.bridge.configure_variable_editing(True)
        self.thread_names[:] = []
        code, target = self.run_threaded('GET', self.target_url())
        self.assertEqual(code, 200)
        payload = {'scope': 'store', 'path': [['attribute', 'score']],
                   'generation': target['generation'], 'expected': target['expected'],
                   'type': target['type'], 'text': '10'}
        self.store.score = 11
        self.thread_names[:] = []
        self.assertEqual(self.run_threaded('PUT', '/api/v1/edit', payload)[0], 409)
        self.assertEqual(self.store.score, 11)
        result = []
        thread = threading.Thread(target=lambda: result.append(
            self.request('PUT', '/api/v1/edit', payload)))
        thread.start()
        time.sleep(0.08)
        self.bridge.invalidate(reason='after_load')
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0][0], 409)
        self.assertEqual(self.store.score, 11)


if __name__ == '__main__':
    unittest.main()
