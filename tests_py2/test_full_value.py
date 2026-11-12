"""Python 2.7-compatible full-value primitive and size regressions."""
from __future__ import unicode_literals

import os
import sys
import unittest
from types import ModuleType

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.bridge_paging import MAX_FULL_VALUE_CHARS, build_full_value


class FullValueCompatTests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType(str('store'))
        self.store.text = u'First line\nSecond: \u2603'
        self.store.large = u'x' * (MAX_FULL_VALUE_CHARS + 1)
        self.store.bytes_text = 'ascii\nsecond'
        self.store.value = 15
        self.store.player = {'score': 4}
        self.store.huge = 1 << 4097
        self.providers = {'store': lambda: self.store, 'persistent': lambda: {}}

    def get_value(self, *path):
        return build_full_value(self.providers, 'store', tuple(path))

    def test_unicode_bytes_and_nested_paths(self):
        self.assertEqual(self.get_value(('attribute', 'text'))['text'], self.store.text)
        self.assertEqual(self.get_value(('attribute', 'bytes_text'))['text'], u'ascii\nsecond')
        self.assertEqual(self.get_value(('attribute', 'player'), ('key', 'score'))['text'], '4')
        self.assertEqual(self.get_value(('attribute', 'value'))['kind'], 'number')

    def test_truncation_missing_and_unsafe_objects(self):
        result = self.get_value(('attribute', 'large'))
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['text']), MAX_FULL_VALUE_CHARS)
        self.assertEqual(self.get_value(('attribute', 'huge'))['kind'], 'unsupported')
        self.assertEqual(self.get_value(('attribute', 'player'), ('key', 'unknown'))['kind'], 'missing')
        class Hostile(object):
            def __repr__(self):
                raise AssertionError('must not call custom repr')
        self.store.hostile = Hostile()
        self.assertEqual(self.get_value(('attribute', 'hostile'))['kind'], 'unsupported')
        with self.assertRaises(ValueError):
            self.get_value(('attribute', '__class__'))


if __name__ == '__main__':
    unittest.main()
