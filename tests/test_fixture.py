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
            self.assertFalse((result / 'game' / 'renpy_inspector' / '__pycache__').exists())
            with self.assertRaises(ValueError):
                prepare_fixture(result)
