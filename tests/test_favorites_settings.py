"""Independent-watch, persistence, rollback and settings safety regressions."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.controller import Inspector
from renpy_inspector.favorites import decode_location, encode_location, format_location
from renpy_inspector.settings import SettingsStore


SCORE_PATH = (('attribute', 'player'), ('key', 'stats'), ('key', 'hp'))


class LocationTests(unittest.TestCase):
    def test_roundtrip_typed_paths(self):
        for kind, key in [('key', 'x'), ('key', -18), ('key', False), ('key', None), ('index', 5), ('attribute', 'foo')]:
            path = (('attribute', 'player'), (kind, key))
            self.assertEqual(decode_location(encode_location('store', path)), ('store', path))

    def test_rejects_unsafe_segments(self):
        bad = [(), (('index', -1),), (('index', True),), (('attribute', ''),),
               (('key', object()),), (('key', 1.5),), (('attribute', 'x' * 300),)]
        for path in bad:
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                encode_location('store', path)
        with self.assertRaises(ValueError):
            encode_location('arbitrary', (('attribute', 'x'),))
        for tag, val in [('bool', 1), ('int', True), ('str', 4), ('none', False), ('obj', 'x')]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                decode_location({'root': 'store', 'segments': [{'kind':'key', 'key':{'type':tag, 'value':val}}]})

    def test_format_path(self):
        self.assertEqual(format_location('persistent', (('attribute', 'unlocked'),)),
                         'persistent.unlocked')
        self.assertEqual(format_location('store', SCORE_PATH), "store.player['stats']['hp']")


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = SettingsStore(self.temp.name)

    def test_defaults_and_roundtrip(self):
        self.assertEqual(self.settings.load()['interval_ms'], 250)
        self.settings.save(interval_ms=0, drawer_width=620,
                           favorites=[('store', SCORE_PATH)])
        self.assertEqual(self.settings.load(), {
            'interval_ms': 0, 'drawer_width': 620,
            'favorites': [('store', SCORE_PATH)], 'scope': 'store'})
        contents = self.settings.path.read_text()
        self.assertNotIn('SimpleNamespace', contents)
        self.assertIn('"version":1', contents)

    def test_malformed_file_and_invalid_entries(self):
        self.settings.path.write_text('{oops', encoding='utf-8')
        self.assertEqual(self.settings.load()['favorites'], [])
        payload = {'version': 1, 'interval_ms': True, 'drawer_width': 12000,
                   'favorites': [encode_location('store', SCORE_PATH),
                                 {'root':'other', 'segments':[]} ,
                                 encode_location('store', SCORE_PATH)]}
        self.settings.path.write_text(json.dumps(payload), encoding='utf-8')
        loaded = self.settings.load()
        self.assertEqual(loaded['interval_ms'], 250)
        self.assertEqual(loaded['drawer_width'], 460)
        self.assertEqual(loaded['favorites'], [('store', SCORE_PATH)])

    def test_oversize_settings_is_not_loaded(self):
        self.settings.path.write_text(' ' * (128 * 1024 + 1))
        self.assertEqual(self.settings.load()['favorites'], [])

    def test_invalid_save_does_not_corrupt_existing_settings(self):
        self.settings.save(interval_ms=250, drawer_width=460, favorites=[])
        original = self.settings.path.read_bytes()
        with self.assertRaises(ValueError):
            self.settings.save(interval_ms=True, drawer_width=460, favorites=[])
        self.assertEqual(self.settings.path.read_bytes(), original)


class FavouriteWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = {'root': SimpleNamespace(player={'stats': {'hp': 10}, 'items': ['key']})}
        self.persistent = {'root': SimpleNamespace(unlocked=False)}
        self.calls = []
        self.settings = SettingsStore(self.temp.name)
        self.inspector = Inspector(on_change=lambda: self.calls.append('refresh'))
        self.inspector.bind(lambda: self.store['root'], lambda: self.persistent['root'], self.settings)
        self.inspector.open()

    def test_pin_nested_and_watch_off_scope(self):
        i = self.inspector
        i.toggle_favorite('store', SCORE_PATH)
        self.assertEqual(i.favorite_rows[0].preview, '10')
        i.set_scope('persistent')
        self.store['root'].player['stats']['hp'] = 8
        i.tick()
        self.assertEqual(i.favorite_rows[0].preview, '8')
        self.assertEqual(len(self.calls), 1)
        i.tick()
        self.assertEqual(len(self.calls), 1)
        i.set_scope('favorites')
        self.assertEqual(len(i.favorite_rows), 1)

    def test_missing_path_survives_then_reconnects(self):
        i = self.inspector
        i.toggle_favorite('store', SCORE_PATH)
        self.store['root'].player = {}
        i.tick()
        self.assertEqual(i.favorite_rows[0].state, 'missing')
        self.store['root'].player = {'stats': {'hp': 42}}
        i.tick()
        self.assertEqual(i.favorite_rows[0].preview, '42')

    def test_replaced_ancestor_and_simulated_save_load_rollback(self):
        i = self.inspector
        i.toggle_favorite('store', SCORE_PATH)
        self.store['root'] = SimpleNamespace(player={'stats': {'hp': 99}})
        i.reset()  # after-load callback
        i.refresh()
        self.assertEqual(i.favorite_rows[0].preview, '99')
        self.store['root'] = SimpleNamespace(player={'stats': {'hp': 10}})
        i.tick()  # rollback or new-game interaction, resolves current root
        self.assertEqual(i.favorite_rows[0].preview, '10')

    def test_settings_survive_restart_and_remove(self):
        i = self.inspector
        i.toggle_favorite('store', SCORE_PATH)
        i.set_interval(0)
        i.set_width(620)
        i.close()
        new = Inspector()
        new.bind(lambda: self.store['root'], lambda: self.persistent['root'],
                 SettingsStore(self.temp.name))
        self.assertEqual(new.favorites, [('store', SCORE_PATH)])
        self.assertEqual((new.interval_ms, new.drawer_width), (0, 620))
        new.open()
        self.assertEqual(new.favorite_rows[0].preview, '10')
        new.toggle_favorite('store', SCORE_PATH)
        self.assertEqual(SettingsStore(self.temp.name).load()['favorites'], [])

    def test_hidden_and_manual_modes_do_not_poll(self):
        i = self.inspector
        i.toggle_favorite('store', SCORE_PATH)
        i.set_interval(0)
        self.store['root'].player['stats']['hp'] = 4
        i.tick()
        self.assertEqual(i.favorite_rows[0].preview, '10')
        i.refresh()
        self.assertEqual(i.favorite_rows[0].preview, '4')
        i.set_interval(250)
        i.close()
        self.store['root'].player['stats']['hp'] = 3
        i.tick()
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(i.favorite_rows, ())
        i.open()
        self.assertEqual(i.favorite_rows[0].preview, '3')

    def test_pin_ui_disables_invalid_long_paths(self):
        i = self.inspector
        self.store['root'].player = {'x' * 300: 12}
        i.refresh()
        i.toggle_node((('attribute', 'player'),))
        self.assertFalse(i.rows[1].pinnable)

    def test_visible_tree_pin_marker(self):
        i = self.inspector
        i.toggle_favorite('store', (('attribute', 'player'),))
        self.assertTrue(i.rows[0].favorite)
        i.toggle_favorite('store', (('attribute', 'player'),))
        self.assertFalse(i.rows[0].favorite)

    def test_faulty_favourite_does_not_block_others(self):
        i = self.inspector
        i.toggle_favorite('store', SCORE_PATH)
        i.toggle_favorite('persistent', (('attribute', 'unlocked'),))
        self.store['root'] = None
        i.tick()
        self.assertEqual(i.favorite_rows[0].state, 'missing')
        self.assertEqual(i.favorite_rows[1].preview, 'False')

    def test_write_error_does_not_break_gameplay(self):
        class Denied:
            def load(self):
                return {'interval_ms':250, 'drawer_width':460, 'favorites':[]}
            def save(self, **kwargs):
                raise PermissionError('read only')
        i = Inspector()
        i.bind(lambda: self.store['root'], lambda: self.persistent['root'], Denied())
        i.open()
        i.set_width(500)
        self.assertEqual(i.drawer_width, 500)
        self.assertIn('not saved', i.settings_error)


if __name__ == '__main__':
    unittest.main()
