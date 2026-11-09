"""Geometry and custom-renderer regression tests without the Ren'Py SDK.

These use a deliberately small fake Render API, so SDK lint and interactive
visual tests remain separate requirements.
"""
import sys
import textwrap
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'game'))
from renpy_inspector.tree_layout import (ROW_HEIGHT, geometry, visible_range,
                                         clamp_scroll, hit_test)


class Row:
    def __init__(self, number, *, depth=0, state='value', expandable=False, pinnable=True):
        self.path = (('attribute', 'node{}'.format(number)),)
        self.label = 'node{}'.format(number)
        self.preview = 'value{}'.format(number)
        self.type_name = 'int'
        self.depth = depth
        self.state = state
        self.expandable = expandable
        self.expanded = False
        self.pinnable = pinnable
        self.favorite = False


class DummyCanvas:
    def __init__(self):
        self.ops = []
    def rect(self, *a): self.ops.append(('rect', a))
    def line(self, *a): self.ops.append(('line', a))
    def polygon(self, *a): self.ops.append(('polygon', a))
    def circle(self, *a): self.ops.append(('circle', a))


class DummyRender:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self._canvas = DummyCanvas()
        self.blits = []
    def canvas(self): return self._canvas
    def blit(self, child, pos): self.blits.append((child, pos))


class DummyText:
    def __init__(self, text, **kwargs):
        self.text = text
        self.kwargs = kwargs


class DummyDisplayable:
    def __init__(self, **kwargs):
        pass


class Ignored(Exception):
    pass


class TreeGeometryTests(unittest.TestCase):
    def test_bounded_visible_range(self):
        top, body, details = geometry(375, 660)
        self.assertEqual((top, details), (26, 84))
        start, end = visible_range(1200, body, 15000)
        self.assertLessEqual(end - start, body // ROW_HEIGHT + 3)
        self.assertGreater(start, 0)
        self.assertEqual(clamp_scroll(10**8, 1200, body), 1200 * ROW_HEIGHT - body)

    def test_hit_targets(self):
        rows = [Row(0, expandable=True), Row(1), Row(2, state='more', pinnable=False)]
        self.assertEqual(hit_test(rows, 11, 26 + 15, 0, 370, 350), ('toggle', 0))
        self.assertEqual(hit_test(rows, 350, 26 + 45, 0, 370, 350), ('pin', 1))
        self.assertEqual(hit_test(rows, 70, 26 + 75, 0, 370, 350), ('more', 2))
        self.assertEqual(hit_test(rows, -1, 30, 0, 370, 350), None)
        self.assertEqual(hit_test(rows, 5, 320, 0, 370, 350), None)


class TreeDisplayableTests(unittest.TestCase):
    def setUp(self):
        import renpy_inspector
        self.package = renpy_inspector
        self.original_inspector = renpy_inspector.inspector
        self.ins = SimpleNamespace(is_open=True, panel='variables', scope='store',
                                   tree_scroll=0, tree_selection=None,
                                   rows=tuple(Row(i) for i in range(1200)))
        self.calls = []
        self.ins.select_tree_row = lambda path: self.calls.append(('select', path))
        self.ins.toggle_node = lambda path: self.calls.append(('toggle', path))
        self.ins.toggle_favorite = lambda scope, path: self.calls.append(('pin', path))
        self.ins.load_more_node = lambda path: self.calls.append(('more', path))
        renpy_inspector.inspector = self.ins
        self.addCleanup(setattr, renpy_inspector, 'inspector', self.original_inspector)
        self.redraws = []
        self.engine = SimpleNamespace(Displayable=DummyDisplayable, Render=DummyRender,
                                      render=lambda child, w, h, st, at: child,
                                      redraw=lambda child, delay: self.redraws.append(delay),
                                      IgnoreEvent=Ignored)
        self.pygame = types.ModuleType('pygame')
        for k, v in [('MOUSEMOTION', 10), ('MOUSEBUTTONDOWN', 11),
                     ('MOUSEBUTTONUP', 12), ('MOUSEWHEEL', 13)]:
            setattr(self.pygame, k, v)
        textmod = types.ModuleType('renpy.text.text')
        textmod.Text = DummyText
        mod = types.ModuleType('renpy.text')
        original = {k: sys.modules.get(k) for k in ('pygame', 'renpy', 'renpy.text', 'renpy.text.text')}
        sys.modules.update({'pygame': self.pygame, 'renpy': self.engine,
                            'renpy.text': mod, 'renpy.text.text': textmod})
        def restore():
            for k, value in original.items():
                if value is None: sys.modules.pop(k, None)
                else: sys.modules[k] = value
        self.addCleanup(restore)
        source = (ROOT / 'game' / 'renpy_inspector_tree.rpy').read_text(encoding='utf-8')
        code = textwrap.dedent(source.split('init -80 python:', 1)[1])
        namespace = {'renpy': self.engine, 'renpy_inspector': renpy_inspector}
        exec(compile(code, 'renpy_inspector_tree.rpy', 'exec'), namespace)
        self.cls = namespace['InspectorTreeDisplayable']

    def test_render_virtualizes_rows(self):
        d = self.cls(370, 640)
        result = d.render(370, 640, 0, 0)
        self.assertEqual((result.w, result.h), (370, 640))
        self.assertLess(len(result.blits), 55)
        self.assertTrue(any(op[0] == 'rect' for op in result.canvas().ops))
        self.assertEqual(len(d.visit()), 0)
        self.assertFalse(hasattr(d, '_cached_render'))

    def test_click_expand_and_load_more(self):
        self.ins.rows = (Row(0, expandable=True), Row(1, state='more', pinnable=False))
        d = self.cls(370, 640)
        with self.assertRaises(Ignored):
            d.event(SimpleNamespace(type=self.pygame.MOUSEBUTTONDOWN, button=1), 12, 40, 0)
        self.assertEqual(self.calls[-1][0], 'toggle')
        with self.assertRaises(Ignored):
            d.event(SimpleNamespace(type=self.pygame.MOUSEBUTTONDOWN, button=1), 50, 75, 0)
        self.assertEqual(self.calls[-1][0], 'more')

    def test_wheel_and_scroll_bounds(self):
        d = self.cls(370, 640)
        with self.assertRaises(Ignored):
            d.event(SimpleNamespace(type=self.pygame.MOUSEBUTTONDOWN, button=5), 80, 80, 0)
        self.assertEqual(self.ins.tree_scroll, 3 * ROW_HEIGHT)
        with self.assertRaises(Ignored):
            d.event(SimpleNamespace(type=self.pygame.MOUSEWHEEL, y=-1), 80, 80, 0)
        self.assertEqual(self.ins.tree_scroll, 6 * ROW_HEIGHT)


if __name__ == '__main__':
    unittest.main()
