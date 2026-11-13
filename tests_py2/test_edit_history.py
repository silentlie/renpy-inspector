# -*- coding: utf-8 -*-
"""Python 2/3 compatibility for the bounded edit history."""
from __future__ import unicode_literals

import os
import sys
import unittest
from types import ModuleType

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.compat import integer_types
from renpy_inspector.edit_history import PrimitiveEditHistory, validate_edit_history_request
from renpy_inspector.edit_values import apply_primitive_edit, inspect_edit_target


class EditHistoryPython2Tests(unittest.TestCase):
    def setUp(self):
        self.root = ModuleType(str('store'))
        self.root.number = integer_types[-1](12345678901234567890)
        self.root.label = u'Before \u2603'
        self.providers = {'store': lambda: self.root}

    def test_unicode_and_long_roundtrip(self):
        history = PrimitiveEditHistory()
        path = (('attribute', 'number'),)
        target = inspect_edit_target(self.providers, 'store', path)
        changed = apply_primitive_edit(
            self.providers, 'store', path, target['expected'], target['type'],
            u'12345678901234567891')
        entry_id = history.record(
            'store', path, target['type'], changed['before'], changed['after'], 1.0)
        self.assertTrue(history.apply(self.providers, 'undo', entry_id)['applied'])
        self.assertEqual(self.root.number, integer_types[-1](12345678901234567890))
        self.assertIs(type(self.root.number), integer_types[-1])
        self.assertTrue(history.apply(self.providers, 'redo', entry_id)['applied'])
        self.assertEqual(self.root.number, integer_types[-1](12345678901234567891))

    def test_unicode_history_text_and_strict_action_payload(self):
        history = PrimitiveEditHistory()
        path = (('attribute', 'label'),)
        target = inspect_edit_target(self.providers, 'store', path)
        changed = apply_primitive_edit(
            self.providers, 'store', path, target['expected'], target['type'],
            u'After \u2603')
        entry_id = history.record(
            'store', path, target['type'], changed['before'], changed['after'], 2.0)
        self.assertEqual(history.snapshot(1)['entries'][0]['before'], u'Before \u2603')
        self.assertEqual(validate_edit_history_request({
            'action': u'undo', 'generation': 1, 'entry_id': entry_id}),
            (u'undo', 1, entry_id))


if __name__ == '__main__':
    unittest.main()
