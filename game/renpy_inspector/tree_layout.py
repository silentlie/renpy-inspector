"""Small, engine-independent geometry for the virtual Ren'Py tree.

All coordinates are pixels relative to the custom displayable. No Ren'Py
objects or gameplay values are retained here; importable on Python 2.7/3.x.
"""

ROW_HEIGHT = 30
HEADER_HEIGHT = 26
DETAIL_HEIGHT = 84
INDENT_WIDTH = 14
MAX_GUIDES = 8
SCROLLBAR_WIDTH = 10
PIN_WIDTH = 31


def geometry(width, height):
    width = max(1, int(width))
    height = max(1, int(height))
    header = min(HEADER_HEIGHT, height)
    detail = DETAIL_HEIGHT if height >= 220 else 0
    return (header, max(0, height - header - detail), detail)


def max_scroll(count, viewport_height):
    return max(0, max(0, int(count)) * ROW_HEIGHT - max(0, int(viewport_height)))


def clamp_scroll(value, count, viewport_height):
    return max(0, min(max_scroll(count, viewport_height), int(value)))


def visible_range(count, viewport_height, scroll):
    count = max(0, int(count))
    viewport_height = max(0, int(viewport_height))
    if not viewport_height or not count:
        return (0, 0)
    start = max(0, min(count, int(scroll) // ROW_HEIGHT))
    end = min(count, (int(scroll) + viewport_height + ROW_HEIGHT - 1) // ROW_HEIGHT + 1)
    return start, max(start, end)


def hit_test(rows, x, y, scroll, width, height):
    """Return (action, row_index), with actions select/toggle/pin/more/scroll."""
    width, height = int(width), int(height)
    header, viewport, _ = geometry(width, height)
    if x < 0 or y < 0 or x >= width or y >= height:
        return None
    if y < header or y >= header + viewport:
        return None
    if x >= width - SCROLLBAR_WIDTH:
        return ('scroll', None)
    idx = (int(scroll) + int(y) - header) // ROW_HEIGHT
    if idx < 0 or idx >= len(rows):
        return None
    row = rows[idx]
    if row.state == 'more':
        return ('more', idx)
    if row.state == 'info':
        return ('select', idx)
    if row.pinnable and x >= width - PIN_WIDTH:
        return ('pin', idx)
    marker_x = 8 + min(row.depth, MAX_GUIDES) * INDENT_WIDTH
    if row.expandable and x >= marker_x - 3 and x < marker_x + 26:
        return ('toggle', idx)
    return ('select', idx)
