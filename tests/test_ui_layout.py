"""F8-only native integration: no in-game inspector GUI is rendered."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = (ROOT / "game" / "renpy_inspector_screens.rpy").read_text(encoding="utf-8")
STYLES = (ROOT / "game" / "renpy_inspector_styles.rpy").read_text(encoding="utf-8")
ENTRYPOINT = (ROOT / "game" / "renpy_inspector.rpy").read_text(encoding="utf-8")


class ExternalOnlyUiLayoutTests(unittest.TestCase):
    def test_f8_is_only_native_user_action(self):
        self.assertEqual(SCREEN.count('key "K_F8"'), 1)
        self.assertIn('Function(renpy_inspector_open_external)', SCREEN)
        self.assertIn('renpy_inspector.bridge.launch_or_open()', ENTRYPOINT)

    def test_snapshot_timer_survives_removing_native_drawer(self):
        self.assertIn('if renpy_inspector.bridge.running:', SCREEN)
        self.assertIn('timer 1.5 repeat True', SCREEN)
        self.assertIn('Function(renpy_inspector.bridge.publish, _update_screens=False)', SCREEN)

    def test_no_native_inspector_interface(self):
        for forbidden in ('textbutton', 'frame:', 'hbox:', 'vbox:', 'viewport:',
                          'vpgrid:', 'input:', 'use renpy_inspector_drawer',
                          'screen renpy_inspector_drawer', 'style renpy_inspector_'):
            self.assertNotIn(forbidden, SCREEN)
        self.assertNotIn('style renpy_inspector_', STYLES)

    def test_server_not_started_during_init(self):
        self.assertIn('renpy_inspector.bridge.configure_game_directory(config.gamedir)', ENTRYPOINT)
        bootstrap = ENTRYPOINT.split('init -99 python:', 1)[0]
        self.assertNotIn('renpy_inspector.bridge.start()', bootstrap)


if __name__ == "__main__":
    unittest.main()
