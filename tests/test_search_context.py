"""Search, named stores, context and lifecycle regression tests."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.controller import Inspector
from renpy_inspector.favorites import decode_location, encode_location
from renpy_inspector.runtime import collect_context
from renpy_inspector.search import search_tree, MAX_SEARCH_MATCHES, MAX_SEARCH_VISITS
from renpy_inspector.settings import SettingsStore


class Explosive:
    def __init__(self):
        self.health = 9

    @property
    def risky(self):
        raise AssertionError('must not call a descriptor')

    def __repr__(self):
        raise AssertionError('must not call repr')


class SearchTests(unittest.TestCase):
    def test_search_nested_without_expanding_tree(self):
        root = SimpleNamespace(player={'stats': {'health': 50}, 'hp': 30})
        result = search_tree(root, 'store', 'health')
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].path, (
            ('attribute', 'player'), ('key', 'stats'), ('key', 'health')))
        self.assertEqual(result.matches[0].preview, '50')

    def test_dangerous_getter_and_repr_not_invoked(self):
        result = search_tree(SimpleNamespace(test=Explosive()), 'store', 'health')
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.errors, 0)

    def test_cycles_not_recursed(self):
        value = {}
        value['self'] = value
        value['health'] = 99
        result = search_tree(SimpleNamespace(value=value), 'store', 'health')
        self.assertEqual(len(result.matches), 1)
        self.assertLessEqual(result.visited, 4)

    def test_bounded_scan(self):
        root = SimpleNamespace(a=list(range(10000)))
        result = search_tree(root, 'store', 'absent', max_visits=30)
        self.assertLessEqual(result.visited, 30)
        self.assertTrue(result.truncated)

    def test_result_cap(self):
        result = search_tree(SimpleNamespace(items={f'health{i}': i for i in range(200)}),
                             'store', 'health')
        self.assertEqual(len(result.matches), MAX_SEARCH_MATCHES)
        self.assertTrue(result.truncated)
        self.assertLessEqual(result.visited, MAX_SEARCH_VISITS)

    def test_input_validation_and_text_escaping(self):
        result = search_tree(SimpleNamespace(data={'{health}': '[danger]'}), 'store', 'health')
        self.assertEqual(len(result.matches), 1)
        self.assertIn('{{', result.matches[0].label)
        self.assertIn('[[', result.matches[0].preview)
        self.assertEqual(search_tree({}, 'store', ' ' * 4).visited, 0)
        with self.assertRaises(ValueError):
            search_tree({}, 'store', 3)


class InspectorPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = SettingsStore(self.tmp.name)
        self.root = ModuleType('store')
        self.root.player = {'stats': {'health': 12}}
        self.named = ModuleType('store.characters')
        self.named.affection = {'alice': 7}
        self.root.characters = self.named
        self.inspector = Inspector()
        self.inspector.bind(lambda: self.root, lambda: SimpleNamespace(), self.settings,
                            context_provider=lambda: {'game': 'Fixture', 'version': '8.5',
                                                      'filename': 'game/script.rpy', 'line': 15,
                                                      'return_depth': 2, 'return_labels': 'start'})
        self.inspector.open()

    def test_discovery_selection_and_persisted_scope(self):
        inspector = self.inspector
        self.assertIn('named:characters', inspector.named_scope_options)
        inspector.set_scope('named:characters')
        self.assertIn('affection', [row.label for row in inspector.rows])
        inspector.close()
        second = Inspector()
        second.bind(lambda: self.root, lambda: SimpleNamespace(), self.settings)
        self.assertEqual(second.scope, 'named:characters')
        second.open()
        self.assertEqual(second.rows[0].label, 'affection')

    def test_named_favorite_survives_replacement_and_restart(self):
        inspector = self.inspector
        inspector.set_scope('named:characters')
        inspector.toggle_favorite('named:characters', (('attribute', 'affection'), ('key', 'alice')))
        self.assertEqual(inspector.favorite_rows[0].preview, '7')
        self.root.characters = ModuleType('store.characters')
        self.root.characters.affection = {'alice': 11}
        inspector.set_scope('persistent')
        inspector.refresh()
        self.assertEqual(inspector.favorite_rows[0].preview, '11')
        self.assertEqual(decode_location(encode_location(
            'named:characters', (('attribute', 'affection'), ('key', 'alice'))))[0], 'named:characters')

    def test_registered_root_and_unavailable_state(self):
        inspector = self.inspector
        inspector.register_named_store('quests', lambda: SimpleNamespace(stage=3))
        self.assertIn('named:quests', inspector.named_scopes())
        inspector.set_scope('named:quests')
        self.assertEqual(inspector.rows[0].label, 'stage')
        with self.assertRaises(ValueError):
            inspector.register_named_store('not valid name!', lambda: None)
        with self.assertRaises(ValueError):
            inspector.set_scope('named:does_not_exist')

    def test_search_and_reveal(self):
        ins = self.inspector
        self.assertEqual([r.label for r in ins.rows if r.depth == 0][:1], ['player'])
        ins.search_query = 'health'
        ins.run_search()
        self.assertEqual(len(ins.search_matches), 1)
        self.assertNotIn('health', [r.label for r in ins.rows])
        match = ins.search_matches[0]
        ins.reveal_search(match.scope, match.path)
        self.assertEqual(ins.applied_search, '')
        self.assertIn("[['health']", [r.label for r in ins.rows])

    def test_live_preview_after_change_without_rescanning(self):
        ins = self.inspector
        ins.search_query = 'health'
        ins.run_search()
        initial = ins.search_visited
        self.root.player['stats']['health'] = 42
        ins.refresh()
        self.assertEqual(ins.search_matches[0].preview, '42')
        self.assertEqual(ins.search_visited, initial)
        ins.reset()
        self.assertEqual(ins.search_matches, ())

    def test_panels_cache_readonly_metadata(self):
        ins = self.inspector
        ins.set_panel('overview')
        self.assertIn(('Game', 'Fixture'), ins.overview_rows)
        ins.set_panel('scripts')
        self.assertIn(('Current file', 'game/script.rpy'), ins.script_rows)
        self.assertIn(('Return depth', '2'), ins.script_rows)
        ins.set_panel('variables')
        with self.assertRaises(ValueError):
            ins.set_panel('bogus')

    def test_interval_zero_does_not_poll_panel(self):
        ins = self.inspector
        calls = []
        ins._on_change = lambda: calls.append(1)
        ins.set_panel('scripts')
        ins.set_interval(0)
        ins.tick()
        self.assertEqual(calls, [])
        ins.close()
        self.assertEqual(ins.rows, ())
        ins.tick()
        self.assertEqual(calls, [])


class ContextTests(unittest.TestCase):
    def test_context_best_effort_without_side_effects(self):
        engine = SimpleNamespace(version_string='8.5.3', get_filename_line=lambda: ('script.rpy', 123),
                                 get_return_stack=lambda: ['start', ('opaque', 1), 'next'])
        data = collect_context(engine, SimpleNamespace(name='Test game'))
        self.assertEqual(data['return_depth'], 3)
        self.assertEqual(data['return_labels'], 'start, next')
        self.assertEqual(data['line'], 123)

    def test_missing_apis_do_not_crash(self):
        self.assertEqual(collect_context(SimpleNamespace(), SimpleNamespace()), {})


if __name__ == '__main__':
    unittest.main()
