# -*- coding: utf-8 -*-
"""Python 2.7 safe set and frozenset typed member inspection."""
from __future__ import unicode_literals

import json
import os
import sys
import unittest
from types import ModuleType

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.bridge_paging import (
    build_tree_page, build_tree_value, build_full_value, validate_tree_request,
)
from renpy_inspector.favorites import format_location, encode_location, decode_location


class SetInspectionPy2Tests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType(str('store'))
        self.store.flags = set((u'snow \u2603', True, None, 42))
        self.store.frozen = frozenset((u'blue', u'red'))
        self.providers = {'store': lambda: self.store, 'persistent': lambda: {}}

    def test_safe_scalar_member_roundtrip_and_pinning(self):
        path = (('attribute', 'flags'), ('member', u'snow \u2603'))
        root = build_tree_page(self.providers, 'store', (), 0, 80)
        entry = next(node for node in root['items'] if node['name'] == 'flags')
        self.assertTrue(entry['expandable'])
        child = build_tree_value(self.providers, 'store', path)['node']
        self.assertEqual(child['compare_sample']['text'], u'snow \u2603')
        self.assertIn(u'snow', format_location('store', path))
        self.assertEqual(decode_location(encode_location('store', path)), ('store', path))
        self.assertEqual(build_full_value(self.providers, 'store', path)['kind'], 'string')
        self.store.flags.remove(u'snow \u2603')
        self.assertEqual(build_tree_value(self.providers, 'store', path)['node']['state'], 'missing')

    def test_python2_utf8_bytes_and_unsupported_values_are_filtered(self):
        self.store.flags.add(b'valid')
        self.store.flags.add(b'\xc3\xa9')
        self.store.flags.add(b'\xff')
        children = build_tree_page(self.providers, 'store',
            (('attribute', 'flags'),), 0, 80)
        names = [node['name'] for node in children['items']]
        self.assertIn("{'valid'}", names)
        self.assertNotIn("{'\\xff'}", names)
        self.assertTrue(children['capped'])
        self.assertFalse(children['more'])
        for invalid in (b'\xff', u'x' * 257):
            with self.assertRaises(ValueError):
                validate_tree_request('store', [
                    ['attribute', 'flags'], ['member', invalid]], 0, 1)

    def test_frozenset_remains_read_only(self):
        page = build_tree_page(self.providers, 'store',
            (('attribute', 'frozen'),), 0, 80)
        self.assertEqual(len(page['items']), 2)
        self.assertTrue(all('member' in item['key'] for item in page['items']))


if __name__ == '__main__':
    unittest.main()
