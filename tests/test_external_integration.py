"""Static integration guards complement Ren'Py SDK lint; no game UI is rendered."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = (ROOT / 'game' / 'renpy_inspector_screens.rpy').read_text(encoding='utf-8')
INIT = (ROOT / 'game' / 'renpy_inspector.rpy').read_text(encoding='utf-8')
PACKAGE = (ROOT / 'game' / 'renpy_inspector' / '__init__.py').read_text(encoding='utf-8')


class ExternalUiIntegrationTests(unittest.TestCase):
    def test_f8_starts_browser_and_keeps_polling_without_native_gui(self):
        self.assertIn('key "K_F8" action Function(renpy_inspector_open_external)', SCREEN)
        self.assertIn('renpy_inspector.bridge.launch_or_open()', INIT)
        self.assertIn('if renpy_inspector.bridge.running:', SCREEN)
        self.assertIn('Function(renpy_inspector.bridge.tick, _update_screens=False)', SCREEN)
        self.assertNotIn('renpy_inspector_drawer', SCREEN)
        self.assertNotIn('textbutton', SCREEN)

    def test_state_invalidation_after_game_load(self):
        self.assertIn('renpy_inspector.reset_lifecycle', INIT)
        self.assertIn('defaults_callbacks.append(renpy_inspector.reset_lifecycle)', INIT)
        self.assertIn('renpy_inspector.observe_legacy_rollback', INIT)
        self.assertIn('bridge.invalidate()', PACKAGE)
        self.assertIn('bridge = InspectorBridge(inspector)', PACKAGE)

    def test_no_external_autostart(self):
        self.assertNotIn('renpy_inspector.bridge.start(', INIT)
        self.assertNotIn('bridge.start()', PACKAGE)


if __name__ == '__main__':
    unittest.main()
