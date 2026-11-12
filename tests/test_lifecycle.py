"""Restore/rollback safety for the read-only browser bridge."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

import renpy_inspector
from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, 'index.html').write_text('local', encoding='utf-8')
        self.store = ModuleType('store')
        self.store.answer = 10
        self.inspector = Inspector()
        self.inspector.bind(lambda: self.store, lambda: {})
        self.bridge = InspectorBridge(self.inspector, self.tmp.name)
        self.bridge.start()
        self.assertTrue(self.bridge.running)
        self.addCleanup(self.bridge.stop)

    def test_restore_rejects_pending_jobs_and_publishes_immediately(self):
        old_generation = self.bridge.generation
        self.store.answer = 20
        self.bridge.last_publish = 10 ** 15  # next tick would otherwise skip capture
        job = self.bridge.enqueue_tree_page(('store', (), 0, 1))
        self.assertIsNotNone(job)
        self.inspector.reset()
        self.bridge.invalidate()
        self.assertTrue(job['event'].is_set())
        self.assertEqual(job['response'][0], 409)
        self.assertEqual(self.bridge.pending_pages, [])
        self.assertEqual(self.bridge.generation, old_generation + 1)
        self.assertEqual(json.loads(self.bridge.cached_bytes)['captured_at'], None)
        self.assertEqual(self.bridge.last_publish, 0)
        self.bridge.tick()
        updated = json.loads(self.bridge.cached_bytes)
        self.assertEqual(updated['generation'], old_generation + 1)
        self.assertEqual(updated['scopes']['store'][0]['preview'], '20')

    def test_one_callback_clears_browser_bridge_cache_and_preserves_pins(self):
        self.inspector.favorites = ['a persisted path']
        self.inspector.rows = ('stale',)
        self.store.answer = 99
        with patch.object(renpy_inspector, 'inspector', self.inspector), patch.object(
                renpy_inspector, 'bridge', self.bridge):
            renpy_inspector.reset_lifecycle()
        self.assertEqual(self.inspector.rows, ())
        self.assertEqual(self.inspector.favorites, ['a persisted path'])
        self.assertIsNone(json.loads(self.bridge.cached_bytes)['captured_at'])
        self.bridge.tick()
        self.assertEqual(json.loads(self.bridge.cached_bytes)['scopes']['store'][0]['preview'], '99')

    def test_integration_registers_both_load_and_rollback_safe_hooks(self):
        script = Path(__file__).resolve().parents[1] / 'game' / 'renpy_inspector.rpy'
        content = script.read_text(encoding='utf-8')
        self.assertIn('config.after_load_callbacks.append(renpy_inspector.reset_lifecycle)', content)
        self.assertIn('defaults_callbacks.append(renpy_inspector.reset_lifecycle)', content)
        self.assertNotIn('config.after_load_callbacks.append(renpy_inspector.bridge.invalidate)', content)


if __name__ == '__main__':
    unittest.main()
