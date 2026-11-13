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
        self.assertTrue(locks.lock('store', path, 1.0))
        entry = locks.snapshot()['entries'][0]
        self.assertEqual(entry['path'], [
            ['attribute', u'player'], ['key', u'生命']])
        self.assertTrue(locks.is_locked('store', path))
        self.assertTrue(locks.unlock('store', path))
        self.assertFalse(locks.is_locked('store', path))

    def test_strict_generation_and_action_validation(self):
        payload = {'action': u'lock', 'scope': u'store',
                   'path': [['attribute', u'score']], 'generation': 3}
        self.assertEqual(validate_variable_lock_request(payload)[0], u'lock')
        self.assertEqual(validate_variable_lock_request(
            dict(payload, action=u'unlock'))[0], u'unlock')
        for invalid in (dict(payload, generation=True),
                        dict(payload, generation=-1),
                        dict(payload, scope=u'persistent'),
                        dict(payload, action=u'execute')):
            with self.assertRaises(ValueError):
                validate_variable_lock_request(invalid)


if __name__ == '__main__':
    unittest.main()
