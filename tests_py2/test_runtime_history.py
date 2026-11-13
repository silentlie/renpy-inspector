# -*- coding: utf-8 -*-
"""Ren'Py 7 / Python 2-compatible timeline regression tests."""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'game'))

from renpy_inspector.runtime_history import RuntimeTimeline, MAX_RUNTIME_EVENTS


class RuntimeHistoryCompatibilityTests(unittest.TestCase):
    def test_safe_unicode_locations_and_bounded_records(self):
        history = RuntimeTimeline()
        for line in range(1, 100):
            history.observe({'filename': u'game/café.rpy', 'line': line}, 1, float(line))
        self.assertEqual(history.snapshot()['total_observed'], 99)
        self.assertEqual(len(history.snapshot()['events']), MAX_RUNTIME_EVENTS)
        self.assertEqual(history.snapshot()['events'][-1]['filename'], u'game/café.rpy')

    def test_default_notification_never_claims_a_turn(self):
        history = RuntimeTimeline()
        history.restoration('after_default', 3, 123.0)
        self.assertEqual(history.events[-1]['signal'], 'after_default')
        self.assertEqual(history.events[-1]['kind'], 'restoration')
        self.assertNotIn('turn', history.snapshot())
        history.restoration('unspecified', 4, 124.0)
        self.assertEqual(history.events[-1]['kind'], 'invalidation')


if __name__ == '__main__':
    unittest.main()
