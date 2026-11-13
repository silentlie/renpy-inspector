"""PR #27: evidence-labelled runtime timeline, read-only and generation-safe."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.runtime_history import RuntimeTimeline, MAX_RUNTIME_EVENTS
from renpy_inspector.runtime import collect_context
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class Explosive:
    def __str__(self):
        raise AssertionError('must not stringify untrusted game objects')

    def __repr__(self):
        raise AssertionError('must not repr untrusted game objects')


class TimelineTests(unittest.TestCase):
    def test_deduplicates_samples_and_retains_bounded_newest_entries(self):
        history = RuntimeTimeline()
        context = {'filename': 'game/script.rpy', 'line': 10, 'return_depth': 3}
        history.observe(context, 0, 100.0)
        history.observe(context, 0, 101.0)
        self.assertEqual(len(history.events), 1)
        for number in range(1, 90):
            history.observe({'filename': 'game/script.rpy', 'line': number}, 0, 101.0 + number)
        self.assertEqual(len(history.snapshot()['events']), MAX_RUNTIME_EVENTS)
        self.assertEqual(history.snapshot()['total_observed'], 90)
        self.assertEqual(history.snapshot()['events'][-1]['line'], 89)

    def test_restoration_is_a_signal_not_an_asserted_rollback(self):
        history = RuntimeTimeline()
        history.observe({'filename': 'a.rpy', 'line': 3}, 1, 20.0)
        history.restoration('after_default', 2, 21.0)
        history.observe({'filename': 'a.rpy', 'line': 3}, 2, 22.0)
        self.assertEqual([event['kind'] for event in history.events],
                         ['location', 'restoration', 'location'])
        self.assertEqual(history.events[1]['signal'], 'after_default')
        self.assertEqual(history.events[1]['generation'], 2)
        self.assertNotIn('turn', history.snapshot())

    def test_rollback_flag_only_records_observed_true_transition(self):
        history = RuntimeTimeline()
        for flag in (False, True, True, False, True):
            history.observe({'rollback_active': flag}, 1, 1.0)
        self.assertEqual([event['kind'] for event in history.events],
                         ['rollback_flag', 'rollback_flag'])

    def test_untrusted_context_is_ignored(self):
        history = RuntimeTimeline()
        history.observe({'filename': Explosive(), 'line': Explosive(),
                         'rollback_active': Explosive()}, 0, 1.0)
        self.assertEqual(history.events, [])
        history.observe({'filename': 'f.rpy', 'line': 2**200}, 0, 1.0)
        self.assertEqual(history.events, [])
        history.restoration('not a callback', 1, 2.0)
        self.assertEqual(history.events[-1]['signal'], 'unspecified')
        self.assertEqual(history.events[-1]['kind'], 'invalidation')

    def test_runtime_collects_optional_public_indicator(self):
        class Engine:
            def get_filename_line(self):
                return ('script.rpy', 9)
            def get_return_stack(self):
                return []
            def in_rollback(self):
                return True
        result = collect_context(Engine(), type('Config', (), {})())
        self.assertTrue(result['rollback_active'])


class BridgeTimelineTests(unittest.TestCase):
    def test_bridge_exposes_history_without_new_http_api(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'index.html').write_text('local', encoding='utf-8')
            store = ModuleType('store')
            store.score = 1
            location = {'line': 3}
            inspector = Inspector()
            inspector.bind(lambda: store, lambda: {},
                           context_provider=lambda: {'filename': 'game/a.rpy',
                                                     'line': location['line'],
                                                     'rollback_active': False})
            bridge = InspectorBridge(inspector, directory)
            bridge.start()
            try:
                first = json.loads(bridge.cached_bytes)
                self.assertEqual(first['runtime']['events'][-1]['kind'], 'location')
                location['line'] = 4
                bridge.publish()
                self.assertEqual(len(json.loads(bridge.cached_bytes)['runtime']['events']), 2)
                bridge.invalidate('after_default')
                reset = json.loads(bridge.cached_bytes)
                self.assertIsNone(reset['captured_at'])
                self.assertEqual(reset['runtime']['events'][-1]['signal'], 'after_default')
                self.assertEqual(reset['generation'], 1)
                self.assertEqual(reset['scopes']['store'], [])
                bridge.publish()
                current = json.loads(bridge.cached_bytes)
                self.assertEqual([x['kind'] for x in current['runtime']['events'][-2:]],
                                 ['restoration', 'location'])
            finally:
                bridge.stop()


if __name__ == '__main__':
    unittest.main()
