# -*- coding: utf-8 -*-
"""Python 2.7-compatible primitive edit and boundary coverage."""
from __future__ import unicode_literals

import os
import sys
import unittest
from types import ModuleType

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.edit_values import (
    EditConflict, apply_primitive_edit, inspect_edit_target, validate_edit_request,
)


class PrimitiveEditPython2Tests(unittest.TestCase):
    def setUp(self):
        self.root = ModuleType(str('store'))
        self.root.score = 10
        self.root.text = u'Snow: \u2603'
        self.root.utf8_bytes = 'ascii only'
        self.root.legacy = long(12345678901234567890)
        self.root.flags = {'enabled': True, 'inventory': [0, 1]}
        self.providers = {'store': lambda: self.root, 'persistent': lambda: {}}

    def test_unicode_integer_long_and_nested_builtin_mutations(self):
        for path, candidate in (
                ((('attribute', 'score'),), '12'),
                ((('attribute', 'text'),), u'New \u2603'),
                ((('attribute', 'legacy'),), '12345678901234567891'),
                ((('attribute', 'flags'), ('key', 'enabled')), 'False'),
                ((('attribute', 'flags'), ('key', 'inventory'), ('index', 1)), '99')):
            result = inspect_edit_target(self.providers, 'store', path)
            self.assertTrue(result['editable'], result)
            self.assertTrue(apply_primitive_edit(
                self.providers, 'store', path, result['expected'],
                result['type'], candidate)['applied'])
        self.assertEqual(self.root.score, 12)
        self.assertEqual(self.root.text, u'New \u2603')
        self.assertEqual(self.root.legacy, long(12345678901234567891))
        self.assertIs(type(self.root.legacy), long)
        self.assertIs(self.root.flags['enabled'], False)
        self.assertEqual(self.root.flags['inventory'][1], 99)

    def test_byte_strings_are_not_silently_converted_or_editable(self):
        result = inspect_edit_target(
            self.providers, 'store', (('attribute', 'utf8_bytes'),))
        self.assertFalse(result['editable'])

    def test_conflict_and_validation_on_python_two(self):
        path = (('attribute', 'score'),)
        result = inspect_edit_target(self.providers, 'store', path)
        self.root.score = 18
        with self.assertRaises(EditConflict):
            apply_primitive_edit(self.providers, 'store', path,
                                 result['expected'], result['type'], '23')
        payload = {'scope': 'store', 'path': [['attribute', 'score']],
                   'generation': 0, 'expected': 'a' * 64, 'type': 'int',
                   'text': u'23'}
        self.assertEqual(validate_edit_request(payload)[-1], u'23')
        payload['type'] = 'object'
        with self.assertRaises(ValueError):
            validate_edit_request(payload)


if __name__ == '__main__':
    unittest.main()
