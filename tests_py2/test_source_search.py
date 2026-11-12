# -*- coding: utf-8 -*-
"""Python 2.7 source search and bounded UTF-8 compatibility tests."""
from __future__ import unicode_literals

import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.bridge_scripts import (
    search_source_text, validate_source_search_request,
    SOURCE_SEARCH_MAX_FILE_BYTES,
)


class SourceSearchPy2Tests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='renpy-source-search-')
        self.addCleanup(shutil.rmtree, self.root)
        with io.open(os.path.join(self.root, 'game_script.rpy'), 'w',
                     encoding='utf-8') as handle:
            handle.write(u'label start:\n    "Trésor in this scene"\n'
                         u'    $ score = 2\n')

    def test_unicode_case_insensitive_literal_search(self):
        result = search_source_text(self.root, u'trésor', '0:0', 20)
        self.assertTrue(result['available'])
        self.assertEqual(len(result['matches']), 1)
        self.assertEqual(result['matches'][0]['line'], 2)
        self.assertIn(u'Trésor', result['matches'][0]['text'])
        self.assertFalse(result['more'])

    def test_oversized_file_is_skipped_not_loaded_unbounded(self):
        with io.open(os.path.join(self.root, 'too_big.rpy'), 'wb') as handle:
            handle.write(b'score ' * (SOURCE_SEARCH_MAX_FILE_BYTES // 6 + 10))
        result = search_source_text(self.root, 'score')
        self.assertTrue(result['limited'])
        self.assertEqual(len(result['matches']), 1)
        self.assertEqual(result['matches'][0]['file'], 'game_script.rpy')

    def test_cursor_and_input_validation(self):
        for args in [('x', '0:0', 20), ('word', '../', 20),
                     ('word', '0:0', 21), ('word', '1:100001', 1)]:
            with self.assertRaises(ValueError):
                validate_source_search_request(*args)


if __name__ == '__main__':
    unittest.main()
