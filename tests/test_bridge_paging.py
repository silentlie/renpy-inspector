"""Read-only paged inspection and HTTP dispatch regression tests."""
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
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.bridge_paging import MAX_BRANCH, PAGE_SIZE, build_tree_page, validate_tree_request
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class PagingTests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType('store')
        self.store.big = list(range(1500))
        self.store.person = {'health': 17, 'attributes': {'name': 'Jane'}}
        self.store.cycle = []
        self.store.cycle.append(self.store.cycle)
        self.providers = {'store': lambda: self.store, 'persistent': lambda: {}}

    def test_list_pagination_and_hard_cap(self):
        parent = (('attribute', 'big'),)
        first = build_tree_page(self.providers, 'store', parent, 0, PAGE_SIZE)
        self.assertEqual(len(first['items']), PAGE_SIZE)
        self.assertTrue(first['more'])
        self.assertEqual(first['next_offset'], PAGE_SIZE)
        middle = build_tree_page(self.providers, 'store', parent, PAGE_SIZE, PAGE_SIZE)
        self.assertEqual(middle['items'][0]['name'], '[80]')
        last = build_tree_page(self.providers, 'store', parent, 960, PAGE_SIZE)
        self.assertEqual(len(last['items']), 40)
        self.assertFalse(last['more'])
        self.assertTrue(last['capped'])

    def test_reads_nested_object_without_properties_or_repr(self):
        class Hostile(object):
            @property
            def danger(self):
                raise AssertionError('property must not run')
            def __repr__(self):
                raise AssertionError('repr must not run')
        self.store.hostile = Hostile()
        result = build_tree_page(self.providers, 'store',
                                 (('attribute', 'hostile'),), 0, PAGE_SIZE)
        self.assertFalse(any(item['name'] == 'danger' for item in result['items']))
        self.assertTrue(all('danger' not in item['preview'] for item in result['items']))

    def test_invalid_paths_scopes_and_pagination(self):
        bad = [
            ('system', [], 0, PAGE_SIZE),
            ('store', [['attribute', '__class__']], 0, PAGE_SIZE),
            ('store', [['index', True]], 0, PAGE_SIZE),
            ('store', [['key', {'evil': 1}]], 0, PAGE_SIZE),
            ('store', [], -1, PAGE_SIZE),
            ('store', [], 0, PAGE_SIZE + 1),
            ('store', [], MAX_BRANCH, PAGE_SIZE),
            ('store', [['key', None]] * 9, 0, 1),
            ('store', ['__import__("os")'], 0, 1),
        ]
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    validate_tree_request(*args)
        for parent in ((('attribute', '_internal'),),
                       (('attribute', 'not_here'),),
                       (('attribute', 'cycle'), ('index', 0)),
                       (('attribute', 'person'), ('key', 'not_here'))):
            with self.subTest(parent=parent):
                with self.assertRaises(ValueError):
                    build_tree_page(self.providers, 'store', parent, 0, 20)

    def test_root_expands_beyond_initial_snapshot(self):
        for i in range(700):
            setattr(self.store, 'field_{:04d}'.format(i), i)
        first = build_tree_page(self.providers, 'store', (), 0, PAGE_SIZE)
        another = build_tree_page(self.providers, 'store', (), 480, PAGE_SIZE)
        self.assertEqual(len(first['items']), PAGE_SIZE)
        self.assertEqual(len(another['items']), PAGE_SIZE)
        self.assertNotEqual(first['items'][0]['key'], another['items'][0]['key'])
        self.assertTrue(another['more'])
        self.assertEqual(another['offset'], 480)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, 'index.html').write_text('<html>local</html>')
        self.store = ModuleType('store')
        self.store.items = list(range(700))
        self.called_on = []
        def store_provider():
            self.called_on.append(threading.current_thread().name)
            return self.store
        self.inspector = Inspector()
        self.inspector.bind(store_provider, lambda: {})
        self.bridge = InspectorBridge(self.inspector, self.tmp.name)
        self.bridge.start()
        self.assertTrue(self.bridge.running, self.bridge.error)
        self.addCleanup(self.bridge.stop)
        self.url = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        self.main_thread = threading.current_thread().name
        self.called_on[:] = []

    def get_children(self, path, token=None, scope='store', offset=0, size=80, method='GET', origin=None):
        params = urlencode({'scope': scope, 'path': json.dumps(path, separators=(',', ':')),
                            'offset': str(offset), 'size': str(size)})
        headers = {'X-Inspector-Token': token or self.bridge.token}
        if origin: headers['Origin'] = origin
        req = Request(self.url + '/api/v1/children?' + params, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as r:
                return (r.status, json.loads(r.read().decode('ascii')))
        except HTTPError as e:
            return (e.code, json.loads(e.read().decode('ascii')) if e.code in (404, 409, 413, 500) else {})

    def test_http_worker_never_reads_game_objects(self):
        results = []
        client = threading.Thread(target=lambda: results.append(
            self.get_children([['attribute', 'items']], size=80)))
        client.start()
        time.sleep(0.1)
        self.assertEqual(self.called_on, [])
        self.assertEqual(len(self.bridge.pending_pages), 1)
        self.bridge.tick()
        client.join(4.0)
        self.assertFalse(client.is_alive())
        self.assertEqual(results[0][0], 200)
        self.assertEqual(len(results[0][1]['items']), 80)
        self.assertEqual(self.called_on, [self.main_thread])

    def test_rejects_unauthorized_and_invalid_paths(self):
        self.assertEqual(self.get_children([], token='wrong')[0], 401)
        self.assertEqual(self.get_children([['attribute', '_private']])[0], 400)
        self.assertEqual(self.get_children([], origin='https://evil.test')[0], 403)

    def test_queued_requests_invalidated_on_game_load(self):
        results = []
        client = threading.Thread(target=lambda: results.append(self.get_children([])))
        client.start()
        time.sleep(0.1)
        self.bridge.invalidate()
        client.join(4.0)
        self.assertFalse(client.is_alive())
        self.assertEqual(results[0][0], 409)
        self.assertEqual(self.bridge.pending_pages, [])

    def test_queue_is_bounded(self):
        jobs = [self.bridge.enqueue_tree_page(('store', (), 0, 1)) for _ in range(8)]
        self.assertTrue(all(jobs))
        self.assertIsNone(self.bridge.enqueue_tree_page(('store', (), 0, 1)))
        self.bridge.cancel_all_tree_pages()


if __name__ == '__main__':
    unittest.main()
