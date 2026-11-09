"""Layout regression guards for both Ren'Py 7 and 8 screen variants.

These structural checks complement SDK lint. They do not replace an actual
interactive UI screenshot/smoke test.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCREEN = (ROOT / "game" / "renpy_inspector_screens.rpy").read_text(encoding="utf-8")
STYLES = (ROOT / "game" / "renpy_inspector_styles.rpy").read_text(encoding="utf-8")


class NativeUiLayoutTests(unittest.TestCase):
    def test_scrollable_tree_has_bounded_height(self):
        self.assertIn("ysize list_height", SCREEN)
        self.assertNotIn("yfill True", SCREEN)
        self.assertIn('screen renpy_inspector_tree_row(', SCREEN)
        self.assertIn("xysize (row_width, 42)", SCREEN)

    def test_footer_separate_from_scrollable_tree(self):
        self.assertIn("use renpy_inspector_footer(inspector, footer_h, inner_width)", SCREEN)
        self.assertIn("ysize footer_h", SCREEN)
        self.assertIn("screen renpy_inspector_footer(", SCREEN)

    def test_all_primary_actions_have_namespaced_styles(self):
        for style in ("renpy_inspector_nav_button", "renpy_inspector_scope_button",
                      "renpy_inspector_action_button", "renpy_inspector_icon_button",
                      "renpy_inspector_search_field", "renpy_inspector_tree_name_button"):
            self.assertIn('style "' + style + '"', SCREEN)
            self.assertIn("style " + style + " is ", STYLES)

    def test_search_and_favourites_kept(self):
        for method in ("run_search", "clear_search", "reveal_search",
                       "toggle_node", "toggle_favorite", "set_interval"):
            self.assertIn("inspector." + method, SCREEN)

    def test_poll_settings_are_not_in_footer(self):
        settings_section = SCREEN.split('elif inspector.panel == "scripts":', 1)[1].split(
            '# Fixed-height footer', 1)[0]
        footer = SCREEN.split('screen renpy_inspector_footer(', 1)[1]
        self.assertIn('text "Polling interval"', settings_section)
        self.assertIn('inspector.set_interval', settings_section)
        self.assertNotIn('inspector.set_interval', footer)
        self.assertNotIn('for ms in (0, 100, 250, 500, 1000):', footer)

    def test_tree_guides_and_explicit_pagination(self):
        self.assertIn('for level in range(guide_count):', SCREEN)
        self.assertIn('Solid("#2c4865")', SCREEN)
        self.assertIn('row.state == "more"', SCREEN)
        self.assertIn('inspector.load_more_node', SCREEN)
        self.assertIn('style "renpy_inspector_load_more_button"', SCREEN)
        self.assertIn('style renpy_inspector_load_more_button is button:', STYLES)

    def test_custom_renderer_and_classic_fallback(self):
        self.assertIn('add InspectorTreeDisplayable(row_width, list_height)', SCREEN)
        self.assertIn('inspector.tree_mode == "custom"', SCREEN)
        self.assertIn('inspector.set_tree_mode', SCREEN)
        self.assertIn('use renpy_inspector_tree_row(inspector, row, row_width)', SCREEN)
        self.assertIn('text "Polling interval"', SCREEN)

    def test_has_uniform_result_rows(self):
        self.assertIn("xysize (row_width, 48)", SCREEN)
        self.assertIn("screen renpy_inspector_match_row(", SCREEN)
        self.assertIn("screen renpy_inspector_favorite_row(", SCREEN)


if __name__ == "__main__":
    unittest.main()
