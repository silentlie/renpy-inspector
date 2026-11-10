import tempfile
import unittest
from pathlib import Path
from scripts.prepare_fixture import prepare_fixture


class EngineFixtureTests(unittest.TestCase):
    def test_fixture_contains_game_and_mod(self):
        with tempfile.TemporaryDirectory() as temp:
            result = prepare_fixture(Path(temp) / 'fixture')
            self.assertTrue((result / 'game' / 'script.rpy').is_file())
            self.assertTrue((result / 'game' / 'renpy_inspector.rpy').is_file())
            self.assertTrue((result / 'game' / 'renpy_inspector' / 'favorites.py').is_file())
            self.assertTrue((result / 'game' / 'renpy_inspector' / 'search.py').is_file())
            self.assertTrue((result / 'game' / 'renpy_inspector' / 'runtime.py').is_file())
            self.assertIn('characters.affection', (result / 'game' / 'script.rpy').read_text())
            self.assertFalse((result / 'game' / 'renpy_inspector' / '__pycache__').exists())
            with self.assertRaises(ValueError):
                prepare_fixture(result)

    def test_f8_only_screen_does_not_render_game_gui(self):
        source = (Path(__file__).resolve().parents[1] / 'game' /
                  'renpy_inspector_screens.rpy').read_text(encoding='utf-8')
        self.assertIn('key "K_F8" action Function(renpy_inspector_open_external)', source)
        self.assertNotIn('textbutton', source)
        self.assertNotIn('renpy_inspector_drawer', source)

    def test_game_python_is_safe_for_renpy7_unicode_loader(self):
        package = Path(__file__).resolve().parents[1] / 'game' / 'renpy_inspector'
        for path in package.glob('*.py'):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                self.assertTrue(raw.isascii())
                self.assertNotIn(b'coding:', raw)
