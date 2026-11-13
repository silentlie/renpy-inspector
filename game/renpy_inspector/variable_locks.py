"""Bounded, session-only locks for explicit inspector writes.

Locks protect an exact typed Store path from this inspector's edit and
undo/redo endpoints. They do not wrap Python objects, intercept game scripts,
or prevent Ren'Py from changing a variable during normal gameplay.
"""
from __future__ import unicode_literals

import json

from .bridge_paging import validate_tree_request
from .compat import integer_types, text_type

MAX_VARIABLE_LOCKS = 128
MAX_VARIABLE_LOCKS_BYTES = 32 * 1024
MAX_VARIABLE_LOCK_REQUEST_BYTES = 4096


class VariableLockLimit(Exception):
    """The bounded session lock set is full."""


def validate_variable_lock_request(payload):
    if type(payload) is not dict or set(payload) != set((
            'action', 'scope', 'path', 'generation')):
        raise ValueError('invalid variable lock request fields')
    action = payload['action']
    if type(action) is not text_type or action not in ('lock', 'unlock'):
        raise ValueError('invalid variable lock action')
    scope, path, unused_offset, unused_size = validate_tree_request(
        payload['scope'], payload['path'], 0, 1)
    if scope != 'store' or not path or any(kind == 'member' for kind, unused in path):
        raise ValueError('locks require an existing Store variable path')
    generation = payload['generation']
    if type(generation) not in integer_types or not 0 <= generation < 2 ** 53:
        raise ValueError('invalid variable lock generation')
    return action, scope, path, generation


class VariableLocks(object):
    """Exact-path lock set with bounded memory and bridge-session lifetime."""

    def __init__(self):
        self.entries = []
        self._by_key = {}
        self.bytes_used = 0
        self.revision = 0
        self.last_reset_reason = 'bridge_start'

    @staticmethod
    def _key(scope, path):
        return json.dumps(
            [scope, [[kind, value] for kind, value in path]],
            ensure_ascii=True, separators=(',', ':'))

    @staticmethod
    def _size(key):
        # The snapshot retains both the canonical key and a JSON-safe path copy.
        return 2 * len(key.encode('utf-8')) + 160

    def is_locked(self, scope, path):
        return self._key(scope, path) in self._by_key

    def lock(self, scope, path, locked_at):
        key = self._key(scope, path)
        if key in self._by_key:
            return False
        size = self._size(key)
        if len(self.entries) >= MAX_VARIABLE_LOCKS or self.bytes_used + size > MAX_VARIABLE_LOCKS_BYTES:
            raise VariableLockLimit('variable lock capacity reached')
        entry = {
            'scope': scope,
            'path': [[kind, value] for kind, value in path],
            'locked_at': locked_at,
            '_key': key,
            '_size': size,
        }
        self.entries.append(entry)
        self._by_key[key] = entry
        self.bytes_used += size
        self.revision += 1
        return True

    def unlock(self, scope, path):
        key = self._key(scope, path)
        entry = self._by_key.pop(key, None)
        if entry is None:
            return False
        self.entries = [item for item in self.entries if item['_key'] != key]
        self.bytes_used -= entry['_size']
        self.revision += 1
        return True

    def reset(self, reason='game_state_changed'):
        self.entries = []
        self._by_key = {}
        self.bytes_used = 0
        self.revision += 1
        self.last_reset_reason = reason

    def snapshot(self):
        return {
            'protocol': 1,
            'revision': self.revision,
            'limit': MAX_VARIABLE_LOCKS,
            'bytes_used': self.bytes_used,
            'byte_limit': MAX_VARIABLE_LOCKS_BYTES,
            'entries': [{
                'scope': entry['scope'],
                'key': entry['_key'],
                'path': [list(segment) for segment in entry['path']],
                'locked_at': entry['locked_at'],
            } for entry in self.entries],
            'last_reset_reason': self.last_reset_reason,
        }
