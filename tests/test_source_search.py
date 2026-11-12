"""Bounded literal source search and authenticated game-thread HTTP checks."""
import json
import os
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
from renpy_inspector.bridge_scripts import (
    search_source_text, validate_source_search_request,
    SOURCE_SEARCH_MAX_FILE_BYTES, SOURCE_SEARCH_PAGE_FILES,
    SOURCE_SEARCH_PAGE_SIZE,
)
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class SourceSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'script.rpy').write_text(
            'label start:\n    "Sword and shield"\n    $ score = 3\n'
            '    "Sword returned"\n', encoding='utf-8')
        (root / 'chapters').mkdir()
        (root / 'chapters' / 'story.rpy').write_text(
            'label second:\n    "SWORD at this scene"\n'
            '    # score is mentioned in a comment\n', encoding='utf-8')
        (root / 'renpy_inspector_screens.rpy').write_text(
            '"Sword secret inspector code"\n', encoding='utf-8')
        self.root = root

    def test_literal_multifile_search_case_insensitive_and_source_excerpt(self):
        result = search_source_text(str(self.root), 'sword')
        self.assertTrue(result['available'])
        self.assertFalse(result['more'])
        self.assertFalse(result['limited'])
        self.assertEqual(len(result['matches']), 3)
        self.assertEqual({row['file'] for row in result['matches']},
                         {'script.rpy', 'chapters/story.rpy'})
        # os.walk enumerates top-level files before nested directories.
        self.assertEqual(result['matches'][0]['file'], 'script.rpy')
        self.assertTrue(all('sword' in row['text'].lower()
                            for row in result['matches']))
        self.assertLessEqual(result['scanned_bytes'], 256 * 1024)

    def test_cursor_pages_with_many_hits_in_one_file(self):
        (self.root / 'script.rpy').write_text(
            ''.join('    "sword %d"\n' % i for i in range(59)), encoding='utf-8')
        first = search_source_text(str(self.root), 'sword', '0:0', 10)
        self.assertEqual(len(first['matches']), 10)
        self.assertTrue(first['more'])
        self.assertRegex(first['cursor'], r'^\d+:\d+$')
        all_matches = list(first['matches'])
        cursor = first['cursor']
        for _ in range(10):
            part = search_source_text(str(self.root), 'sword', cursor, 10)
            all_matches.extend(part['matches'])
            if not part['more']:
                break
            self.assertNotEqual(part['cursor'], cursor)
            cursor = part['cursor']
        self.assertEqual(len(all_matches), 60)  # 59 script + 1 chapter
        self.assertEqual(len({(x['file'], x['line']) for x in all_matches}), 60)

    def test_search_skips_symlinks_oversized_and_inspector_files(self):
        (self.root / 'huge.rpy').write_bytes(b'sword' * (
            SOURCE_SEARCH_MAX_FILE_BYTES // 5 + 20))
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, 'private.rpy').write_text(
            'sword confidential\n', encoding='utf-8')
        (self.root / 'escape.rpy').symlink_to(Path(outside.name, 'private.rpy'))
        result = search_source_text(str(self.root), 'sword')
        self.assertTrue(result['limited'])
        self.assertFalse(any(x['file'] in ('escape.rpy', 'huge.rpy',
                                         'renpy_inspector_screens.rpy')
                             for x in result['matches']))

    def test_partial_scan_and_continue_even_without_early_matches(self):
        for i in range(SOURCE_SEARCH_PAGE_FILES + 5):
            (self.root / ('file_%03d.rpy' % i)).write_text(
                'label test_%d:\n    "absent"\n' % i, encoding='utf-8')
        first = search_source_text(str(self.root), 'needle')
        self.assertTrue(first['more'])
        self.assertEqual(first['matches'], [])
        self.assertLessEqual(first['scanned_files'], SOURCE_SEARCH_PAGE_FILES)
        second = search_source_text(str(self.root), 'needle', first['cursor'])
        self.assertNotEqual(first['cursor'], second['cursor'])
        self.assertFalse(second['more'])

    def test_rejects_query_injection_and_cursor_or_size_abuse(self):
        for args in (('a', '0:0', 20), ('x' * 65, '0:0', 20),
                     ('abc\nx', '0:0', 20), ('abc', '../secret.rpy', 20),
                     ('abc', '-1:0', 20), ('abc', '99999:0', 20),
                     ('abc', '0:999999999', 20), ('abc', '0:0', 21),
                     ('abc', '0:0', True), ('abc', '1:2:3', 20)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_source_search_request(*args)


class SourceSearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'index.html').write_text('<html>ok</html>')
        (root / 'script.rpy').write_text('label start:\n    $ score = 12\n')
        self.inspector = Inspector()
        self.inspector.bind(lambda: ModuleType('store'), lambda: {})
        self.bridge = InspectorBridge(self.inspector, self.temp.name)
        self.bridge.configure_script_runtime(None, self.temp.name)
        self.bridge.start()
        self.assertTrue(self.bridge.running, self.bridge.error)
        self.addCleanup(self.bridge.stop)
        self.base = 'http://127.0.0.1:%d' % self.bridge.server.server_port

    def fetch(self, token=None, origin=None, q='score', cursor='0:0', size=20,
              method='GET'):
        url = self.base + '/api/v1/source-search?' + urlencode(
            {'q': q, 'cursor': cursor, 'size': str(size)})
        headers = {'X-Inspector-Token':
                   self.bridge.token if token is None else token}
        if origin:
            headers['Origin'] = origin
        request = Request(url, headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, {}

    def test_auth_rejection_and_read_only_method(self):
        self.assertEqual(self.fetch(token='bad')[0], 401)
        self.assertEqual(self.fetch(origin='https://evil.example')[0], 403)
        self.assertEqual(self.fetch(method='POST')[0], 405)
        self.assertEqual(self.fetch(q='x')[0], 400)
        self.assertEqual(self.fetch(cursor='../../../secret')[0], 400)

    def test_search_queue_runs_only_on_tick_and_invalidates_on_game_load(self):
        result = []
        worker = threading.Thread(target=lambda: result.append(self.fetch()))
        worker.start()
        time.sleep(.12)
        self.assertEqual(result, [])
        self.assertEqual(len(self.bridge.pending_pages), 1)
        self.bridge.tick()
        worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0][0], 200)
        self.assertEqual(result[0][1]['matches'][0]['line'], 2)
        self.assertEqual(result[0][1]['generation'], self.bridge.generation)

        pending = []
        thread = threading.Thread(target=lambda: pending.append(self.fetch()))
        thread.start()
        time.sleep(.12)
        self.bridge.invalidate()
        thread.join(4)
        self.assertEqual(pending[0][0], 409)


if __name__ == '__main__':
    unittest.main()
