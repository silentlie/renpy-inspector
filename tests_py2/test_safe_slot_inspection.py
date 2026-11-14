# Python 2.7 compatible tests for native slot inspection; also run on Python 3.
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'game')))
from renpy_inspector.inspection import MISSING, child_descriptors, read_child, snapshot
from renpy_inspector.safe_slots import MAX_SLOT_FIELDS


class SlotCompatibilityTests(unittest.TestCase):
    def test_new_style_class_native_slots_and_inheritance(self):
        class Base(object):
            __slots__ = ('score', '_private')
        class GameModel(Base):
            __slots__ = ('inventory', '__dict__')
            def __getattribute__(self, name):
                raise AssertionError('user getter invoked')
            def __getattr__(self, name):
                raise AssertionError('user fallback invoked')
            @property
            def calculated(self):
                raise AssertionError('user property invoked')

        value = GameModel()
        object.__setattr__(value, 'score', 7)
        object.__setattr__(value, 'inventory', {'potion': 2})
        object.__setattr__(value, '_private', 100)
        object.__getattribute__(value, '__dict__')['ordinary'] = True

        nodes, capped = child_descriptors(value, 80)
        self.assertFalse(capped)
        self.assertEqual([part[0][1] for part in nodes],
                         ['inventory', 'ordinary', 'score'])
        self.assertEqual(read_child(value, ('attribute', 'score')), 7)
        self.assertEqual(read_child(value, ('attribute', 'inventory')),
                         {'potion': 2})
        self.assertIs(read_child(value, ('attribute', '_private')), MISSING)
        self.assertIs(read_child(value, ('attribute', 'calculated')), MISSING)
        self.assertTrue(snapshot(value)[3])

    def test_unset_slots_and_non_native_descriptors_rejected(self):
        class GetData(object):
            def __get__(self, instance, owner):
                raise AssertionError('user descriptor invoked')

        class Safe(object):
            __slots__ = ('unset',)
            bad = GetData()
        value = Safe()
        self.assertEqual(child_descriptors(value, 10), ([], False))
        self.assertIs(read_child(value, ('attribute', 'unset')), MISSING)
        self.assertIs(read_child(value, ('attribute', 'bad')), MISSING)

    def test_private_slot_alias_and_custom_dict_property_are_not_executed(self):
        class Parent(object):
            __slots__ = ('_secret', 'score')
        class Child(Parent):
            __slots__ = ('alias',)
        obj = Child()
        object.__setattr__(obj, 'score', 7)
        Parent.__dict__['_secret'].__set__(obj, 'classified')
        Child.alias = Parent.__dict__['_secret']
        nodes, capped = child_descriptors(obj, 80)
        self.assertEqual([entry[0][1] for entry in nodes], ['score'])
        self.assertFalse(capped)
        self.assertIs(read_child(obj, ('attribute', 'alias')), MISSING)
        self.assertIs(read_child(obj, ('attribute', '_secret')), MISSING)

        class Tricky(object):
            @property
            def __dict__(self):
                raise AssertionError('user dictionary descriptor called')
        invalid = Tricky()
        self.assertEqual(child_descriptors(invalid, 80), ([], False))
        self.assertFalse(snapshot(invalid)[3])
        self.assertIs(read_child(invalid, ('attribute', 'foo')), MISSING)

    def test_store_module_native_dictionary_may_be_a_dict_subclass(self):
        class StoreDict(dict):
            def __iter__(self):
                raise AssertionError('custom dict iterator invoked')
            def __getitem__(self, name):
                raise AssertionError('custom dict getter invoked')
        class StoreModule(object):
            def __init__(self, values):
                object.__setattr__(self, '__dict__', values)
            def __getattribute__(self, name):
                raise AssertionError('custom object getter invoked')
        value = StoreModule(StoreDict(e2e_value=1))
        self.assertEqual(child_descriptors(value, 80, True)[0],
                         [(('attribute', 'e2e_value'), 'e2e_value')])
        self.assertEqual(read_child(value, ('attribute', 'e2e_value')), 1)
        self.assertTrue(snapshot(value)[3])

    def test_slot_count_is_independent_of_caller_page_size(self):
        class Many(object):
            __slots__ = tuple('field{}'.format(i) for i in range(100))
        value = Many()
        for i in range(100):
            object.__setattr__(value, 'field{}'.format(i), i)
        nodes, capped = child_descriptors(value, 80)
        self.assertTrue(capped)
        self.assertEqual(len(nodes), MAX_SLOT_FIELDS)
        self.assertIs(read_child(value, ('attribute', 'field99')), MISSING)


if __name__ == '__main__':
    unittest.main()
