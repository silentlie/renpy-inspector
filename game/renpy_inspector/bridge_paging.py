"""Bounded, read-only child pages for the localhost inspector (Python 2/3).

HTTP workers may parse and queue these requests but MUST NOT invoke
build_tree_page. Ren'Py's interaction thread performs all game-data reads.
"""
from __future__ import unicode_literals

import json

from .compat import integer_types, string_types
from .favorites import encode_location, format_location
from .inspection import MISSING, child_descriptors, read_child, snapshot
from .bridge_snapshot import _safe_text

MAX_BRANCH = 1000
PAGE_SIZE = 80
MAX_DEPTH = 8


def validate_tree_request(scope, raw_path, offset, size):
    """Accept only typed, bounded root-relative paths and paging parameters."""
    if scope not in ('store', 'persistent'):
        raise ValueError('unsupported scope')
    if not isinstance(raw_path, list) or len(raw_path) > MAX_DEPTH:
        raise ValueError('invalid path depth')
    if type(offset) is not int or type(size) is not int:
        raise ValueError('invalid page numbers')
    if offset < 0 or offset >= MAX_BRANCH or size < 1 or size > PAGE_SIZE:
        raise ValueError('page out of bounds')
    path = []
    for item in raw_path:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError('invalid path segment')
        kind, value = item
        if kind == 'attribute':
            if not isinstance(value, string_types) or not value or value.startswith('_'):
                raise ValueError('private or invalid attribute')
        elif kind == 'index':
            if type(value) not in integer_types or not 0 <= value <= 1000000:
                raise ValueError('invalid list index')
        elif kind == 'key':
            if not (type(value) in integer_types + (bool, type(None)) or
                    isinstance(value, string_types)):
                raise ValueError('invalid mapping key')
        else:
            raise ValueError('invalid path type')
        path.append((kind, value))
    path = tuple(path)
    if path:
        encode_location(scope, path)  # size and type limits, no expressions
    return scope, path, offset, size


def build_tree_page(providers, scope, path, offset, size):
    """Resolve and page only visible children, without retaining game references.

    Each path step must have appeared in a bounded visible-key enumeration.
    This prevents requests from bypassing private names or filtered store
    members, even when a caller holds a valid localhost pairing token.
    """
    scope, path, offset, size = validate_tree_request(
        scope, [[kind, value] for kind, value in path], offset, size)
    owner = providers[scope]()
    ancestors = set((id(owner),))
    for depth, segment in enumerate(path):
        visible, unused = child_descriptors(
            owner, MAX_BRANCH, is_store_root=(depth == 0 and scope == 'store'))
        if segment not in [pair[0] for pair in visible]:
            raise ValueError('path is not visible')
        owner = read_child(owner, segment)
        if owner is MISSING or id(owner) in ancestors:
            raise ValueError('missing or cyclic path')
        ancestors.add(id(owner))

    visible, truncated = child_descriptors(
        owner, MAX_BRANCH, is_store_root=(not path and scope == 'store'))
    page = visible[offset:offset + size]
    items = []
    for segment, label in page:
        child_path = path + (segment,)
        try:
            value = read_child(owner, segment)
            is_cycle = value is not MISSING and id(value) in ancestors
            state, type_name, preview, expandable, unused_token = snapshot(
                value, is_cycle=is_cycle)
        except Exception:
            state, type_name, preview, expandable = 'error', 'error', '<unavailable>', False
        items.append({
            'key': json.dumps([scope, child_path], ensure_ascii=True, separators=(',', ':')),
            'name': _safe_text(label, 90),
            'path': _safe_text(format_location(scope, child_path), 230),
            'type': _safe_text(type_name, 48),
            'preview': _safe_text(preview),
            'state': _safe_text(state, 18),
            'expandable': bool(expandable),
            'children': [],
        })
    next_offset = offset + len(items)
    more = next_offset < MAX_BRANCH and (next_offset < len(visible) or truncated)
    capped = next_offset >= MAX_BRANCH and truncated
    return {
        'protocol': 1, 'scope': scope,
        'parent': json.dumps([scope, path], ensure_ascii=True, separators=(',', ':')),
        'offset': offset, 'next_offset': next_offset,
        'more': bool(more), 'capped': bool(capped),
        'items': items,
    }
