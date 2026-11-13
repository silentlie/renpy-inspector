"""Bounded, session-only locks for explicit inspector writes.

A lock records the exact primitive fingerprint at the time it is created.
Game-side changes do not bypass or silently clear the lock: bounded game-thread
checks mark it stale, and the user must explicitly refresh or release it.
Locks never wrap Python objects, intercept game scripts, or prevent Ren'Py from
changing variables during normal gameplay.
"""
from __future__ import unicode_literals

import json

from .bridge_paging import validate_tree_request
from .compat import integer_types, text_type, to_text

MAX_VARIABLE_LOCKS = 128
MAX_VARIABLE_LOCKS_BYTES = 32 * 1024
MAX_VARIABLE_LOCK_REQUEST_BYTES = 4096
MAX_LOCK_CHECKS_PER_PUBLISH = 8
_HEX_CHARS = 'abcdef0123456789'
_EDITABLE_TYPES = ('str', 'unicode', 'int', 'long', 'float', 'bool')


class VariableLockLimit(Exception):
    """The bounded session lock set is full."""


class VariableLockMissing(Exception):
    """A refresh was requested for a path without an active lock."""


def validate_variable_lock_request(payload):
    if type(payload) is not dict or set(payload) != set((
            'action', 'scope', 'path', 'generation')):
        raise ValueError('invalid variable lock request fields')
    action = payload['action']
    if type(action) is not text_type or action not in ('lock', 'unlock', 'refresh'):
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
        self.last_event = None
        self._check_cursor = 0

    @staticmethod
    def _display_key(scope, path):
        return json.dumps(
            [scope, [[kind, value] for kind, value in path]],
            ensure_ascii=True, separators=(',', ':'))

    @staticmethod
    def _key(scope, path):
        # Python dictionaries treat True/1 and False/0 as the same key.
        # Canonicalise those aliases so a differently typed JSON path cannot
        # bypass an Inspector lock on the same underlying dictionary entry.
        canonical = []
        for kind, value in path:
            if kind == 'key' and type(value) is bool:
                value = 1 if value else 0
            canonical.append([kind, value])
        return json.dumps(
            [scope, canonical], ensure_ascii=True, separators=(',', ':'))

    @staticmethod
    def _size(key, display_key, expected, typename):
        # Account conservatively for all retained path/key copies, baseline
        # fingerprint, type and mutable status metadata.
        return (3 * max(len(key.encode('utf-8')),
                        len(display_key.encode('utf-8'))) +
                len(expected) + len(typename.encode('utf-8')) + 80)

    def _event(self, action, entry=None, reason=None, at=None):
        self.revision += 1
        event = {'action': action, 'revision': self.revision}
        if entry is not None:
            event['scope'] = entry['scope']
        if reason:
            event['reason'] = reason
        if at is not None:
            event['at'] = at
        self.last_event = event

    def is_locked(self, scope, path):
        return self._key(scope, path) in self._by_key

    def state(self, scope, path):
        entry = self._by_key.get(self._key(scope, path))
        if entry is None:
            return {'locked': False, 'stale': False, 'stale_reason': None}
        return {
            'locked': True,
            'stale': bool(entry['stale']),
            'stale_reason': entry['stale_reason'],
            'locked_at': entry['locked_at'],
            'baseline_type': entry['baseline_type'],
        }

    def lock(self, scope, path, locked_at, expected, typename):
        try:
            expected = to_text(expected)
            typename = to_text(typename)
        except (TypeError, ValueError, UnicodeError):
            raise ValueError('variable lock needs a supported primitive fingerprint')
        if (len(expected) != 64 or any(
                character not in _HEX_CHARS for character in expected)):
            raise ValueError('variable lock needs a supported primitive fingerprint')
        if typename not in _EDITABLE_TYPES:
            raise ValueError('variable lock needs a supported primitive fingerprint')
        key = self._key(scope, path)
        if key in self._by_key:
            return False
        display_key = self._display_key(scope, path)
        size = self._size(key, display_key, expected, typename)
        if len(self.entries) >= MAX_VARIABLE_LOCKS or self.bytes_used + size > MAX_VARIABLE_LOCKS_BYTES:
            raise VariableLockLimit('variable lock capacity reached')
        entry = {
            'scope': scope,
            'path': [[kind, value] for kind, value in path],
            'locked_at': locked_at,
            'baseline_expected': expected,
            'baseline_type': typename,
            'stale': False,
            'stale_reason': None,
            'stale_at': None,
            '_key': key,
            '_display_key': display_key,
            '_size': size,
        }
        self.entries.append(entry)
        self._by_key[key] = entry
        self.bytes_used += size
        self._event('locked', entry, at=locked_at)
        return True

    def observe(self, scope, path, target, observed_at):
        """Mark an active lock stale when a game-side value/type/path changes.

        Staleness is sticky until an explicit refresh or unlock. This avoids
        silently removing protection merely because gameplay assigned a value.
        """
        entry = self._by_key.get(self._key(scope, path))
        if entry is None:
            return {'locked': False, 'stale': False, 'stale_reason': None}
        if not entry['stale']:
            reason = None
            if not target or not target.get('editable'):
                reason = 'target_unavailable'
            elif target.get('type') != entry['baseline_type']:
                reason = 'type_changed'
            elif target.get('expected') != entry['baseline_expected']:
                reason = 'value_changed'
            if reason:
                entry['stale'] = True
                entry['stale_reason'] = reason
                entry['stale_at'] = observed_at
                self._event('stale', entry, reason=reason, at=observed_at)
        return self.state(scope, path)

    def next_check_batch(self, limit=MAX_LOCK_CHECKS_PER_PUBLISH):
        """Return a rotating, bounded set of non-stale paths for background checks."""
        if not self.entries or limit <= 0:
            self._check_cursor = 0
            return []
        count = len(self.entries)
        cursor = self._check_cursor % count
        result = []
        scanned = 0
        while scanned < count and len(result) < limit:
            entry = self.entries[(cursor + scanned) % count]
            scanned += 1
            if not entry['stale']:
                result.append((entry['scope'], tuple(
                    (segment[0], segment[1]) for segment in entry['path'])))
        self._check_cursor = (cursor + scanned) % count
        return result

    def refresh(self, scope, path, refreshed_at, expected, typename):
        """Rebase an existing stale or current lock to the inspected primitive."""
        entry = self._by_key.get(self._key(scope, path))
        if entry is None:
            raise VariableLockMissing('No active lock exists for this path')
        try:
            expected = to_text(expected)
            typename = to_text(typename)
        except (TypeError, ValueError, UnicodeError):
            raise ValueError('variable lock needs a supported primitive fingerprint')
        if (len(expected) != 64 or any(
                character not in _HEX_CHARS for character in expected)):
            raise ValueError('variable lock needs a supported primitive fingerprint')
        if typename not in _EDITABLE_TYPES:
            raise ValueError('variable lock needs a supported primitive fingerprint')
        new_size = self._size(
            entry['_key'], entry['_display_key'], expected, typename)
        delta = new_size - entry['_size']
        if self.bytes_used + delta > MAX_VARIABLE_LOCKS_BYTES:
            raise VariableLockLimit('variable lock capacity reached')
        self.bytes_used += delta
        entry['_size'] = new_size
        entry['baseline_expected'] = expected
        entry['baseline_type'] = typename
        entry['stale'] = False
        entry['stale_reason'] = None
        entry['stale_at'] = None
        self._event('refreshed', entry, at=refreshed_at)
        return True

    def unlock(self, scope, path, unlocked_at=None):
        key = self._key(scope, path)
        entry = self._by_key.pop(key, None)
        if entry is None:
            return False
        self.entries = [item for item in self.entries if item['_key'] != key]
        self.bytes_used -= entry['_size']
        if self._check_cursor >= len(self.entries):
            self._check_cursor = 0
        self._event('unlocked', entry, at=unlocked_at)
        return True

    def reset(self, reason='game_state_changed'):
        self.entries = []
        self._by_key = {}
        self.bytes_used = 0
        self._check_cursor = 0
        self.revision += 1
        self.last_reset_reason = reason
        self.last_event = {'action': 'reset', 'reason': reason,
                           'revision': self.revision}

    def snapshot(self):
        return {
            'protocol': 2,
            'revision': self.revision,
            'limit': MAX_VARIABLE_LOCKS,
            'bytes_used': self.bytes_used,
            'byte_limit': MAX_VARIABLE_LOCKS_BYTES,
            'entries': [{
                'scope': entry['scope'],
                'key': entry['_display_key'],
                'path': [list(segment) for segment in entry['path']],
                'locked_at': entry['locked_at'],
                'baseline_type': entry['baseline_type'],
                'stale': bool(entry['stale']),
                'stale_reason': entry['stale_reason'],
                'stale_at': entry['stale_at'],
            } for entry in self.entries],
            'last_event': self.last_event,
            'last_reset_reason': self.last_reset_reason,
        }
