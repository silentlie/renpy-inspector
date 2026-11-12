"""Read-only script label navigation, source safety and HTTP queue coverage."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.bridge_scripts import (
    MAX_LABEL_SCAN, LABEL_PAGE_SIZE, list_labels, source_excerpt,
    validate_label_request, validate_source_request)
from renpy_inspector.controller import Inspector


class ScriptFixture:
    def __init__(self, base):
        self.game_dir = base
        self.files = {}
        for name in ('script.rpy', 'chapters/intro.rpy'):
            target = Path(base, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(''.join('%s line %d\n' % (name, n)
                                      for n in range(1, 90)), encoding='utf-8')
        self.files = {
            'start': ('game/script.rpy', 5),
            'story.intro': ('game/chapters/intro.rpy', 12),
            'story.end': ('game/chapters/intro.rpy', 78),
            '_internal': ('game/script.rpy', 1),
            'engine_label': ('renpy/common/00library.rpy', 25),
        }
        self.names = list(self.files)
        self.calls = []
        self.game = SimpleNamespace(script=self)

    def get_all_labels(self):
        self.calls.append(threading.current_thread().name)
        return set(self.names)

    def lookup(self, label):
        filename, line = self.files[label]
        return SimpleNamespace(filename=filename, linenumber=line)


class ScriptCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = ScriptFixture(self.temp.name)

    def test_labels_are_searchable_by_name_and_file_and_paginated(self):
        first = list_labels(self.api, self.temp.name, 'story', 0, 1)
        self.assertEqual(len(first['labels']), 1)
        self.assertTrue(first['more'])
        second = list_labels(self.api, self.temp.name, 'story', 1, 1)
        self.assertEqual(len(second['labels']), 1)
        self.assertFalse(second['more'])
        self.assertEqual({x['name'] for x in first['labels'] + second['labels']},
                         {'story.intro', 'story.end'})
        by_file = list_labels(self.api, self.temp.name, 'intro.rpy')
        self.assertEqual(len(by_file['labels']), 2)
        self.assertNotIn('_internal', [x['name'] for x in by_file['labels']])
        self.assertFalse(any('renpy/common' in x['file'] for x in by_file['labels']))

    def test_current_location_excerpt_is_bounded_and_read_only(self):
        result = source_excerpt(self.temp.name, 'chapters/intro.rpy', 12)
        self.assertTrue(result['available'])
        self.assertEqual(result['line'], 12)
        self.assertEqual(len(result['lines']), 21)
        self.assertEqual(result['lines'][10]['line'], 12)
        self.assertIn('intro.rpy line 12', result['lines'][10]['text'])
        self.assertEqual(Path(self.temp.name, 'chapters/intro.rpy').read_text(
            encoding='utf-8').count('line 12'), 1)

    def test_source_read_is_bounded_even_when_file_size_check_is_stale(self):
        # A single oversized line must not be materialised as an unbounded
        # source line, including if an earlier size check became stale.
        target = Path(self.temp.name, 'large.rpy')
        target.write_bytes(b'x' * (1024 * 1024 + 1))
        result = source_excerpt(self.temp.name, 'large.rpy', 1)
        self.assertFalse(result['available'])
        self.assertIn('exceeds read limit', result['reason'])
        self.assertEqual(result['lines'], [])

    def test_compiled_only_games_gracefully_report_missing_source(self):
        Path(self.temp.name, 'chapters/intro.rpy').unlink()
        source = source_excerpt(self.temp.name, 'chapters/intro.rpy', 78)
        self.assertFalse(source['available'])
        self.assertIn('not installed', source['reason'])
        labels = list_labels(self.api, self.temp.name, 'intro')
        self.assertTrue(labels['labels'])

    def test_reject_traversal_invalid_extension_symlink_and_invalid_line(self):
        for value in ('../secret.rpy', '/etc/passwd', 'chapters\\intro.rpy',
                      'script.rpy/../config.rpy', '', 'something.txt', 'a//b.rpy'):
            with self.subTest(filename=value), self.assertRaises(ValueError):
                validate_source_request(value, 1)
        for value in (0, -1, 100001, True, '11'):
            with self.subTest(line=value), self.assertRaises(ValueError):
                validate_source_request('script.rpy', value)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, 'private.rpy').write_text('private\n', encoding='utf-8')
        Path(self.temp.name, 'escape.rpy').symlink_to(Path(outside.name, 'private.rpy'))
        with self.assertRaises(ValueError):
            source_excerpt(self.temp.name, 'escape.rpy', 1)
        for args in (('a\nb', 0, 40), ('', -1, 40), ('a', 0, 41),
                     ('x'*65, 0, 40), ('a', 3961, 40), ('a', 0, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_label_request(*args)

    def test_label_budget_and_offset(self):
        self.api.names = ['chapter_%04d' % n for n in range(4200)]
        self.api.files = {name: ('game/script.rpy', n % 80 + 1)
                          for n, name in enumerate(self.api.names)}
        result = list_labels(self.api, self.temp.name, 'chapter')
        self.assertTrue(result['limited'])
        self.assertLessEqual(result['scanned'], MAX_LABEL_SCAN)
        self.assertEqual(len(result['labels']), LABEL_PAGE_SIZE)


class ScriptHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        Path(self.temp.name, 'index.html').write_text('test', encoding='utf-8')
        self.api = ScriptFixture(self.temp.name)
        inspector = Inspector()
        inspector.bind(lambda: ModuleType('store'), lambda: {})
        self.bridge = InspectorBridge(inspector, self.temp.name)
        self.bridge.configure_script_runtime(self.api, self.temp.name)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.base = 'http://127.0.0.1:%d' % self.bridge.server.server_port
        self.api.calls[:] = []

    def fetch(self, path, params, token=None, origin=None):
        req = Request(self.base + path + '?' + urlencode(params),
                      headers={'X-Inspector-Token':
                               self.bridge.token if token is None else token,
                               **({'Origin': origin} if origin else {})})
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            return error.code, None

    def test_queries_wait_for_game_interaction_thread(self):
        for path, params in [
            ('/api/v1/scripts', {'q': 'intro', 'offset': '0', 'size': '40'}),
            ('/api/v1/source', {'file': 'script.rpy', 'line': '5'}),
        ]:
            result = []
            calls_before = len(self.api.calls)
            worker = threading.Thread(target=lambda: result.append(self.fetch(path, params)))
            worker.start()
            time.sleep(.12)
            self.assertEqual(len(self.api.calls), calls_before)
            self.assertEqual(len(self.bridge.pending_pages), 1)
            self.bridge.tick()
            worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result[0][0], 200)
            if path == '/api/v1/scripts':
                self.assertEqual(len(self.api.calls), calls_before + 1)
                self.assertEqual(self.api.calls[-1], threading.current_thread().name)
            else:
                self.assertEqual(len(self.api.calls), calls_before)
        self.assertEqual(len(self.api.calls), 1)  # source reading doesn't query labels

    def test_endpoint_auth_and_input_rejection(self):
        self.assertEqual(self.fetch('/api/v1/scripts',
            {'q': '', 'offset': '0', 'size': '40'}, token='wrong')[0], 401)
        self.assertEqual(self.fetch('/api/v1/scripts',
            {'q': '', 'offset': '0', 'size': '40'},
            origin='https://evil.example')[0], 403)
        self.assertEqual(self.fetch('/api/v1/scripts',
            {'q': '', 'offset': '-1', 'size': '40'})[0], 400)
        self.assertEqual(self.fetch('/api/v1/source',
            {'file': '../private.rpy', 'line': '1'})[0], 400)


if __name__ == '__main__':
    unittest.main()
