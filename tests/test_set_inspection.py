"""Read-only set/frozenset membership paths, safe bounds and engine paging."""
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.bridge_paging import (
    MAX_BRANCH, PAGE_SIZE, build_tree_page, build_tree_value,
    build_full_value, validate_tree_request,
)
from renpy_inspector.bridge_search import build_reveal_chain, build_search_results
from renpy_inspector.browser_favourites import validate_favourites
from renpy_inspector.favorites import encode_location, decode_location, format_location
from renpy_inspector.inspection import child_descriptors


class SetInspectionTests(unittest.TestCase):
    def setUp(self):
        store = ModuleType('store')
        store.flags = {'open', 'locked', 42, -9, True, None, 'unicode ☃'}
        store.immutable = frozenset(['blue', 'red'])
        store.empty = set()
        store.nested = {'members': frozenset([3, 4])}
        store.mixed = {'ok', object(), (1, 2)}
        store.large = set(range(1200))
        self.store = store
        self.providers = {'store': lambda: store, 'persistent': lambda: {}}

    def test_set_and_frozenset_pages_have_stable_value_member_keys(self):
        snapshot = build_tree_page(self.providers, 'store', (), 0, PAGE_SIZE)
        by_name = {entry['name']: entry for entry in snapshot['items']}
        self.assertTrue(by_name['flags']['expandable'])
        self.assertTrue(by_name['immutable']['expandable'])
        self.assertEqual(by_name['empty']['expandable'], False)
        flags = build_tree_page(self.providers, 'store', (('attribute', 'flags'),), 0, PAGE_SIZE)
        self.assertEqual(len(flags['items']), len(self.store.flags))
        self.assertFalse(flags['more'])
        self.assertTrue(all(json.loads(row['key'])[1][-1][0] == 'member'
                            for row in flags['items']))
        self.assertIn('{' + repr('open') + '}', [x['name'] for x in flags['items']])
        frozen = build_tree_page(self.providers, 'store', (('attribute', 'immutable'),), 0, PAGE_SIZE)
        self.assertEqual(len(frozen['items']), 2)
        self.assertIn('member', frozen['items'][0]['key'])
        before = {x['key'] for x in flags['items']}
        self.store.flags.add('new')
        after = {x['key'] for x in build_tree_page(self.providers, 'store',
                     (('attribute', 'flags'),), 0, PAGE_SIZE)['items']}
        self.assertEqual(before & after, before)
        self.assertEqual(len(after - before), 1)

    def test_value_reveal_full_value_and_favourite_membership_path(self):
        path = (('attribute', 'flags'), ('member', 'open'))
        key = json.dumps(['store', path])
        scope, encoded = decode_location(encode_location('store', path))
        self.assertEqual((scope, encoded), ('store', path))
        self.assertIn("{'open'}", format_location('store', path))
        reveal = build_reveal_chain(self.providers, 'store', path)
        self.assertEqual(len(reveal['chain']), 2)
        self.assertEqual(reveal['chain'][-1]['key'], json.dumps(['store', path],
                         ensure_ascii=True, separators=(',', ':')))
        result = build_tree_value(self.providers, 'store', path)['node']
        self.assertEqual(result['state'], 'value')
        self.assertEqual(result['type'], 'str')
        self.assertEqual(result['compare_sample']['text'], 'open')
        full = build_full_value(self.providers, 'store', path)
        self.assertEqual(full['kind'], 'string')
        self.assertEqual(full['text'], 'open')
        favourite = validate_favourites([{'scope': 'store', 'key': key}])
        self.assertEqual(len(favourite), 1)
        self.store.flags.remove('open')
        self.assertEqual(build_tree_value(self.providers, 'store', path)['node']['state'], 'missing')
        self.assertEqual(build_full_value(self.providers, 'store', path)['kind'], 'missing')
        with self.assertRaises(ValueError):
            build_reveal_chain(self.providers, 'store', path)
        self.store.flags.add('open')
        self.assertEqual(build_tree_value(self.providers, 'store', path)['node']['state'], 'value')

    def test_nested_frozen_scalar_keys_and_pagination(self):
        path = (('attribute', 'nested'), ('key', 'members'), ('member', 4))
        self.assertEqual(build_tree_value(self.providers, 'store', path)['node']['preview'], '4')
        page = build_tree_page(self.providers, 'store', (('attribute', 'large'),), 0, PAGE_SIZE)
        self.assertEqual(len(page['items']), PAGE_SIZE)
        self.assertTrue(page['more'])
        page2 = build_tree_page(self.providers, 'store', (('attribute', 'large'),),
                                PAGE_SIZE, PAGE_SIZE)
        self.assertEqual(len(page2['items']), PAGE_SIZE)
        self.assertEqual(len({x['key'] for x in page['items'] + page2['items']}), 2 * PAGE_SIZE)
        final = build_tree_page(self.providers, 'store', (('attribute', 'large'),),
                                960, PAGE_SIZE)
        self.assertTrue(final['capped'])
        self.assertFalse(final['more'])

    def test_unsupported_objects_do_not_invoke_user_code_or_create_endless_pages(self):
        class Hostile:
            def __repr__(self):
                raise AssertionError('repr must not run')
            def __hash__(self):
                return 1234
        self.store.hostile = {Hostile(), 'ok'}
        page = build_tree_page(self.providers, 'store', (('attribute', 'hostile'),), 0, PAGE_SIZE)
        self.assertEqual(len(page['items']), 1)
        self.assertTrue(page['capped'])
        self.assertFalse(page['more'])
        self.assertEqual(page['items'][0]['preview'], "'ok'")
        none_visible = build_tree_page(self.providers, 'store',
            (('attribute', 'mixed'),), 0, PAGE_SIZE)
        self.assertEqual(len(none_visible['items']), 1)
        self.assertFalse(none_visible['more'])
        self.assertTrue(none_visible['capped'])

    def test_rejects_injected_invalid_member_paths(self):
        bad_values = [[], {}, 1.25, -9007199254740992, 'x' * 257, True]
        for value in bad_values[:-1]:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                validate_tree_request('store', [['attribute', 'flags'], ['member', value]], 0, 1)
        with self.assertRaises(ValueError):
            validate_tree_request('store', [['member', {'__class__': 'payload'}]], 0, 1)
        # A forged, but syntactically well-formed member must still be visible
        # in the game's bounded descriptor list to be readable.
        with self.assertRaises(ValueError):
            build_tree_page(self.providers, 'store',
                            (('attribute', 'flags'), ('member', 'not-present')), 0, 1)
        for key in (['attribute', '__class__'], ['member', {'bad': 1}]):
            with self.assertRaises(ValueError):
                validate_tree_request('store', [key], 0, 1)

    def test_bounded_search_discovers_set_members_without_game_object_iteration(self):
        result = build_search_results(self.providers, 'all', 'open')
        self.assertTrue(any('member' in x['key'] for x in result['results']))
        self.assertTrue(all(item['scope'] == 'store' for item in result['results']))


if __name__ == '__main__':
    unittest.main()
