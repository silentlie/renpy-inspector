"""Bounded, session-only, conflict-aware undo/redo for explicit primitive edits.

Records contain only typed paths and bounded exact primitive text. They never
retain game-object references or touch Ren'Py save files. Every reversal is a
fresh compare-and-swap performed by the interaction-thread bridge tick.
"""
from __future__ import unicode_literals

import json

from .compat import integer_types, string_types, text_type, to_text
from .edit_values import (
    MAX_EDIT_TEXT, EditConflict, EditUnsupported, _fingerprint,
    apply_primitive_edit,
)

MAX_EDIT_HISTORY_ENTRIES = 50
MAX_EDIT_HISTORY_BYTES = 64 * 1024
MAX_HISTORY_REQUEST_BYTES = 6144


def validate_edit_history_request(payload):
    if type(payload) is not dict or set(payload) != set((
            'action', 'generation', 'entry_id')):
        raise ValueError('invalid edit history request fields')
    action = payload['action']
    if type(action) is not text_type or action not in ('undo', 'redo'):
        raise ValueError('invalid edit history action')
    generation = payload['generation']
    if type(generation) not in integer_types or not 0 <= generation < 2 ** 53:
        raise ValueError('invalid edit history generation')
    entry_id = payload['entry_id']
    if type(entry_id) not in integer_types or not 1 <= entry_id < 2 ** 53:
        raise ValueError('invalid edit history entry')
    return action, generation, entry_id


class PrimitiveEditHistory(object):
    """Bounded in-memory edit log with independent undo and redo stacks."""

    def __init__(self):
        self.entries = []
        self.undo_stack = []
        self.redo_stack = []
        self.next_id = 0
        self.bytes_used = 0
        self.total_recorded = 0
        self.revision = 0
        self.last_reset_reason = 'bridge_start'

    @staticmethod
    def _size(entry):
        key = entry['key']
        before = entry['before']
        after = entry['after']
        return (len(key.encode('utf-8')) + len(before.encode('utf-8')) +
                len(after.encode('utf-8')) + 192)

    def record(self, scope, path, typename, before, after, captured_at):
        """Record a successful write; drop the redo branch after a new edit."""
        if (scope != 'store' or type(typename) not in string_types or
                type(before) not in string_types or type(after) not in string_types):
            raise ValueError('invalid primitive edit history record')
        typename = to_text(typename)
        before = to_text(before)
        after = to_text(after)
        if len(before) > MAX_EDIT_TEXT or len(after) > MAX_EDIT_TEXT:
            raise ValueError('invalid primitive edit history record')
        if before == after:
            raise ValueError('no-op edit history record')
        for entry in self.redo_stack:
            entry['status'] = 'superseded'
        self.redo_stack = []
        self.next_id += 1
        key = json.dumps([scope, path], ensure_ascii=True, separators=(',', ':'))
        entry = {
            'id': self.next_id, 'scope': scope,
            'path': [[kind, value] for kind, value in path],
            'key': key, 'type': typename, 'before': before, 'after': after,
            'created_at': captured_at, 'status': 'applied',
        }
        size = self._size(entry)
        if size > MAX_EDIT_HISTORY_BYTES:
            raise ValueError('primitive edit history record exceeds memory budget')
        entry['_size'] = size
        self.entries.append(entry)
        self.undo_stack.append(entry)
        self.bytes_used += size
        self.total_recorded += 1
        self.revision += 1
        while (len(self.entries) > MAX_EDIT_HISTORY_ENTRIES or
               self.bytes_used > MAX_EDIT_HISTORY_BYTES):
            removed = self.entries.pop(0)
            self.bytes_used -= removed['_size']
            self.undo_stack = [item for item in self.undo_stack
                               if item['id'] != removed['id']]
            self.redo_stack = [item for item in self.redo_stack
                               if item['id'] != removed['id']]
        return entry['id']

    def apply(self, providers, action, entry_id):
        """Apply the current stack head only if its exact recorded value remains."""
        if action == 'undo':
            stack = self.undo_stack
            expected_text = 'after'
            replacement_text = 'before'
        elif action == 'redo':
            stack = self.redo_stack
            expected_text = 'before'
            replacement_text = 'after'
        else:
            raise ValueError('unsupported history action')
        if not stack or stack[-1]['id'] != entry_id:
            raise EditConflict('Edit history changed; refresh before retrying')
        entry = stack[-1]
        expected = entry[expected_text]
        replacement = entry[replacement_text]
        try:
            apply_primitive_edit(
                providers, entry['scope'],
                tuple((segment[0], segment[1]) for segment in entry['path']),
                _fingerprint(entry['type'], expected), entry['type'], replacement)
        except (EditConflict, EditUnsupported):
            # A game-side write or changed container makes this record unsafe.
            # Retire only the conflicting stack head; older unrelated edits
            # remain eligible for reversal.
            stack.pop()
            entry['status'] = 'conflicted'
            self.revision += 1
            raise EditConflict('Recorded variable no longer matches; edit retired')
        stack.pop()
        if action == 'undo':
            entry['status'] = 'undone'
            self.redo_stack.append(entry)
        else:
            entry['status'] = 'applied'
            self.undo_stack.append(entry)
        self.revision += 1
        return {'applied': True, 'action': action, 'entry_id': entry_id}

    def reset(self, reason='game_state_changed'):
        """Drop reversals across load/rollback or any unclassified generation."""
        self.entries = []
        self.undo_stack = []
        self.redo_stack = []
        self.bytes_used = 0
        self.revision += 1
        self.last_reset_reason = reason

    def snapshot(self, generation):
        """Return JSON-safe copies; never expose internal mutable records."""
        visible = []
        for entry in self.entries:
            visible.append({
                'id': entry['id'], 'scope': entry['scope'],
                'path': [list(segment) for segment in entry['path']],
                'key': entry['key'], 'type': entry['type'],
                'before': entry['before'], 'after': entry['after'],
                'created_at': entry['created_at'], 'status': entry['status'],
            })
        return {
            'protocol': 1, 'generation': generation, 'revision': self.revision,
            'limit': MAX_EDIT_HISTORY_ENTRIES,
            'byte_limit': MAX_EDIT_HISTORY_BYTES,
            'bytes_used': self.bytes_used,
            'total_recorded': self.total_recorded,
            'entries': visible,
            'can_undo': bool(self.undo_stack),
            'undo_entry_id': self.undo_stack[-1]['id'] if self.undo_stack else None,
            'can_redo': bool(self.redo_stack),
            'redo_entry_id': self.redo_stack[-1]['id'] if self.redo_stack else None,
            'last_reset_reason': self.last_reset_reason,
        }
