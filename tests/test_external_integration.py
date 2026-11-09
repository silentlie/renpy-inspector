"""Static integration guards complement Ren'Py SDK lint; no game UI is rendered."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = (ROOT / 'game' / 'renpy_inspector_screens.rpy').read_text(encoding='utf-8')
INIT = (ROOT / 'game' / 'renpy_inspector.rpy').read_text(encoding='utf-8')
PACKAGE = (ROOT / 'game' / 'renpy_inspector' / '__init__.py').read_text(encoding='utf-8')


class ExternalUiIntegrationTests(unittest.TestCase):
    def test_opt_in_game_screen(self):
        self.assertIn('Function(renpy_inspector.bridge.start)', SCREEN)
        self.assertIn('Function(renpy_inspector.bridge.stop)', SCREEN)
        self.assertIn('Function(renpy_inspector.bridge.open_browser)', SCREEN)
        self.assertIn('if renpy_inspector.bridge.running:', SCREEN)
        self.assertIn('Function(renpy_inspector.bridge.publish, _update_screens=False)', SCREEN)

    def test_state_invalidation_after_game_load(self):
        self.assertIn('renpy_inspector.bridge.invalidate', INIT)
        self.assertIn('bridge = InspectorBridge(inspector)', PACKAGE)

    def test_no_external_autostart(self):
        self.assertNotIn('renpy_inspector.bridge.start(', INIT)
        self.assertNotIn('bridge.start()', PACKAGE)


if __name__ == '__main__':
    unittest.main()
