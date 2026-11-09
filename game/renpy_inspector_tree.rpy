# v0.5 prototype: virtual, purpose-built tree renderer for Ren'Py 7 and 8.
# No Render objects, inspected Python objects or controller references are kept
# on the displayable. This is screen-only UI, never gameplay state.
init -80 python:
    import pygame
    from renpy.text.text import Text as InspectorText
    from renpy_inspector.tree_layout import (
        ROW_HEIGHT, INDENT_WIDTH, MAX_GUIDES, SCROLLBAR_WIDTH,
        geometry, clamp_scroll, max_scroll, visible_range, hit_test,
    )
    from renpy_inspector.favorites import format_location
    from renpy_inspector.inspection import escape_text

    class InspectorTreeDisplayable(renpy.Displayable):
        """Virtualised IDE-style explorer; draws a single Ren'Py Render."""

        def __init__(self, width, height, **kwargs):
            super(InspectorTreeDisplayable, self).__init__(**kwargs)
            self.view_width = int(width)
            self.view_height = int(height)
            self.hover = -1
            self.dragging = False
            self.drag_y = 0
            self.drag_scroll = 0

        def visit(self):
            return []

        def _text(self, target, value, x, y, available, size, color, st, at):
            """Render a bounded text displayable without holding its Render."""
            available = max(1, int(available))
            # Conservative character clipping prevents absurd game strings from
            # becoming wide, expensive text surfaces in older Ren'Py builds.
            max_chars = max(4, int(available / max(5, size * 0.56)))
            value = value[:max_chars - 1] + u'…' if len(value) > max_chars else value
            child = InspectorText(value, size=size, color=color, slow=False,
                                  substitute=False)
            rendered = renpy.render(child, available, size + 5, st, at)
            target.blit(rendered, (int(x), int(y)))

        def render(self, width, height, st, at):
            w = max(1, min(int(width), self.view_width))
            h = max(1, min(int(height), self.view_height))
            canvas_render = renpy.Render(w, h)
            draw = canvas_render.canvas()
            ins = renpy_inspector.inspector
            rows = ins.rows
            top, body_h, details_h = geometry(w, h)
            ins.tree_scroll = clamp_scroll(ins.tree_scroll, len(rows), body_h)
            scroll = ins.tree_scroll
            draw.rect('#0d1522', (0, 0, w, h))
            draw.rect('#172336', (0, 0, w, top))
            self._text(canvas_render, 'VARIABLES', 11, 5, w - 110,
                       11, '#8da4c2', st, at)
            self._text(canvas_render, '{} nodes'.format(len(rows)), w - 81, 5,
                       70, 10, '#8098b3', st, at)
            draw.line('#27384e', (0, top - 1), (w, top - 1), 1)

            start, end = visible_range(len(rows), body_h, scroll)
            for i in range(start, end):
                row = rows[i]
                y = top + i * ROW_HEIGHT - scroll
                if y >= top + body_h or y + ROW_HEIGHT <= top:
                    continue
                selected = ins.tree_selection == row.path
                hovered = self.hover == i
                if selected:
                    draw.rect('#244669', (0, y, w - SCROLLBAR_WIDTH, ROW_HEIGHT))
                    draw.rect('#67b5ea', (0, y, 2, ROW_HEIGHT))
                elif hovered:
                    draw.rect('#1c3048', (0, y, w - SCROLLBAR_WIDTH, ROW_HEIGHT))
                if i:
                    draw.line('#1a2739', (0, y), (w - SCROLLBAR_WIDTH, y), 1)

                guide_count = min(row.depth, MAX_GUIDES)
                for level in range(guide_count):
                    guide_x = 18 + level * INDENT_WIDTH
                    draw.line('#2a4059', (guide_x, y + 1),
                              (guide_x, y + ROW_HEIGHT - 1), 1)
                x = 8 + guide_count * INDENT_WIDTH
                if row.state == 'more':
                    self._text(canvas_render, '+  ' + row.label, x + 18, y + 7,
                               w - x - 40, 12, '#74c6ff', st, at)
                    continue
                if row.state == 'info':
                    self._text(canvas_render, row.label, x + 18, y + 7,
                               w - x - 40, 11, '#9bafc8', st, at)
                    continue

                if row.expandable:
                    if row.expanded:
                        points = [(x + 2, y + 12), (x + 12, y + 12),
                                  (x + 7, y + 18)]
                    else:
                        points = [(x + 5, y + 10), (x + 5, y + 20),
                                  (x + 11, y + 15)]
                    draw.polygon('#a4bed9', points)
                else:
                    draw.circle('#546b85', (x + 7, y + 15), 2)

                name_x = x + 19
                name_budget = max(34, int((w - name_x - 42) * 0.66))
                self._text(canvas_render, row.label, name_x, y + 6,
                           name_budget, 13, '#e9f1fa', st, at)
                preview_x = name_x + name_budget + 5
                preview_budget = max(12, w - preview_x - 34)
                preview = row.preview if row.type_name == 'missing' else row.type_name + ' : ' + row.preview
                self._text(canvas_render, preview, preview_x, y + 8,
                           preview_budget, 10, '#8fa9c7', st, at)
                if row.favorite or (hovered and row.pinnable):
                    glyph = u'★' if row.favorite else u'☆'
                    self._text(canvas_render, glyph, w - 28, y + 6, 19,
                               15, '#f5c56b' if row.favorite else '#9db7ce', st, at)

            # Only the visible row range is drawn, including a small overscan.
            if len(rows) * ROW_HEIGHT > body_h and body_h > 0:
                track_x = w - 8
                draw.rect('#203249', (track_x, top, 5, body_h))
                total = len(rows) * ROW_HEIGHT
                thumb_h = max(22, int(body_h * body_h / float(total)))
                travel = max(0, body_h - thumb_h)
                denom = max_scroll(len(rows), body_h)
                thumb_y = top + int(travel * (float(scroll) / denom)) if denom else top
                draw.rect('#6086ad', (track_x, thumb_y, 5, thumb_h))

            if details_h:
                footer_y = top + body_h
                draw.rect('#152338', (0, footer_y, w, details_h))
                draw.line('#304962', (0, footer_y), (w, footer_y), 1)
                selected_row = next((r for r in rows if r.path == ins.tree_selection), None)
                if selected_row is None:
                    self._text(canvas_render, 'SELECT A VARIABLE', 11,
                               footer_y + 9, w - 24, 11, '#8cabc8', st, at)
                    self._text(canvas_render, 'Click a row to inspect its path and value.',
                               11, footer_y + 34, w - 22, 11, '#758ea9', st, at)
                else:
                    self._text(canvas_render, selected_row.label + '   /   ' + selected_row.type_name,
                               11, footer_y + 6, w - 24, 13, '#e7f1ff', st, at)
                    try:
                        path_label = escape_text(format_location(ins.scope, selected_row.path))
                    except Exception:
                        path_label = selected_row.label
                    self._text(canvas_render, path_label, 11, footer_y + 28,
                               w - 24, 11, '#80bce5', st, at)
                    self._text(canvas_render, selected_row.preview, 11, footer_y + 51,
                               w - 24, 11, '#a8c3da', st, at)
            return canvas_render

        def event(self, ev, x, y, st):
            ins = renpy_inspector.inspector
            if not ins.is_open or ins.panel != 'variables' or ins.scope == 'favorites':
                return None
            w, h = self.view_width, self.view_height
            top, body_h, _ = geometry(w, h)
            rows = ins.rows
            ins.tree_scroll = clamp_scroll(ins.tree_scroll, len(rows), body_h)
            inside = 0 <= x < w and top <= y < top + body_h

            if ev.type == pygame.MOUSEMOTION:
                new_hover = (ins.tree_scroll + int(y) - top) // ROW_HEIGHT if inside else -1
                if new_hover >= len(rows):
                    new_hover = -1
                if new_hover != self.hover:
                    self.hover = new_hover
                    renpy.redraw(self, 0)
                if self.dragging:
                    remaining = max(1, body_h - max(22, int(body_h * body_h /
                                                             float(max(1, len(rows) * ROW_HEIGHT)))))
                    fraction = (y - self.drag_y) / float(remaining)
                    ins.tree_scroll = clamp_scroll(
                        self.drag_scroll + int(fraction * max_scroll(len(rows), body_h)),
                        len(rows), body_h)
                    renpy.redraw(self, 0)
                    raise renpy.IgnoreEvent()

            if ev.type == pygame.MOUSEBUTTONUP and getattr(ev, 'button', 0) == 1:
                if self.dragging:
                    self.dragging = False
                    raise renpy.IgnoreEvent()

            if ev.type == pygame.MOUSEBUTTONDOWN and inside:
                button = getattr(ev, 'button', 0)
                if button in (4, 5):
                    ins.tree_scroll = clamp_scroll(
                        ins.tree_scroll + (3 * ROW_HEIGHT if button == 5 else -3 * ROW_HEIGHT),
                        len(rows), body_h)
                    renpy.redraw(self, 0)
                    raise renpy.IgnoreEvent()
                if button == 1:
                    hit = hit_test(rows, x, y, ins.tree_scroll, w, h)
                    if hit is not None:
                        action, index = hit
                        if action == 'scroll':
                            self.dragging = True
                            self.drag_y = y
                            self.drag_scroll = ins.tree_scroll
                        elif action == 'more':
                            ins.load_more_node(rows[index].path[:-1])
                        elif action == 'toggle':
                            ins.toggle_node(rows[index].path)
                        elif action == 'pin':
                            ins.toggle_favorite(ins.scope, rows[index].path)
                        else:
                            ins.select_tree_row(rows[index].path)
                        renpy.redraw(self, 0)
                        raise renpy.IgnoreEvent()
            if inside and ev.type == getattr(pygame, 'MOUSEWHEEL', -1):
                delta = getattr(ev, 'y', 0)
                if delta:
                    ins.tree_scroll = clamp_scroll(ins.tree_scroll - 3 * ROW_HEIGHT * int(delta),
                                                   len(rows), body_h)
                    renpy.redraw(self, 0)
                    raise renpy.IgnoreEvent()
            return None
