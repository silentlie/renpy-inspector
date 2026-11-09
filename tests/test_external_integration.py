"""Static wiring checks for the optional external inspector and fallback."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExternalIntegrationTests(unittest.TestCase):
    def test_bridge_initialized_without_starting_network(self):
        source = (ROOT / 'game/renpy_inspector/__init__.py').read_text(encoding='utf-8')
        self.assertIn('bridge = InspectorBridge(inspector)', source)
        self.assertNotIn('bridge.start()', source)

    def test_overlay_samples_in_interaction_thread(self):
        screen = (ROOT / 'game/renpy_inspector_screens.rpy').read_text(encoding='utf-8')
        self.assertIn('if renpy_inspector.bridge.running:', screen)
        self.assertIn('Function(renpy_inspector.bridge.publish', screen)
        self.assertIn('Start local server', screen)
        self.assertIn('Open external window', screen)
        self.assertIn('Stop server', screen)
        self.assertIn('renpy_inspector_drawer', screen)

    def test_after_load_clears_bridge_snapshot(self):
        source = (ROOT / 'game/renpy_inspector.rpy').read_text(encoding='utf-8')
        self.assertIn('config.after_load_callbacks.append(renpy_inspector.bridge.invalidate)', source)


if __name__ == '__main__':
    unittest.main()
