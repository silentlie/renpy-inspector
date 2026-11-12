"""Precise, bounded primitive baselines on the Ren'Py interaction thread."""
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.bridge_paging import (
    MAX_COMPARE_SAMPLE_CHARS, MAX_COMPARE_INTEGER_BITS, MAX_COMPARE_PAGE_BYTES,
    build_lazy_snapshot, build_tree_page, build_tree_value, comparison_sample,
)


class PrimitiveCompareCaptureTests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType('store')
        self.store.memo = 'A' * 110 + 'one'
        self.store.other = 'A' * 110 + 'two'
        self.store.large = 'B' * (MAX_COMPARE_SAMPLE_CHARS + 1)
        self.store.score = 123456789
        self.store.huge = 1 << (MAX_COMPARE_INTEGER_BITS + 10)
        self.store.empty = None
        self.store.active = True
        self.store.decimal = 2.5
        self.store.player = {'hp': 10, 'bio': 'first\nsecond'}
        self.providers = {'store': lambda: self.store, 'persistent': lambda: {}}

    def test_small_primitive_text_exact_even_if_preview_is_truncated(self):
        root = build_lazy_snapshot(self.providers)
        captured = {node['name']: node for node in root['scopes']['store']}
        self.assertEqual(captured['memo']['compare_sample']['text'], self.store.memo)
        self.assertEqual(captured['other']['compare_sample']['text'], self.store.other)
        self.assertNotEqual(captured['memo']['compare_sample'],
                            captured['other']['compare_sample'])
        self.assertEqual(captured['score']['compare_sample']['text'], '123456789')
        self.assertEqual(captured['active']['compare_sample']['text'], 'True')
        self.assertEqual(captured['empty']['compare_sample']['text'], 'None')
        self.assertEqual(captured['decimal']['compare_sample']['text'], '2.5')
        self.assertNotIn('compare_sample', captured['large'])
        self.assertNotIn('compare_sample', captured['huge'])
        self.assertNotIn('compare_sample', captured['player'])
        self.assertLess(len(json.dumps(root).encode('utf-8')), 256 * 1024)

    def test_child_and_direct_favourite_reads_share_exact_samples(self):
        page = build_tree_page(self.providers, 'store', (('attribute', 'player'),), 0, 80)
        bio = next(n for n in page['items'] if n['name'] == "['bio']")
        self.assertEqual(bio['compare_sample']['text'], 'first\nsecond')
        value = build_tree_value(self.providers, 'store',
                                 (('attribute', 'player'), ('key', 'bio')))
        self.assertEqual(value['node']['compare_sample']['text'], 'first\nsecond')
        self.assertNotIn('compare_sample', build_tree_value(self.providers, 'store',
            (('attribute', 'player'), ('key', 'nonexistent')))['node'])

    def test_exact_scalar_metadata_has_per_page_byte_budget(self):
        store = ModuleType('large_store')
        for index in range(80):
            setattr(store, 'field_%03d' % index, 'A' * MAX_COMPARE_SAMPLE_CHARS)
        page = build_tree_page(
            {'store': lambda: store, 'persistent': lambda: {}},
            'store', (), 0, 80)
        samples = [n['compare_sample'] for n in page['items']
                   if 'compare_sample' in n]
        self.assertTrue(samples)
        self.assertLess(len(samples), 80)
        self.assertLessEqual(sum(len(json.dumps(item, ensure_ascii=True))
                                 for item in samples), MAX_COMPARE_PAGE_BYTES)

    def test_never_runs_arbitrary_repr_or_property_for_compare_sample(self):
        class Hostile:
            @property
            def attribute(self):
                raise AssertionError('hostile property evaluated')
            def __repr__(self):
                raise AssertionError('hostile repr evaluated')
            def __str__(self):
                raise AssertionError('hostile str evaluated')
        self.store.hostile = Hostile()
        self.assertIsNone(comparison_sample(self.store.hostile))
        root = build_lazy_snapshot(self.providers)
        hostile = next(n for n in root['scopes']['store'] if n['name'] == 'hostile')
        self.assertNotIn('compare_sample', hostile)

    def test_cap_applies_before_converting_large_strings_and_integers(self):
        self.assertIsNone(comparison_sample('x' * (MAX_COMPARE_SAMPLE_CHARS + 1)))
        self.assertEqual(len(comparison_sample('x' * MAX_COMPARE_SAMPLE_CHARS)['text']),
                         MAX_COMPARE_SAMPLE_CHARS)
        self.assertIsNone(comparison_sample(1 << (MAX_COMPARE_INTEGER_BITS + 1)))


if __name__ == '__main__':
    unittest.main()
