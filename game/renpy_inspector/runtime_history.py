"""Bounded, evidence-labelled runtime observations, never SugarCube turns.

Only called from the Ren'Py interaction thread. This records public engine
context and callback signals, not dialogue events, rollback destinations,
mutation causes or values from the game's stores. No disk persistence.
"""
from __future__ import unicode_literals

from .compat import string_types, integer_types

MAX_RUNTIME_EVENTS = 64
MAX_LOCATION_TEXT = 180
RESTORE_SIGNALS = ('after_load', 'after_default', 'legacy_rollback', 'unspecified', 'edit')


def _safe_filename(value):
    # Exact built-in strings only; never call game-defined __str__/__repr__.
    if type(value) not in string_types:
        return None
    try:
        if isinstance(value, bytes) and not isinstance(value, type(u'')):
            value = value.decode('utf-8')
        return value[:MAX_LOCATION_TEXT]
    except (UnicodeError, TypeError, ValueError):
        return None


def _safe_line(value):
    if type(value) in integer_types and 0 < value < 10000000:
        return int(value)
    return None


class RuntimeTimeline(object):
    """Per-bridge-session FIFO, with monotonic IDs and observed-only semantics."""

    def __init__(self):
        self.events = []
        self.total = 0
        self.last_location = None
        self.last_rollback = None

    def _append(self, kind, generation, captured_at, **details):
        self.total += 1
        event = {'id': self.total, 'kind': kind, 'generation': generation,
                 'captured_at': captured_at}
        event.update(details)
        self.events.append(event)
        if len(self.events) > MAX_RUNTIME_EVENTS:
            del self.events[:-MAX_RUNTIME_EVENTS]

    def restoration(self, signal, generation, captured_at):
        # A default callback is NOT proof of rollback. It also runs during
        # startup and following a save load on supported Ren'Py versions.
        if signal not in RESTORE_SIGNALS:
            signal = 'unspecified'
        self.last_location = None
        self.last_rollback = None
        # Cache-only invalidations are not Ren'Py restoration callbacks.
        kind = 'invalidation' if signal in ('unspecified', 'edit') else 'restoration'
        self._append(kind, generation, captured_at, signal=signal)

    def observe(self, context, generation, captured_at):
        if not isinstance(context, dict):
            return
        filename = _safe_filename(context.get('filename'))
        line = _safe_line(context.get('line'))
        depth = _safe_line(context.get('return_depth'))
        if filename and line is not None:
            signature = (filename, line, depth)
            if signature != self.last_location:
                self._append('location', generation, captured_at, filename=filename,
                             line=line, return_depth=depth)
                self.last_location = signature

        indicator = context.get('rollback_active')
        if type(indicator) is bool:
            if indicator and self.last_rollback is not True:
                self._append('rollback_flag', generation, captured_at)
            self.last_rollback = indicator

    def snapshot(self):
        return {'limit': MAX_RUNTIME_EVENTS, 'total_observed': self.total,
                'events': [dict(event) for event in self.events]}
