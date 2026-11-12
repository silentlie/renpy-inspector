"""Python 2.7 exact compare samples and byte-string decoding safety."""
from __future__ import unicode_literals

import os
import sys
import unittest
from types import ModuleType

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.bridge_paging import (
    MAX_COMPARE_SAMPLE_CHARS, comparison_sample, build_lazy_snapshot,
)
from renpy_inspector.compat import PY2


class CompareCapturePy2Tests(unittest.TestCase):
    def test_unicode_and_byte_text_are_small_and_exact(self):
        self.assertEqual(comparison_sample(u'first\nsecond')['text'], u'first\nsecond')
        if PY2:
            self.assertEqual(comparison_sample(b'hello')['text'], u'hello')
            self.assertEqual(comparison_sample(b'\xc3\xa9')['text'], u'\u00e9')
            self.assertIsNone(comparison_sample(b'\xff'))
        else:
            # Python 3 bytes are not part of the supported string primitive
            # types. The same compatibility tests run in both interpreters.
            self.assertIsNone(comparison_sample(b'hello'))
            self.assertIsNone(comparison_sample(b'\xff'))
        self.assertIsNone(comparison_sample(u'x' * (MAX_COMPARE_SAMPLE_CHARS + 1)))
        self.assertEqual(comparison_sample(True)['text'], 'True')
        self.assertEqual(comparison_sample(None)['text'], 'None')

    def test_sampled_page_remains_json_safe_and_never_renders_game_objects(self):
        store = ModuleType(str('store'))
        store.memo = u'abcd \u2603'
        class Hostile(object):
            def __repr__(self):
                raise AssertionError('repr must not be called')
        store.unsafe = Hostile()
        root = build_lazy_snapshot(
            {'store': lambda: store, 'persistent': lambda: {}})
        nodes = dict((n['name'], n) for n in root['scopes']['store'])
        self.assertEqual(nodes['memo']['compare_sample']['text'], store.memo)
        self.assertNotIn('compare_sample', nodes['unsafe'])


if __name__ == '__main__':
    unittest.main()
