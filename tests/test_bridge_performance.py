"""Read-only queue diagnostics and reproducible synthetic benchmark coverage."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.bridge_snapshot import MAX_JSON_BYTES
from renpy_inspector.controller import Inspector
from scripts.benchmark_bridge import run_benchmark


class BridgePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, 'index.html').write_text('ok', encoding='utf-8')
        store = ModuleType('store')
        store.answer = 10
        inspector = Inspector()
        inspector.bind(lambda: store, lambda: {})
        self.bridge = InspectorBridge(inspector, self.tmp.name)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)

    def test_queue_stays_bounded_and_reports_game_thread_observations(self):
        jobs = [self.bridge.enqueue_tree_page(('store', (), 0, 1))
                for _ in range(8)]
        self.assertTrue(all(jobs))
        self.assertIsNone(self.bridge.enqueue_tree_page(('store', (), 0, 1)))
        self.assertEqual(len(self.bridge.pending_pages), 8)
        self.assertEqual(self.bridge.queue_peak, 8)
        self.assertEqual(self.bridge.queue_rejected, 1)
        self.bridge.last_publish = float('-inf')
        self.bridge.tick()
        self.assertTrue(all(job['event'].is_set() for job in jobs[:2]))
        self.assertFalse(jobs[2]['event'].is_set())
        snap = json.loads(self.bridge.cached_bytes)
        metrics = snap['diagnostics']
        self.assertEqual(metrics['queue_pending'], 6)
        self.assertEqual(metrics['queue_capacity'], 8)
        self.assertEqual(metrics['queue_peak'], 8)
        self.assertEqual(metrics['queue_rejected'], 1)
        self.assertEqual(metrics['requests_completed'], 2)
        self.assertGreaterEqual(metrics['root_scan_ms'], 0)
        self.assertGreaterEqual(metrics['last_request_ms'], 0)
        self.assertGreaterEqual(metrics['last_queue_wait_ms'], 0)
        self.assertNotIn('token', metrics)
        self.assertLess(len(self.bridge.cached_bytes), MAX_JSON_BYTES)

    def test_restore_resets_diagnostics_without_reviving_old_jobs(self):
        self.bridge.enqueue_tree_page(('store', (), 0, 1))
        self.bridge.enqueue_tree_page(('store', (), 0, 1))
        waiting = self.bridge.enqueue_tree_page(('store', (), 0, 1))
        self.bridge.tick()
        self.assertFalse(waiting['event'].is_set())
        self.bridge.invalidate()
        self.assertEqual(waiting['response'][0], 409)
        self.assertEqual(self.bridge.queue_peak, 0)
        self.assertEqual(self.bridge.requests_completed, 0)
        self.bridge.tick()
        diagnostics = json.loads(self.bridge.cached_bytes)['diagnostics']
        self.assertEqual(diagnostics['requests_completed'], 0)
        self.assertEqual(diagnostics['queue_pending'], 0)


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_microbenchmark_reports_measured_and_bounded_responses(self):
        report = run_benchmark(iterations=3, warmup=0)
        self.assertEqual(report['kind'], 'synthetic_bridge_microbenchmark')
        self.assertEqual([case['operation'] for case in report['cases']],
                         ['root_scan', 'expanded_page', 'favourite_value'])
        for case in report['cases']:
            self.assertEqual(case['samples'], 3)
            self.assertLess(case['max_response_bytes'], MAX_JSON_BYTES)
            self.assertGreaterEqual(case['max_ms'], case['median_ms'])
            self.assertGreaterEqual(case['p95_ms'], 0)
        self.assertIn('No RenPy renderer', report['limitations'])


if __name__ == '__main__':
    unittest.main()
