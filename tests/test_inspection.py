"""stdlib-only tests for the engine-independent inspection core."""

import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game'))

from renpy_inspector.controller import Inspector, MAX_CHILDREN, MAX_PAGE_CHILDREN
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

    def test_initialized_slots_are_visible_without_invoking_object_hooks(self):
        class Slotted:
            __slots__ = ('safe', '_private')
            def __init__(self):
                object.__setattr__(self, 'safe', {'hp': 8})
                object.__setattr__(self, '_private', 999)
            def __repr__(self):
                raise AssertionError('repr must not run')
            def __getattribute__(self, name):
                raise AssertionError('__getattribute__ must not run')
            def __getattr__(self, name):
                raise AssertionError('__getattr__ must not run')
            @property
            def computed(self):
                raise AssertionError('property must not run')
        obj = Slotted()
        self.assertTrue(snapshot(obj)[3])
        nodes, truncated = child_descriptors(obj, 80)
        self.assertFalse(truncated)
        self.assertEqual(nodes, [(('attribute', 'safe'), 'safe')])
        self.assertEqual(read_child(obj, ('attribute', 'safe')), {'hp': 8})
        self.assertIs(read_child(obj, ('attribute', '_private')), MISSING)
        self.assertIs(read_child(obj, ('attribute', 'computed')), MISSING)
        self.assertIs(read_child(obj, ('attribute', 'not_here')), MISSING)

    def test_inherited_slots_mixed_with_instance_dict_and_unset_slots(self):
        class Parent(object):
            __slots__ = ('first', 'unused')
        class Child(Parent):
            __slots__ = ('second', '__dict__')
        obj = Child()
        obj.first = 3
        obj.second = [4]
        obj.other = 5
        nodes, capped = child_descriptors(obj, 80)
        self.assertEqual([entry[0][1] for entry in nodes], ['first', 'other', 'second'])
        self.assertFalse(capped)
        self.assertEqual(snapshot(obj)[2], '3 attributes')
        self.assertEqual(read_child(obj, ('attribute', 'first')), 3)
        self.assertEqual(read_child(obj, ('attribute', 'second')), [4])
        self.assertIs(read_child(obj, ('attribute', 'unused')), MISSING)

    def test_derived_property_does_not_expose_an_inherited_slot(self):
        class Parent(object):
            __slots__ = ('secret',)
        class Child(Parent):
            __slots__ = ()
            @property
            def secret(self):
                raise AssertionError('shadowing property must never run')
        obj = Child()
        # Populate the underlying slot directly; the derived property hides it.
        Parent.__dict__['secret'].__set__(obj, 'hidden')
        nodes, capped = child_descriptors(obj, 80)
        self.assertEqual(nodes, [])
        self.assertFalse(capped)
        self.assertIs(read_child(obj, ('attribute', 'secret')), MISSING)

    def test_native_slot_alias_cannot_expose_a_private_base_field(self):
        class Parent(object):
            __slots__ = ('safe', '_private')
        class Child(Parent):
            __slots__ = ('alias',)
        obj = Child()
        obj.safe = 17
        Parent.__dict__['_private'].__set__(obj, 'secret')
        # A writable class dictionary allows swapping a native slot
        # descriptor after class creation. The alias must not expose it.
        Child.alias = Parent.__dict__['_private']
        self.assertEqual(child_descriptors(obj, 80)[0],
                         [(('attribute', 'safe'), 'safe')])
        self.assertIs(read_child(obj, ('attribute', 'alias')), MISSING)
        self.assertIs(read_child(obj, ('attribute', '_private')), MISSING)

    def test_custom_instance_dict_properties_never_run(self):
        class CustomDict(object):
            def __init__(self):
                self.public = 2
            @property
            def __dict__(self):
                raise AssertionError('custom __dict__ getter invoked')
        obj = CustomDict()
        self.assertFalse(snapshot(obj)[3])
        self.assertEqual(child_descriptors(obj, 80), ([], False))
        self.assertIs(read_child(obj, ('attribute', 'public')), MISSING)

    def test_engine_module_namespace_remains_visible(self):
        # Ren'Py's Store module exposes live game state through its module
        # namespace. A native descriptor can return the wrong dictionary.
        class StoreWrapper(ModuleType):
            @property
            def __dict__(self):
                return {'score': 5}
        mod = StoreWrapper('store')
        self.assertEqual(child_descriptors(mod, 40, True)[0],
                         [(('attribute', 'score'), 'score')])
        self.assertEqual(read_child(mod, ('attribute', 'score')), 5)

    def test_renpy_style_store_uses_native_rollback_aware_dict_subclass(self):
        class StoreDict(dict):
            def __iter__(self):
                raise AssertionError('custom StoreDict iterator invoked')
            def __getitem__(self, key):
                raise AssertionError('custom StoreDict getter invoked')
        class StoreModule(object):
            def __init__(self, data):
                object.__setattr__(self, '__dict__', data)
            def __getattribute__(self, key):
                raise AssertionError('custom StoreModule getter invoked')
        store = StoreModule(StoreDict(e2e_value=1, inventory={'hp': 5}))
        nodes, capped = child_descriptors(store, 80, is_store_root=True)
        self.assertFalse(capped)
        self.assertEqual([n[0][1] for n in nodes], ['e2e_value', 'inventory'])
        self.assertEqual(read_child(store, ('attribute', 'e2e_value')), 1)
        self.assertEqual(read_child(store, ('attribute', 'inventory')), {'hp': 5})
        self.assertTrue(snapshot(store)[3])

    def test_slot_enumeration_is_bounded_and_hidden_items_are_not_accessible(self):
        class ManySlots(object):
            __slots__ = tuple('item_{}'.format(i) for i in range(150))
        obj = ManySlots()
        for i in range(150):
            object.__setattr__(obj, 'item_{}'.format(i), i)
        nodes, capped = child_descriptors(obj, 80)
        self.assertEqual(len(nodes), 48)
        self.assertTrue(capped)
        self.assertIn('bounded slots', snapshot(obj)[2])
        self.assertEqual(read_child(obj, ('attribute', 'item_0')), 0)
        self.assertIs(read_child(obj, ('attribute', 'item_90')), MISSING)

    def test_uninitialized_slot_and_untrusted_descriptor_not_enumerated(self):
        class Untrusted(object):
            __slots__ = ('unused',)
            @property
            def dangerous(self):
                raise AssertionError('property executed')
        obj = Untrusted()
        self.assertFalse(snapshot(obj)[3])
        self.assertEqual(child_descriptors(obj, 40), ([], False))
        self.assertIs(read_child(obj, ('attribute', 'unused')), MISSING)


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

    def test_unsafe_instance_dict_property_is_not_called(self):
        class Broken:
            @property
            def __dict__(self):
                raise AssertionError('custom dictionary getter invoked')
        ins, state, _ = self.make_inspector()
        state['store'].game = Broken()
        ins.refresh()
        self.assertEqual(len(ins.rows), 1)
        self.assertEqual(ins.rows[0].state, 'value')
        self.assertFalse(ins.rows[0].expandable)

    def test_many_children_capped(self):
        ins, state, _ = self.make_inspector()
        state['store'].game = list(range(MAX_CHILDREN + 20))
        ins.refresh()
        ins.toggle_node((('attribute', 'game'),))
        self.assertEqual(len(ins.rows), MAX_CHILDREN + 2)
        self.assertEqual(ins.rows[-1].state, 'more')

    def test_load_more_list_pages_preserve_expanded_nodes(self):
        ins, state, _ = self.make_inspector()
        state['store'].game = [{'health': i} for i in range(450)]
        ins.refresh()
        game_path = (('attribute', 'game'),)
        ins.toggle_node(game_path)
        self.assertEqual(len(ins.rows), MAX_CHILDREN + 2)
        self.assertEqual(ins.rows[-1].state, 'more')
        first_path = game_path + (('index', 0),)
        ins.toggle_node(first_path)
        self.assertIn("[['health']", [row.label for row in ins.rows])

        ins.load_more_node(game_path)
        self.assertEqual(len([r for r in ins.rows if r.path == first_path]), 1)
        self.assertTrue(next(r for r in ins.rows if r.path == first_path).expanded)
        self.assertEqual(len([r for r in ins.rows if r.depth == 1 and r.state == 'value']), 400)
        self.assertEqual(ins.rows[-1].state, 'more')

        ins.load_more_node(game_path)
        self.assertEqual(len([r for r in ins.rows if r.depth == 1 and r.state == 'value']), 450)
        self.assertFalse(any(r.state == 'more' for r in ins.rows))

    def test_load_more_root_and_invalid_requests(self):
        state = {'root': __import__('types').SimpleNamespace(**{
            'field{}'.format(i): i for i in range(420)})}
        ins = Inspector()
        ins.bind(lambda: state['root'], lambda: {})
        ins.open()
        self.assertEqual(sum(r.state == 'value' for r in ins.rows), 200)
        ins.load_more_node(())
        self.assertEqual(sum(r.state == 'value' for r in ins.rows), 400)
        ins.load_more_node((('attribute', 'nonexistent'),))
        self.assertEqual(sum(r.state == 'value' for r in ins.rows), 400)
        ins.load_more_node(())
        self.assertEqual(sum(r.state == 'value' for r in ins.rows), 420)
        ins.close()
        ins.load_more_node(())
        self.assertEqual(ins.rows, ())

    def test_per_branch_paging_is_bounded(self):
        ins, state, _ = self.make_inspector()
        state['store'].game = list(range(5000))
        ins.refresh()
        game_path = (('attribute', 'game'),)
        ins.toggle_node(game_path)
        for _ in range(6):
            ins.load_more_node(game_path)
        values = [r for r in ins.rows if r.state == 'value' and r.depth == 1]
        self.assertEqual(len(values), MAX_PAGE_CHILDREN)
        self.assertEqual(ins.rows[-1].state, 'info')
        self.assertIn('cap', ins.rows[-1].label.lower())
        ins.load_more_node(game_path)
        self.assertEqual(len(ins.rows), MAX_PAGE_CHILDREN + 2)


if __name__ == '__main__':
    unittest.main()
