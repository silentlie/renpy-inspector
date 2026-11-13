"""Bounded exact-path lock manager and request validation tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.variable_locks import (
    MAX_VARIABLE_LOCKS, MAX_VARIABLE_LOCKS_BYTES, VariableLocks,
    validate_variable_lock_request,
)


class VariableLocksTests(unittest.TestCase):
    def setUp(self):
        self.path = (('attribute', 'player'), ('key', 'hp'))

    def test_lock_is_exact_path_and_idempotent(self):
        locks = VariableLocks()
        self.assertTrue(locks.lock('store', self.path, 1.0))
        self.assertFalse(locks.lock('store', self.path, 2.0))
        self.assertTrue(locks.is_locked('store', self.path))
        self.assertFalse(locks.is_locked('store', (('attribute', 'player'),)))
        snapshot = locks.snapshot()
        self.assertEqual(snapshot['revision'], 1)
        self.assertEqual(snapshot['entries'][0]['path'],
                         [['attribute', 'player'], ['key', 'hp']])
        self.assertEqual(snapshot['entries'][0]['key'],
                         '["store",[["attribute","player"],["key","hp"]]]')

    def test_unlock_is_idempotent_and_does_not_touch_game_state(self):
        locks = VariableLocks()
        self.assertFalse(locks.unlock('store', self.path))
        locks.lock('store', self.path, 1.0)
        self.assertTrue(locks.unlock('store', self.path))
        self.assertFalse(locks.unlock('store', self.path))
        self.assertFalse(locks.is_locked('store', self.path))
        self.assertEqual(locks.snapshot()['entries'], [])

    def test_lock_count_and_memory_are_bounded(self):
        locks = VariableLocks()
        for index in range(MAX_VARIABLE_LOCKS):
            locks.lock('store', (('attribute', 'v{}'.format(index)),), float(index))
        with self.assertRaises(ValueError):
            locks.lock('store', (('attribute', 'overflow'),), 999.0)
        snapshot = locks.snapshot()
        self.assertEqual(len(snapshot['entries']), MAX_VARIABLE_LOCKS)
        self.assertLessEqual(snapshot['bytes_used'], MAX_VARIABLE_LOCKS_BYTES)

    def test_reset_drops_locks_and_advances_revision(self):
        locks = VariableLocks()
        locks.lock('store', self.path, 1.0)
        revision = locks.revision
        locks.reset('after_load')
        self.assertFalse(locks.is_locked('store', self.path))
        self.assertEqual(locks.snapshot()['entries'], [])
        self.assertGreater(locks.revision, revision)
        self.assertEqual(locks.snapshot()['last_reset_reason'], 'after_load')

    def test_request_validation_is_strict(self):
        payload = {'action': 'lock', 'scope': 'store',
                   'path': [['attribute', 'score']], 'generation': 4}
        self.assertEqual(validate_variable_lock_request(payload),
                         ('lock', 'store', (('attribute', 'score'),), 4))
        unlock = dict(payload, action='unlock')
        self.assertEqual(validate_variable_lock_request(unlock)[0], 'unlock')
        for invalid in (
                dict(payload, action='execute'),
                dict(payload, scope='persistent'),
                dict(payload, path=[]),
                dict(payload, path=[['attribute', 'score'], ['member', 'x']]),
                dict(payload, generation=True),
                dict(payload, generation=-1),
                dict(payload, extra='field'),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_variable_lock_request(invalid)


if __name__ == '__main__':
    unittest.main()
