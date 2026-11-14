"""Namedtuple presentation stays index-based and never executes game getters."""
import sys
import unittest
from collections import namedtuple
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.inspection import MISSING, child_descriptors, read_child, snapshot
from renpy_inspector.bridge_paging import build_tree_page, build_tree_value
from renpy_inspector.bridge_search import build_search_results, build_reveal_chain


class NamedtuplePresentationTests(unittest.TestCase):
    def test_namedtuple_fields_use_safe_index_paths_instead_of_getters(self):
        Point = namedtuple('Point', 'latitude longitude')
        class Guarded(Point):
            __slots__ = ()
            def __getattribute__(self, key):
                raise AssertionError('instance getter must not run: ' + key)
            def __getattr__(self, key):
                raise AssertionError('fallback getter must not run')
            def __repr__(self):
                raise AssertionError('custom repr must not run')
            def __iter__(self):
                raise AssertionError('custom iterator must not run')
            @property
            def calculated(self):
                raise AssertionError('property must not run')
        item = Guarded(20, 45)
        state, typename, preview, expandable, token = snapshot(item)
        self.assertEqual((state, typename, preview, expandable),
                         ('value', 'Guarded', '2 named fields', True))
        descriptors, cut = child_descriptors(item, 80)
        self.assertEqual(descriptors, [
            (('index', 0), '[0] latitude'),
            (('index', 1), '[1] longitude'),
        ])
        self.assertFalse(cut)
        self.assertEqual(read_child(item, ('index', 0)), 20)
        self.assertIs(read_child(item, ('attribute', 'latitude')), MISSING)
        self.assertNotIn('calculated', str(descriptors))

    def test_ordinary_tuples_are_unchanged_and_empty_namedtuple_is_identified(self):
        self.assertEqual(snapshot((1, 2))[2], '2 items')
        self.assertEqual(child_descriptors((1, 2), 80)[0], [
            (('index', 0), '[0]'), (('index', 1), '[1]'),
        ])
        Empty = namedtuple('Empty', '')
        self.assertEqual(snapshot(Empty())[2], '0 named fields')
        self.assertEqual(child_descriptors(Empty(), 80), ([], False))

    def test_shadowed_invalid_and_forged_metadata_falls_back_without_iteration(self):
        Base = namedtuple('Base', 'hp mp')
        class Corrupted(Base):
            __slots__ = ()
            _fields = property(lambda self: self.explode())
        invalid = Corrupted(5, 6)
        self.assertEqual(snapshot(invalid)[2], '2 items')
        self.assertEqual(child_descriptors(invalid, 80)[0][0],
                         (('index', 0), '[0]'))

        class Forged(tuple):
            _fields = ('ok', 'duplicate', 'duplicate')
            def __iter__(self):
                raise AssertionError('forged iterator must never run')
        item = Forged((1, 2, 3))
        self.assertEqual(snapshot(item)[2], '3 items')
        self.assertEqual(child_descriptors(item, 80)[0][1][1], '[1]')

        class Invalid(tuple):
            _fields = ('safe', 'bad.<script>')
        self.assertEqual(child_descriptors(Invalid((1, 2)), 80)[0][0][1], '[0]')

        class Overlong(tuple):
            _fields = ('x' * 65,)
        self.assertEqual(snapshot(Overlong((1,)))[2], '1 item')
        class Oversize(tuple):
            _fields = tuple('field{}'.format(i) for i in range(129))
        value = Oversize(range(129))
        self.assertEqual(snapshot(value)[2], '129 items')
        self.assertEqual(child_descriptors(value, 2)[0][0], (('index', 0), '[0]'))

    def test_page_pinning_search_and_reveal_keep_index_identity_and_named_label(self):
        store = ModuleType('store')
        Hero = namedtuple('Hero', 'health mana')
        store.hero = Hero(12, {'potions': 3})
        providers = {'store': lambda: store, 'persistent': lambda: {}}
        root = build_tree_page(providers, 'store', (), 0, 80)
        hero = next(node for node in root['items'] if node['name'] == 'hero')
        self.assertEqual(hero['preview'], '2 named fields')

        path = (('attribute', 'hero'),)
        page = build_tree_page(providers, 'store', path, 0, 80)
        self.assertEqual([x['name'] for x in page['items']],
                         ['[0] health', '[1] mana'])
        self.assertEqual([x['preview'] for x in page['items']], ['12', '1 item'])
        self.assertEqual([x['type'] for x in page['items']], ['int', 'dict'])
        self.assertEqual([x['key'] for x in page['items']],
                         ['["store",[["attribute","hero"],["index",0]]]',
                          '["store",[["attribute","hero"],["index",1]]]'])
        watched = build_tree_value(providers, 'store', path + (('index', 0),))
        self.assertEqual(watched['node']['name'], '[0] health')
        self.assertEqual(watched['node']['preview'], '12')

        chain = build_reveal_chain(providers, 'store', path + (('index', 1),))
        self.assertEqual(chain['chain'][-1]['name'], '[1] mana')
        hits = build_search_results(providers, 'store', 'health')
        self.assertTrue(any(item['name'] == '[0] health' for item in hits['results']))
        nested = build_tree_page(providers, 'store', path +
                                 (('index', 1),), 0, 80)
        self.assertEqual(nested['items'][0]['preview'], '3')
        self.assertEqual(nested['items'][0]['name'], "['potions']")

    def test_bounded_paging_still_uses_offsets_and_caps(self):
        fields = ['f{}'.format(i) for i in range(90)]
        Massive = namedtuple('Massive', fields)
        store = ModuleType('store')
        store.bulk = Massive(*range(90))
        providers = {'store': lambda: store, 'persistent': lambda: {}}
        root = (('attribute', 'bulk'),)
        page = build_tree_page(providers, 'store', root, 80, 80)
        self.assertEqual([item['name'] for item in page['items']],
                         ['[80] f80', '[81] f81', '[82] f82', '[83] f83',
                          '[84] f84', '[85] f85', '[86] f86', '[87] f87',
                          '[88] f88', '[89] f89'])
        self.assertFalse(page['more'])
        self.assertFalse(page['capped'])


if __name__ == '__main__':
    unittest.main()
