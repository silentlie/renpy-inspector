# -*- coding: utf-8 -*-
"""Python 2.7 executable regression suite for the *shared* game package.

Run with: python2 -m unittest discover -s tests_py2 -v
The modern build scripts and Python 3 tests are intentionally excluded.
"""
from __future__ import unicode_literals

import json
import os
import shutil
import sys
import tempfile
import unittest
from types import ModuleType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'game'))

from renpy_inspector.compat import iter_keys, iter_items, fold_text, atomic_replace
from renpy_inspector.controller import Inspector
from renpy_inspector.favorites import encode_location, decode_location
from renpy_inspector.inspection import child_descriptors, MISSING, snapshot, read_child
from renpy_inspector.runtime import collect_context
from renpy_inspector.search import search_tree
from renpy_inspector.settings import SettingsStore


class Guarded(object):
    def __init__(self):
        self.health = 8

    @property
    def trap(self):
        raise AssertionError('properties must not run')

    def __repr__(self):
        raise AssertionError('user repr must not run')


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix='inspector-py2-')

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_lazy_dictionary_iteration(self):
        # Exercise a large dictionary without materialising 10000 key previews.
        data = dict((i, i) for i in range(10000))
        self.assertEqual(next(iter_keys(data)), 0)
        self.assertEqual(next(iter_items(data)), (0, 0))
        desc, truncated = child_descriptors(data, 15)
        self.assertEqual(len(desc), 15)
        self.assertTrue(truncated)

    def test_unicode_named_scope_and_serialization(self):
        path = (('attribute', u'health'), ('key', u'café'), ('index', 2))
        location = encode_location('named:characters', path)
        self.assertEqual(decode_location(json.loads(json.dumps(location))),
                         ('named:characters', path))
        self.assertIn(u'café', location['segments'][1]['key']['value'])

    def test_safe_snapshot_does_not_read_properties(self):
        root = Guarded()
        self.assertEqual(read_child(root, ('attribute', 'health')), 8)
        self.assertIs(read_child(root, ('attribute', 'trap')), MISSING)
        self.assertEqual(snapshot(root)[0], 'value')

    def test_search_matches_and_cycles(self):
        root = ModuleType(str('store'))
        item = {'health': 3}
        item['self'] = item
        root.player = item
        result = search_tree(root, 'store', 'health')
        self.assertEqual(len(result.matches), 1)
        self.assertLessEqual(result.visited, 10)
        self.assertEqual(result.matches[0].preview, '3')
        self.assertEqual(fold_text(u'CAFÉ'), u'café')

    def test_settings_roundtrip_atomic_replace(self):
        store = SettingsStore(self.tempdir)
        path = (('attribute', 'player'), ('key', u'café'))
        for i in (1, 2):
            store.save(interval_ms=250, drawer_width=460,
                       favorites=[('store', path)], scope='store')
        data = store.load()
        self.assertEqual(data['favorites'], [('store', path)])
        self.assertEqual(data['interval_ms'], 250)
        self.assertTrue(os.path.isfile(store.path))

    def test_inspector_polled_favourite_after_object_replacement(self):
        store = ModuleType(str('store'))
        store.player = {'health': 3}
        ins = Inspector()
        ins.bind(lambda: store, lambda: {}, SettingsStore(self.tempdir))
        ins.open()
        ins.toggle_favorite('store', (('attribute', 'player'), ('key', 'health')))
        store.player = {'health': 6}
        ins.refresh()
        self.assertEqual(ins.favorite_rows[0].preview, '6')
        ins.close()
        self.assertEqual(ins.rows, ())

    def test_runtime_context(self):
        class Engine(object):
            version_string = u'7.8.7'
            def get_filename_line(self):
                return (u'script.rpy', 22)
            def get_return_stack(self):
                return ['start']
        class Config(object):
            name = u'Fixture'
        self.assertEqual(collect_context(Engine(), Config())['line'], 22)

    def test_atomic_settings_failure_preserves_old_file(self):
        store = SettingsStore(self.tempdir)
        store.save(interval_ms=250, drawer_width=460, favorites=[])
        try:
            store.save(interval_ms=-1, drawer_width=460, favorites=[])
            self.fail('invalid value accepted')
        except ValueError:
            pass
        self.assertEqual(store.load()['interval_ms'], 250)


if __name__ == '__main__':
    unittest.main()
