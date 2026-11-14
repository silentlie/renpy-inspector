"""Python 2 and Python 3 namedtuple labels stay read-only and indexed."""
from __future__ import unicode_literals

import os
import sys
import unittest
from collections import namedtuple
from types import ModuleType

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))

from renpy_inspector.inspection import MISSING, child_descriptors, read_child, snapshot
from renpy_inspector.bridge_paging import build_tree_page, build_tree_value


class NamedtuplePython2Tests(unittest.TestCase):
    def test_fields_are_static_and_index_based_without_custom_methods(self):
        Point = namedtuple('Point', 'score lives')
        class Hostile(Point):
            __slots__ = ()
            def __getattribute__(self, name):
                raise AssertionError('custom getter executed')
            def __repr__(self):
                raise AssertionError('custom repr executed')
            def __iter__(self):
                raise AssertionError('custom iterator executed')
        value = Hostile(8, 3)
        self.assertEqual(snapshot(value)[2], '2 named fields')
        self.assertEqual(child_descriptors(value, 80),
                         ([(('index', 0), '[0] score'),
                           (('index', 1), '[1] lives')], False))
        self.assertEqual(read_child(value, ('index', 1)), 3)
        self.assertIs(read_child(value, ('attribute', 'score')), MISSING)

    def test_invalid_static_field_metadata_falls_back(self):
        class Bogus(tuple):
            _fields = ('name', 'name')
        value = Bogus((1, 2))
        self.assertEqual(snapshot(value)[2], '2 items')
        self.assertEqual(child_descriptors(value, 80)[0][0],
                         (('index', 0), '[0]'))
        class Broken(tuple):
            _fields = ('h<unsafe>',)
        self.assertEqual(child_descriptors(Broken((3,)), 80)[0][0][1], '[0]')

    def test_paging_and_pinning_preserve_field_label_and_index_path(self):
        Hero = namedtuple('Hero', 'hp mp')
        store = ModuleType(str('store'))
        store.hero = Hero(42, 4)
        providers = {'store': lambda: store, 'persistent': lambda: {}}
        parent = (('attribute', 'hero'),)
        page = build_tree_page(providers, 'store', parent, 0, 80)
        self.assertEqual([v['name'] for v in page['items']],
                         ['[0] hp', '[1] mp'])
        self.assertEqual(page['items'][0]['key'],
                         '["store",[["attribute","hero"],["index",0]]]')
        watch = build_tree_value(providers, 'store', parent + (('index', 0),))
        self.assertEqual(watch['node']['name'], '[0] hp')
        self.assertEqual(watch['node']['preview'], '42')


if __name__ == '__main__':
    unittest.main()
