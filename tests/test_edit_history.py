"""Conflict-aware bounded undo/redo history tests."""
import sys
import unittest
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))
from renpy_inspector.edit_history import (
    MAX_EDIT_HISTORY_BYTES, MAX_EDIT_HISTORY_ENTRIES, PrimitiveEditHistory,
    validate_edit_history_request,
)
from renpy_inspector.edit_values import (
    EditConflict, EditLocked, apply_primitive_edit, inspect_edit_target,
)


class PrimitiveEditHistoryTests(unittest.TestCase):
    def setUp(self):
        self.store = ModuleType('store')
        self.store.score = 2
        self.store.memo = 'before'
        self.providers = {'store': lambda: self.store}

    def edit(self, name, text, history):
        path = (('attribute', name),)
        target = inspect_edit_target(self.providers, 'store', path)
        result = apply_primitive_edit(
            self.providers, 'store', path, target['expected'], target['type'], text)
        entry_id = history.record(
            'store', path, target['type'], result['before'], result['after'], 10.0)
        return entry_id

    def test_undo_redo_round_trip_and_status(self):
        history = PrimitiveEditHistory()
        entry_id = self.edit('score', '7', history)
        self.assertEqual(history.snapshot(0)['revision'], 1)
        self.assertEqual(self.store.score, 7)
        self.assertTrue(history.snapshot(0)['can_undo'])
        self.assertTrue(history.apply(self.providers, 'undo', entry_id)['applied'])
        self.assertEqual(self.store.score, 2)
        snapshot = history.snapshot(1)
        self.assertFalse(snapshot['can_undo'])
        self.assertTrue(snapshot['can_redo'])
        self.assertEqual(snapshot['entries'][0]['status'], 'undone')
        self.assertEqual(snapshot['revision'], 2)
        self.assertTrue(history.apply(self.providers, 'redo', entry_id)['applied'])
        self.assertEqual(self.store.score, 7)
        snapshot = history.snapshot(2)
        self.assertTrue(snapshot['can_undo'])
        self.assertFalse(snapshot['can_redo'])
        self.assertEqual(snapshot['entries'][0]['status'], 'applied')

    def test_conflicting_game_write_retires_only_the_unsafe_stack_head(self):
        history = PrimitiveEditHistory()
        first = self.edit('score', '7', history)
        second = self.edit('memo', 'after', history)
        self.store.score = 99
        self.assertTrue(history.apply(self.providers, 'undo', second)['applied'])
        self.assertEqual(self.store.memo, 'before')
        with self.assertRaises(EditConflict):
            history.apply(self.providers, 'undo', first)
        self.assertEqual(self.store.score, 99)
        snapshot = history.snapshot(2)
        self.assertFalse(snapshot['can_undo'])
        self.assertTrue(snapshot['can_redo'])
        self.assertEqual(snapshot['entries'][0]['status'], 'conflicted')
        self.assertEqual(snapshot['entries'][1]['status'], 'undone')

    def test_stale_lock_rejects_undo_without_retiring_history(self):
        history = PrimitiveEditHistory()
        entry_id = self.edit('score', '7', history)
        with self.assertRaises(EditLocked) as caught:
            history.apply(self.providers, 'undo', entry_id,
                          lambda scope, path: {
                              'locked': True, 'stale': True,
                              'stale_reason': 'value_changed',
                          })
        self.assertTrue(caught.exception.stale)
        self.assertEqual(caught.exception.stale_reason, 'value_changed')
        self.assertEqual(self.store.score, 7)
        snapshot = history.snapshot(0)
        self.assertTrue(snapshot['can_undo'])
        self.assertEqual(snapshot['entries'][0]['status'], 'applied')

    def test_new_edit_discards_redo_branch_but_keeps_audit_record(self):
        history = PrimitiveEditHistory()
        old_id = self.edit('score', '7', history)
        history.apply(self.providers, 'undo', old_id)
        new_id = self.edit('score', '9', history)
        self.assertNotEqual(old_id, new_id)
        snapshot = history.snapshot(2)
        self.assertFalse(snapshot['can_redo'])
        self.assertTrue(snapshot['can_undo'])
        states = {entry['id']: entry['status'] for entry in snapshot['entries']}
        self.assertEqual(states[old_id], 'superseded')
        self.assertEqual(states[new_id], 'applied')

    def test_wrong_stack_head_or_generation_cannot_reverse(self):
        history = PrimitiveEditHistory()
        entry_id = self.edit('score', '7', history)
        with self.assertRaises(EditConflict):
            history.apply(self.providers, 'undo', entry_id + 1)
        self.assertEqual(self.store.score, 7)
        self.assertEqual(history.snapshot(4)['undo_entry_id'], entry_id)

    def test_record_retention_and_memory_are_bounded(self):
        history = PrimitiveEditHistory()
        for index in range(60):
            self.store.score = index
            self.edit('score', str(index + 1), history)
        snapshot = history.snapshot(60)
        self.assertEqual(len(snapshot['entries']), MAX_EDIT_HISTORY_ENTRIES)
        self.assertLessEqual(snapshot['bytes_used'], MAX_EDIT_HISTORY_BYTES)
        self.assertEqual(snapshot['entries'][0]['id'], 11)
        self.assertEqual(snapshot['entries'][-1]['id'], 60)
        self.assertEqual(len(history.undo_stack), MAX_EDIT_HISTORY_ENTRIES)

    def test_utf8_byte_budget_trims_before_record_count_limit(self):
        history = PrimitiveEditHistory()
        path = (('attribute', 'memo'),)
        for index in range(20):
            history.record('store', path, 'unicode', u'☃' * 1024,
                           u'雪' * 1024, float(index))
        snapshot = history.snapshot(20)
        self.assertLess(len(snapshot['entries']), MAX_EDIT_HISTORY_ENTRIES)
        self.assertLessEqual(snapshot['bytes_used'], MAX_EDIT_HISTORY_BYTES)
        self.assertGreater(snapshot['entries'][0]['id'], 1)

    def test_load_or_rollback_reset_drops_all_reversals(self):

        history = PrimitiveEditHistory()
        self.edit('score', '7', history)
        history.reset('after_load')
        snapshot = history.snapshot(8)
        self.assertEqual(snapshot['entries'], [])
        self.assertFalse(snapshot['can_undo'])
        self.assertFalse(snapshot['can_redo'])
        self.assertEqual(snapshot['last_reset_reason'], 'after_load')

    def test_history_request_is_strict_and_rejects_boolean_ids(self):
        payload = {'action': 'undo', 'generation': 4, 'entry_id': 2}
        self.assertEqual(validate_edit_history_request(payload), ('undo', 4, 2))
        for invalid in (
                dict(payload, action='execute'),
                dict(payload, generation=True),
                dict(payload, entry_id=True),
                dict(payload, entry_id=0),
                dict(payload, extra='value'),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_edit_history_request(invalid)


if __name__ == '__main__':
    unittest.main()
