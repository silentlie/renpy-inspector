# -*- coding: utf-8 -*-
"""Python 2/3 compatibility coverage for session variable locks."""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.variable_locks import (
    VariableLocks, validate_variable_lock_request,
)


class VariableLocksCompatibilityTests(unittest.TestCase):
    def test_unicode_typed_path_round_trip(self):
        locks = VariableLocks()
        path = (('attribute', u'player'), ('key', u'生命'))
        self.assertTrue(locks.lock('store', path, 1.0, 'a' * 64, 'int'))
        entry = locks.snapshot()['entries'][0]
        self.assertEqual(entry['path'], [
            ['attribute', u'player'], ['key', u'生命']])
        self.assertTrue(locks.is_locked('store', path))
        self.assertTrue(locks.unlock('store', path))
        self.assertFalse(locks.is_locked('store', path))

    def test_python_dictionary_boolean_integer_aliases_share_lock_identity(self):
        locks = VariableLocks()
        bool_path = (('attribute', u'flags'), ('key', True))
        int_path = (('attribute', u'flags'), ('key', 1))
        self.assertTrue(locks.lock('store', bool_path, 1.0, 'a' * 64, 'int'))
        self.assertTrue(locks.is_locked('store', int_path))
        self.assertFalse(locks.lock('store', int_path, 2.0, 'a' * 64, 'int'))
        self.assertTrue(locks.unlock('store', int_path))
        self.assertFalse(locks.is_locked('store', bool_path))

    def test_stale_baseline_and_refresh_are_python2_compatible(self):
        locks = VariableLocks()
        path = (('attribute', u'player'), ('key', u'生命'))
        locks.lock('store', path, 1.0, 'a' * 64, u'int')
        state = locks.observe('store', path, {
            'editable': True, 'type': u'int', 'expected': 'b' * 64}, 2.0)
        self.assertTrue(state['locked'])
        self.assertTrue(state['stale'])
        self.assertEqual(state['stale_reason'], 'value_changed')
        locks.refresh('store', path, 3.0, 'b' * 64, u'int')
        self.assertFalse(locks.state('store', path)['stale'])

    def test_bridge_fingerprint_byte_strings_normalize_on_python2(self):
        locks = VariableLocks()
        path = (('attribute', u'score'),)
        self.assertTrue(locks.lock('store', path, 1.0, b'a' * 64, b'int'))
        self.assertEqual(locks.state('store', path)['baseline_type'], u'int')
        locks.refresh('store', path, 2.0, b'b' * 64, b'long')
        self.assertEqual(locks.state('store', path)['baseline_type'], u'long')

    def test_strict_generation_and_action_validation(self):
        payload = {'action': u'lock', 'scope': u'store',
                   'path': [['attribute', u'score']], 'generation': 3}
        self.assertEqual(validate_variable_lock_request(payload)[0], u'lock')
        self.assertEqual(validate_variable_lock_request(
            dict(payload, action=u'unlock'))[0], u'unlock')
        self.assertEqual(validate_variable_lock_request(
            dict(payload, action=u'refresh'))[0], u'refresh')
        for invalid in (dict(payload, generation=True),
                        dict(payload, generation=-1),
                        dict(payload, scope=u'persistent'),
                        dict(payload, action=u'execute')):
            with self.assertRaises(ValueError):
                validate_variable_lock_request(invalid)


if __name__ == '__main__':
    unittest.main()
