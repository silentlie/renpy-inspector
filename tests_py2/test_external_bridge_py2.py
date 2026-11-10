# -*- coding: utf-8 -*-
"""Python 2 smoke coverage for the optional external bridge."""
from __future__ import unicode_literals

import json
import os
import shutil
import sys
import tempfile
import unittest
from types import ModuleType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'game'))

from renpy_inspector.bridge_snapshot import build_snapshot, encode_snapshot
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.bridge_paging import build_tree_page, build_lazy_snapshot, validate_tree_request
from renpy_inspector.controller import Inspector


class BridgePy2Tests(unittest.TestCase):
    def test_ascii_serialization_and_budget(self):
        root = ModuleType(str('store'))
        root.people = {'jane': {'health': 80}}
        data = build_snapshot({'store': lambda: root, 'persistent': lambda: {}},
                              {'game': 'Fixture'})
        blob = encode_snapshot(data)
        self.assertEqual(json.loads(blob)['scopes']['store'][0]['name'], 'people')
        self.assertTrue(len(blob) < 256 * 1024)

    def test_paged_children_compatible_with_python2(self):
        root = ModuleType(str('store'))
        root.large = list(range(240))
        providers = {'store': lambda: root, 'persistent': lambda: {}}
        page = build_tree_page(providers, 'store', (('attribute', 'large'),), 0, 80)
        self.assertEqual(len(page['items']), 80)
        self.assertTrue(page['more'])
        page2 = build_tree_page(providers, 'store', (('attribute', 'large'),), 160, 80)
        self.assertFalse(page2['more'])
        self.assertEqual(page2['items'][0]['name'], '[160]')
        with self.assertRaises(ValueError):
            validate_tree_request('store', [['attribute', '__class__']], 0, 80)
        shallow = build_lazy_snapshot(providers)
        self.assertTrue(shallow['root_pages']['store']['more'])
        self.assertEqual(len(shallow['scopes']['store']), 1)

    def test_service_starts_and_stops_without_game(self):
        folder = tempfile.mkdtemp(prefix='bridge-py2-')
        try:
            with open(os.path.join(folder, 'index.html'), 'wb') as f:
                f.write(b'<html>fixture</html>')
            ins = Inspector()
            ins.bind(lambda: ModuleType(str('store')), lambda: {})
            bridge = InspectorBridge(ins, folder)
            bridge.start()
            self.assertTrue(bridge.running, bridge.error)
            self.assertTrue(bridge.url.startswith('http://127.0.0.1:'))
            called = []
            bridge.open_browser = lambda: called.append(bridge.url) or True
            self.assertTrue(bridge.launch_or_open())
            self.assertTrue(bridge.launch_or_open())
            self.assertEqual(len(called), 2)
            self.assertEqual(called[0], called[1])
            bridge.stop()
            self.assertFalse(bridge.running)
        finally:
            shutil.rmtree(folder)


if __name__ == '__main__':
    unittest.main()
