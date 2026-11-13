"""Bounded exact-path lock manager and request validation tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.variable_locks import (
    MAX_VARIABLE_LOCKS, MAX_VARIABLE_LOCKS_BYTES, VariableLockLimit,
    VariableLocks, validate_variable_lock_request,
)


class VariableLocksTests(unittest.TestCase):
    def setUp(self):
        self.path = (('attribute', 'player'), ('key', 'hp'))

    def test_lock_is_exact_path_and_idempotent(self):
        locks = VariableLocks()
        self.assertTrue(locks.lock('store', self.path, 1.0, 'a' * 64, 'int'))
        self.assertFalse(locks.lock('store', self.path, 2.0, 'a' * 64, 'int'))
        self.assertTrue(locks.is_locked('store', self.path))
        self.assertFalse(locks.is_locked('store', (('attribute', 'player'),)))
        snapshot = locks.snapshot()
        self.assertEqual(snapshot['revision'], 1)
        self.assertEqual(snapshot['entries'][0]['path'],
                         [['attribute', 'player'], ['key', 'hp']])
        self.assertEqual(snapshot['entries'][0]['key'],
                         '["store",[["attribute","player"],["key","hp"]]]')

    def test_python_dictionary_boolean_integer_aliases_share_lock_identity(self):
        locks = VariableLocks()
        true_path = (('attribute', 'flags'), ('key', True))
        one_path = (('attribute', 'flags'), ('key', 1))
        self.assertTrue(locks.lock('store', true_path, 1.0, 'a' * 64, 'int'))
        self.assertTrue(locks.is_locked('store', one_path))
        self.assertFalse(locks.lock('store', one_path, 2.0, 'a' * 64, 'int'))
        self.assertEqual(locks.snapshot()['entries'][0]['path'][-1], ['key', True])
        self.assertTrue(locks.unlock('store', one_path))
        self.assertFalse(locks.is_locked('store', true_path))

        false_path = (('attribute', 'flags'), ('key', False))
        zero_path = (('attribute', 'flags'), ('key', 0))
        self.assertTrue(locks.lock('store', false_path, 3.0, 'a' * 64, 'int'))
        self.assertTrue(locks.is_locked('store', zero_path))
        self.assertTrue(locks.unlock('store', zero_path))

    def test_unlock_is_idempotent_and_does_not_touch_game_state(self):
        locks = VariableLocks()
        self.assertFalse(locks.unlock('store', self.path))
        locks.lock('store', self.path, 1.0, 'a' * 64, 'int')
        self.assertTrue(locks.unlock('store', self.path))
        self.assertFalse(locks.unlock('store', self.path))
        self.assertFalse(locks.is_locked('store', self.path))
        self.assertEqual(locks.snapshot()['entries'], [])

    def test_lock_count_and_memory_are_bounded(self):
        locks = VariableLocks()
        for index in range(MAX_VARIABLE_LOCKS):
            locks.lock('store', (('attribute', 'v{}'.format(index)),), float(index), 'a' * 64, 'int')
        with self.assertRaises(VariableLockLimit):
            locks.lock('store', (('attribute', 'overflow'),), 999.0, 'a' * 64, 'int')
        snapshot = locks.snapshot()
        self.assertEqual(len(snapshot['entries']), MAX_VARIABLE_LOCKS)
        self.assertLessEqual(snapshot['bytes_used'], MAX_VARIABLE_LOCKS_BYTES)

    def test_serialized_path_budget_is_enforced_before_count_limit(self):
        locks = VariableLocks()
        for index in range(MAX_VARIABLE_LOCKS):
            path = tuple(
                [('attribute', 'v{}{}'.format(index, 'x' * 200))] +
                [('key', 'y' * 200) for unused in range(7)])
            try:
                locks.lock('store', path, float(index), 'a' * 64, 'int')
            except VariableLockLimit:
                break
        snapshot = locks.snapshot()
        self.assertGreater(len(snapshot['entries']), 1)
        self.assertLess(len(snapshot['entries']), MAX_VARIABLE_LOCKS)
        self.assertLessEqual(snapshot['bytes_used'], MAX_VARIABLE_LOCKS_BYTES)

    def test_external_value_and_type_changes_mark_lock_stale_but_keep_it_active(self):
        locks = VariableLocks()
        self.assertTrue(locks.lock('store', self.path, 1.0, 'a' * 64, 'int'))
        same = {'editable': True, 'type': 'int', 'expected': 'a' * 64}
        state = locks.observe('store', self.path, same, 2.0)
        self.assertTrue(state['locked'])
        self.assertFalse(state['stale'])

        changed = {'editable': True, 'type': 'int', 'expected': 'b' * 64}
        state = locks.observe('store', self.path, changed, 3.0)
        self.assertTrue(state['locked'])
        self.assertTrue(state['stale'])
        self.assertEqual(state['stale_reason'], 'value_changed')
        revision = locks.revision
        # Staleness is sticky, even if gameplay later restores the old value.
        state = locks.observe('store', self.path, same, 4.0)
        self.assertTrue(state['stale'])
        self.assertEqual(locks.revision, revision)
        self.assertEqual(locks.snapshot()['last_event']['action'], 'stale')

        locks.refresh('store', self.path, 5.0, 'b' * 64, 'int')
        state = locks.state('store', self.path)
        self.assertTrue(state['locked'])
        self.assertFalse(state['stale'])
        self.assertEqual(state['baseline_type'], 'int')
        self.assertEqual(locks.snapshot()['last_event']['action'], 'refreshed')

    def test_missing_or_unsupported_targets_mark_lock_stale_and_can_be_unlocked(self):
        locks = VariableLocks()
        locks.lock('store', self.path, 1.0, 'a' * 64, 'int')
        state = locks.observe('store', self.path, {
            'editable': False, 'reason': 'Variable no longer exists'}, 2.0)
        self.assertTrue(state['locked'])
        self.assertTrue(state['stale'])
        self.assertEqual(state['stale_reason'], 'target_unavailable')
        self.assertTrue(locks.unlock('store', self.path, 3.0))
        self.assertFalse(locks.state('store', self.path)['locked'])

    def test_background_checks_rotate_and_skip_stale_entries(self):
        locks = VariableLocks()
        for index in range(10):
            path = (('attribute', 'v{}'.format(index)),)
            locks.lock('store', path, float(index), 'a' * 64, 'int')
        first = locks.next_check_batch(4)
        second = locks.next_check_batch(4)
        self.assertEqual(len(first), 4)
        self.assertEqual(len(second), 4)
        self.assertNotEqual(first, second)
        locks.observe('store', first[0][1], {'editable': False}, 11.0)
        self.assertNotIn(first[0], locks.next_check_batch(10))

    def test_refresh_requires_an_existing_lock(self):
        from renpy_inspector.variable_locks import VariableLockMissing
        with self.assertRaises(VariableLockMissing):
            locks = VariableLocks()
            locks.refresh('store', self.path, 1.0, 'a' * 64, 'int')

    def test_reset_drops_locks_and_advances_revision(self):

        locks = VariableLocks()
        locks.lock('store', self.path, 1.0, 'a' * 64, 'int')
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
        refresh = dict(payload, action='refresh')
        self.assertEqual(validate_variable_lock_request(refresh)[0], 'refresh')
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
