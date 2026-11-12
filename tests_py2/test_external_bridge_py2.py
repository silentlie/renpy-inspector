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
from renpy_inspector.bridge_paging import build_tree_value
from renpy_inspector.browser_favourites import BrowserFavouritesStore
from renpy_inspector.bridge_search import build_search_results, build_reveal_chain, validate_search_request
from renpy_inspector.bridge_scripts import list_labels, source_excerpt


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
        self.assertFalse(shallow['root_pages']['store']['more'])
        self.assertEqual(len(shallow['scopes']['store']), 1)
        for i in range(100):
            setattr(root, 'field{:03d}'.format(i), i)
        shallow = build_lazy_snapshot(providers)
        self.assertTrue(shallow['root_pages']['store']['more'])
        self.assertEqual(len(shallow['scopes']['store']), 80)

    def test_direct_watch_and_persistent_browser_favourites_py2(self):
        root = ModuleType(str('store'))
        root.profile = {'score': 10}
        providers = {'store': lambda: root, 'persistent': lambda: {}}
        location = (('attribute', 'profile'), ('key', 'score'))
        self.assertEqual(build_tree_value(providers, 'store', location)['node']['preview'], '10')
        root.profile = {'score': 25}
        self.assertEqual(build_tree_value(providers, 'store', location)['node']['preview'], '25')
        folder = tempfile.mkdtemp(prefix='inspector-favourites-py2-')
        try:
            store = BrowserFavouritesStore(folder)
            key = json.dumps(['store', location], separators=(',', ':'))
            store.save([{'scope': 'store', 'key': key}])
            self.assertEqual(len(BrowserFavouritesStore(folder).load()['favourites']), 1)
        finally:
            shutil.rmtree(folder)

    def test_search_and_reveal_work_on_python_2(self):
        root = ModuleType(str('store'))
        root.player = {'stats': {'hp': 42}}
        for index in range(105):
            setattr(root, 'field_{:03d}'.format(index), index)
        providers = {'store': lambda: root, 'persistent': lambda: {}}
        results = build_search_results(providers, 'store', 'field_100')
        self.assertTrue(results['results'])
        chain = build_reveal_chain(providers, 'store',
            (('attribute', 'player'), ('key', 'stats'), ('key', 'hp')))
        self.assertEqual(chain['chain'][-1]['preview'], '42')
        with self.assertRaises(ValueError):
            validate_search_request('store', '__\nimport__')

    def test_readonly_script_navigation_py2(self):
        game_dir = tempfile.mkdtemp(prefix='inspector-scripts-py2-')
        try:
            with open(os.path.join(game_dir, 'script.rpy'), 'wb') as stream:
                stream.write(b'label start:\n    "Hello."\n')
            class Node(object):
                filename = 'game/script.rpy'
                linenumber = 1
            class Script(object):
                def lookup(self, name):
                    return Node()
            class Engine(object):
                game = type(str('Game'), (), {'script': Script()})()
                def get_all_labels(self):
                    return set(['start', '_internal'])
            result = list_labels(Engine(), game_dir, 'start')
            self.assertEqual(len(result['labels']), 1)
            self.assertEqual(result['labels'][0]['file'], 'script.rpy')
            source = source_excerpt(game_dir, 'script.rpy', 1)
            self.assertTrue(source['available'])
        finally:
            shutil.rmtree(game_dir)

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
