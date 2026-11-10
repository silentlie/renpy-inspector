"""Read-only bridge protocol, threading and bounded snapshot unit tests."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.bridge_snapshot import build_snapshot, encode_snapshot, MAX_NODES
from renpy_inspector.controller import Inspector


class Guarded:
    def __init__(self):
        self.health = 10

    @property
    def dangerous(self):
        raise AssertionError('must never invoke property')

    def __repr__(self):
        raise AssertionError('must never invoke game repr')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType('store')
        self.store.player = Guarded()
        self.store.big = list(range(1000))
        self.store.cycle = []
        self.store.cycle.append(self.store.cycle)

    def test_safe_and_bounded_snapshot(self):
        data = build_snapshot({'store': lambda: self.store, 'persistent': lambda: {}},
                              game_info={'game': 'Fixture', 'version': '7.8.7'})
        serialized = encode_snapshot(data)
        self.assertLess(len(serialized), 256 * 1024)
        self.assertLessEqual(sum(data['counts'].values()), MAX_NODES)
        self.assertTrue(data['truncated']['store'])
        self.assertEqual(data['game']['game'], 'Fixture')
        player = next(n for n in data['scopes']['store'] if n['name'] == 'player')
        self.assertEqual(player['children'][0]['name'], 'health')
        self.assertNotIn('dangerous', serialized.decode('ascii'))
        self.assertEqual(data['protocol'], 1)

    def test_snapshot_rejects_budget_overflow(self):
        with self.assertRaises(ValueError):
            build_snapshot({'store': lambda: {}, 'persistent': lambda: {}}, max_nodes=MAX_NODES + 1)

    def test_root_updates_are_fresh(self):
        providers = {'store': lambda: self.store, 'persistent': lambda: {}}
        before = build_snapshot(providers)
        self.store.player.health = 55
        after = build_snapshot(providers)
        self.assertNotEqual(before['scopes']['store'], after['scopes']['store'])


class BridgeAssetDiscoveryTests(unittest.TestCase):
    def test_explicit_game_folder_overrides_import_path(self):
        with tempfile.TemporaryDirectory() as root:
            ui = Path(root, 'game', 'renpy_inspector_web')
            ui.mkdir(parents=True)
            (ui / 'index.html').write_text('<html>working</html>', encoding='utf-8')
            ins = Inspector()
            ins.bind(lambda: {}, lambda: {})
            bridge = InspectorBridge(ins, ui_dir=str(Path(root, 'wrong')))
            bridge.configure_game_directory(str(Path(root, 'game')))
            self.assertEqual(Path(bridge.ui_dir), ui)
            bridge.start()
            try:
                self.assertTrue(bridge.running, bridge.error)
            finally:
                bridge.stop()

    def test_missing_ui_explains_correct_nested_zip_installation(self):
        with tempfile.TemporaryDirectory() as root:
            ins = Inspector()
            ins.bind(lambda: {}, lambda: {})
            bridge = InspectorBridge(ins, ui_dir=str(Path(root, 'missing')))
            bridge.start()
            self.assertFalse(bridge.running)
            self.assertIn('game/renpy_inspector_web/index.html', bridge.error)
            self.assertIn('inner', bridge.error)
            self.assertIn('installation root', bridge.error)


class HttpBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ui_dir = self.tmp.name
        Path(self.ui_dir, 'index.html').write_text('<html>local</html>', encoding='utf-8')
        assets = Path(self.ui_dir, 'assets')
        assets.mkdir()
        (assets / 'index.js').write_text('console.log(1)', encoding='ascii')
        self.store = ModuleType('store')
        self.store.answer = 42
        self.inspector = Inspector()
        self.inspector.bind(lambda: self.store, lambda: {})
        self.bridge = InspectorBridge(self.inspector, self.ui_dir)
        self.bridge.start()
        self.assertTrue(self.bridge.running, self.bridge.error)
        self.addCleanup(self.bridge.stop)
        self.base = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)

    def req(self, path, token=None, origin=None, method='GET', host=None):
        headers = {}
        if token:
            headers['X-Inspector-Token'] = token
        if origin:
            headers['Origin'] = origin
        if host:
            headers['Host'] = host
        return urlopen(Request(self.base + path, headers=headers, method=method), timeout=5)

    def test_cached_json_authenticated_and_readonly(self):
        with self.assertRaises(HTTPError) as error:
            self.req('/api/v1/snapshot')
        self.assertEqual(error.exception.code, 401)
        with self.req('/api/v1/snapshot', self.bridge.token) as response:
            data = json.load(response)
            self.assertEqual(data['scopes']['store'][0]['name'], 'answer')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        with self.assertRaises(HTTPError) as error:
            self.req('/api/v1/snapshot', self.bridge.token, method='POST')
        self.assertEqual(error.exception.code, 405)

    def test_cross_origin_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.req('/api/v1/snapshot', self.bridge.token, origin='https://evil.example')
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.req('/api/v1/snapshot', self.bridge.token, host='evil.example')
        self.assertEqual(error.exception.code, 403)

    def test_local_ui_files_are_static_without_token(self):
        with self.req('/') as response:
            self.assertIn(b'<html>local</html>', response.read())
        with self.req('/assets/index.js') as response:
            self.assertIn(b'console.log', response.read())
        with self.assertRaises(HTTPError) as error:
            self.req('/etc/passwd')
        self.assertEqual(error.exception.code, 404)

    def test_updates_only_on_explicit_publish(self):
        self.store.answer = 76
        with self.req('/api/v1/snapshot', self.bridge.token) as response:
            data = json.load(response)
        self.assertEqual(data['scopes']['store'][0]['preview'], '42')
        self.bridge.publish()
        with self.req('/api/v1/snapshot', self.bridge.token) as response:
            data = json.load(response)
        self.assertEqual(data['scopes']['store'][0]['preview'], '76')

    def test_stopping_revokes_session_token_and_restart_rotates_it(self):
        previous = self.bridge.token
        self.bridge.stop()
        self.assertIsNone(self.bridge.token)
        self.bridge.start()
        self.assertNotEqual(previous, self.bridge.token)
        self.base = 'http://127.0.0.1:{}'.format(self.bridge.server.server_port)
        with self.assertRaises(HTTPError) as error:
            self.req('/api/v1/snapshot', previous)
        self.assertEqual(error.exception.code, 401)

    def test_f8_launch_start_once_then_open_same_local_server(self):
        with patch('webbrowser.open', return_value=True) as opened:
            self.assertTrue(self.bridge.launch_or_open())
            first = self.bridge.url
            token = self.bridge.token
            self.assertTrue(self.bridge.launch_or_open())
            self.assertEqual(self.bridge.url, first)
            self.assertEqual(self.bridge.token, token)
            self.assertEqual(opened.call_count, 2)
            opened.assert_called_with(first, new=1)

    def test_f8_launch_reports_missing_assets_without_opening_browser(self):
        self.bridge.stop()
        os.remove(os.path.join(self.ui_dir, 'index.html'))
        with patch('webbrowser.open') as opened:
            self.assertFalse(self.bridge.launch_or_open())
            opened.assert_not_called()
        self.assertIn('index.html', self.bridge.error)

    def test_f8_launch_reports_browser_failures(self):
        with patch('webbrowser.open', return_value=False):
            self.assertFalse(self.bridge.launch_or_open())
        self.assertTrue(self.bridge.running)
        self.assertIn('Could not open browser', self.bridge.error)

    def test_snapshot_failure_invalidates_stale_values(self):
        self.inspector._providers['store'] = lambda: self.store
        self.bridge.publish()
        with self.req('/api/v1/snapshot', self.bridge.token) as response:
            self.assertIsNotNone(json.load(response)['captured_at'])
        # Invalid providers make an empty partial snapshot; even then HTTP only
        # receives serializable data and never touches game objects.
        def bad_capture():
            raise RuntimeError('game unavailable')
        self.inspector._providers['store'] = bad_capture
        self.bridge.publish()
        with self.req('/api/v1/snapshot', self.bridge.token) as response:
            data = json.load(response)
        self.assertEqual(data['scopes']['store'], [])

    def test_invalidate_and_disconnect(self):
        self.bridge.invalidate()
        with self.req('/api/v1/snapshot', self.bridge.token) as response:
            self.assertIsNone(json.load(response)['captured_at'])
        self.bridge.stop()
        self.assertFalse(self.bridge.running)
        self.bridge.publish()


if __name__ == '__main__':
    unittest.main()
