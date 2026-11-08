"""stdlib-only tests for the engine-independent inspection core."""

import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.controller import Inspector, MAX_CHILDREN
from renpy_inspector.inspection import (MISSING, child_descriptors, escape_text,
                                        read_child, snapshot)


class ExplosiveRepr:
    def __repr__(self):
        raise AssertionError('repr must not be used')


class Guarded:
    def __init__(self):
        self.safe = 7

    @property
    def trap(self):
        raise AssertionError('property must not be read')

    def __getattr__(self, key):
        raise AssertionError('__getattr__ must not be read')


class TestCore(unittest.TestCase):
    def test_text_escaping(self):
        self.assertEqual(escape_text('[secret]{b}〖'), '[[secret]{{b}〖〖')

    def test_safe_attribute_read(self):
        obj = Guarded()
        self.assertEqual(read_child(obj, ('attribute', 'safe')), 7)
        self.assertIs(read_child(obj, ('attribute', 'trap')), MISSING)
        self.assertIs(read_child(obj, ('attribute', 'unknown')), MISSING)

    def test_unsafe_repr_never_invoked(self):
        name, typ, preview, expandable, sig = snapshot(ExplosiveRepr())
        self.assertEqual((name, typ), ('value', 'ExplosiveRepr'))
        self.assertNotIn('repr', preview)

    def test_dict_arbitrary_keys_omitted(self):
        weird = ExplosiveRepr()
        nodes, truncated = child_descriptors({weird: 'x', 'ok': 'y'}, 10)
        self.assertEqual(nodes, [(('key', 'ok'), "['ok']")])
        self.assertTrue(truncated)

    def test_bounded_collection_enumeration(self):
        nodes, truncated = child_descriptors(list(range(10000)), 200)
        self.assertEqual(len(nodes), 200)
        self.assertTrue(truncated)

    def test_function_and_module_not_expanded(self):
        m = ModuleType('example')
        self.assertFalse(snapshot(m)[3])
        self.assertFalse(snapshot(lambda x: x)[3])

    def test_store_filters_private_and_imports(self):
        m = ModuleType('store')
        m._internal = 4
        m.game_value = 42
        m.system = sys
        self.assertEqual(child_descriptors(m, 20, True)[0],
                         [(('attribute', 'game_value'), 'game_value')])

    def test_missing_and_none_differ(self):
        self.assertEqual(snapshot(MISSING)[0], 'missing')
        self.assertEqual(snapshot(None)[0], 'value')

    def test_slots_are_not_invoked(self):
        class Slotted:
            __slots__ = ('danger',)
            def __init__(self):
                self.danger = 8
        self.assertFalse(snapshot(Slotted())[3])


class TestController(unittest.TestCase):
    def make_inspector(self, data=None):
        data = data or SimpleNamespace(score=1)
        state = {'store': SimpleNamespace(game=data), 'persistent': SimpleNamespace(flag=True)}
        calls = []
        ins = Inspector(on_change=lambda: calls.append('restart'))
        ins.bind(lambda: state['store'], lambda: state['persistent'])
        ins.open()
        return ins, state, calls

    def test_initial_store_and_expand(self):
        ins, state, _ = self.make_inspector()
        self.assertEqual([r.label for r in ins.rows], ['game'])
        ins.toggle_node((('attribute', 'game'),))
        self.assertEqual([r.label for r in ins.rows], ['game', 'score'])
        self.assertEqual(ins.rows[1].preview, '1')

    def test_scalar_refresh_only_when_changed(self):
        ins, state, calls = self.make_inspector()
        ins.toggle_node((('attribute', 'game'),))
        ins.tick()
        self.assertEqual(calls, [])
        state['store'].game.score = 4
        ins.tick()
        self.assertEqual(calls, ['restart'])
        self.assertEqual(ins.rows[1].preview, '4')
        ins.tick()
        self.assertEqual(calls, ['restart'])

    def test_replacement_of_parent(self):
        ins, state, _ = self.make_inspector()
        ins.toggle_node((('attribute', 'game'),))
        state['store'].game = SimpleNamespace(score=98)
        ins.refresh()
        self.assertEqual(ins.rows[1].preview, '98')

    def test_list_in_place_changes(self):
        ins, state, _ = self.make_inspector([1])
        state['store'].game = [1]
        ins.refresh()
        ins.toggle_node((('attribute', 'game'),))
        state['store'].game.append(2)
        ins.refresh()
        self.assertEqual([r.label for r in ins.rows], ['game', '[[0]', '[[1]'])
        self.assertEqual(ins.rows[0].preview, '2 items')

    def test_dictionary_in_place_changes(self):
        ins, state, _ = self.make_inspector()
        state['store'].game = {'gold': 3}
        ins.refresh()
        ins.toggle_node((('attribute', 'game'),))
        state['store'].game['gold'] = 8
        ins.refresh()
        self.assertEqual(ins.rows[1].preview, '8')
        del state['store'].game['gold']
        ins.refresh()
        self.assertEqual(len(ins.rows), 1)

    def test_cycles_and_shared_objects(self):
        value = []
        value.append(value)
        ins, state, _ = self.make_inspector()
        state['store'].game = value
        ins.refresh()
        ins.toggle_node((('attribute', 'game'),))
        self.assertEqual(len(ins.rows), 2)
        self.assertEqual(ins.rows[1].state, 'cycle')
        self.assertFalse(ins.rows[1].expandable)

    def test_scope_switch(self):
        ins, _, _ = self.make_inspector()
        ins.set_scope('persistent')
        self.assertEqual([r.label for r in ins.rows], ['flag'])
        ins.set_scope('store')
        self.assertEqual([r.label for r in ins.rows], ['game'])

    def test_hidden_and_manual_modes(self):
        ins, state, calls = self.make_inspector()
        ins.set_interval(0)
        state['store'].game = 'new'
        ins.tick()
        self.assertEqual(calls, [])
        self.assertTrue(ins.refresh())
        ins.close()
        self.assertEqual(ins.rows, ())
        ins.tick()
        self.assertEqual(calls, [])

    def test_interval_validation(self):
        ins, _, _ = self.make_inspector()
        for invalid in (1, -1, 49, 60001, 0.25, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    ins.set_interval(invalid)
        ins.set_interval(50)
        self.assertEqual(ins.interval_ms, 50)

    def test_stale_path_not_followed_after_load(self):
        ins, state, _ = self.make_inspector()
        ins.toggle_node((('attribute', 'game'),))
        ins.reset()
        state['store'] = SimpleNamespace(game=SimpleNamespace(score=100))
        ins.refresh()
        self.assertEqual([r.label for r in ins.rows], ['game'])
        ins.toggle_node((('attribute', 'game'),))
        self.assertEqual(ins.rows[1].preview, '100')

    def test_per_node_errors_isolated(self):
        class Broken:
            @property
            def __dict__(self):
                raise RuntimeError('blocked')
        ins, state, _ = self.make_inspector()
        state['store'].game = Broken()
        ins.refresh()
        self.assertEqual(len(ins.rows), 1)
        self.assertEqual(ins.rows[0].state, 'error')

    def test_many_children_capped(self):
        ins, state, _ = self.make_inspector()
        state['store'].game = list(range(MAX_CHILDREN + 20))
        ins.refresh()
        ins.toggle_node((('attribute', 'game'),))
        self.assertEqual(len(ins.rows), MAX_CHILDREN + 2)
        self.assertEqual(ins.rows[-1].state, 'info')


if __name__ == '__main__':
    unittest.main()
