"""Bounded, read-only child pages for the localhost inspector (Python 2/3).

HTTP workers may parse and queue these requests but MUST NOT invoke
build_tree_page. Ren'Py's interaction thread performs all game-data reads.
"""
from __future__ import unicode_literals

import json
import time

from .compat import integer_types, string_types, to_text, binary_type
from .bridge_snapshot import MAX_TEXT, _safe_text
from .favorites import encode_location, format_location
from .inspection import MISSING, child_descriptors, read_child, snapshot

MAX_BRANCH = 1000
PAGE_SIZE = 80
MAX_DEPTH = 8
# On-demand primitive display budget; independent from compact tree previews.
MAX_FULL_VALUE_CHARS = 16384
MAX_FULL_INTEGER_BITS = 4096


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


def build_lazy_snapshot(providers, game_info=None):
    """Capture shallow root pages; fetch descendants only on user expansion.

    Root and child pages use the same bounded ordering, unlike the former
    450-node recursively sampled snapshot which could obscure whole subtrees.
    """
    result = {
        'protocol': 1, 'captured_at': time.time(),
        'scopes': {}, 'counts': {}, 'truncated': {},
        'root_pages': {}, 'game': {},
    }
    if isinstance(game_info, dict):
        for name in ('game', 'version', 'filename', 'line', 'return_depth', 'return_labels'):
            value = game_info.get(name)
            if type(value) in (int, float) or isinstance(value, string_types):
                result['game'][name] = _safe_text(value)
    for scope in ('store', 'persistent'):
        try:
            page = build_tree_page(providers, scope, (), 0, PAGE_SIZE)
            result['scopes'][scope] = page['items']
            result['counts'][scope] = len(page['items'])
            result['truncated'][scope] = bool(page['more'] or page['capped'])
            result['root_pages'][scope] = {
                'next_offset': page['next_offset'],
                'more': page['more'], 'capped': page['capped'],
            }
        except Exception:
            result['scopes'][scope] = []
            result['counts'][scope] = 0
            result['truncated'][scope] = False
            result['root_pages'][scope] = {
                'next_offset': 0, 'more': False, 'capped': False,
            }
    return result


def build_tree_value(providers, scope, path):
    """Resolve a single pinned path safely, without requiring tree expansion.

    Called ONLY by Ren'Py's interaction thread. Each segment must be a visible
    descriptor, preventing private attribute access or arbitrary evaluation.
    Missing keys produce an explicit missing node so pins survive replacements.
    """
    scope, path, unused_offset, unused_size = validate_tree_request(
        scope, [[kind, value] for kind, value in path], 0, 1)
    if not path:
        raise ValueError('a favourite must identify a node')
    value = providers[scope]()
    ancestors = set((id(value),))
    missing = False
    is_cycle = False
    for depth, segment in enumerate(path):
        descriptors, unused_truncated = child_descriptors(
            value, MAX_BRANCH, is_store_root=(depth == 0 and scope == 'store'))
        if segment not in [pair[0] for pair in descriptors]:
            missing = True
            break
        value = read_child(value, segment)
        if value is MISSING:
            missing = True
            break
        is_cycle = id(value) in ancestors
        if is_cycle and depth != len(path) - 1:
            missing = True
            break
        ancestors.add(id(value))
    if missing:
        state, type_name, preview, expandable = 'missing', 'missing', '<missing>', False
    else:
        state, type_name, preview, expandable, unused_token = snapshot(
            value, is_cycle=is_cycle)
    last_kind, last_value = path[-1]
    name = last_value if last_kind == 'attribute' else (
        '[{}]'.format(last_value) if last_kind == 'index' else repr(last_value))
    node = {
        'key': json.dumps([scope, path], ensure_ascii=True, separators=(',', ':')),
        'name': _safe_text(name, 90),
        'path': _safe_text(format_location(scope, path), 230),
        'type': _safe_text(type_name, 48),
        'preview': _safe_text(preview),
        'state': _safe_text(state, 18),
        'expandable': bool(expandable),
        'children': [],
    }
    return {'protocol': 1, 'scope': scope, 'node': node}


def build_full_value(providers, scope, path):
    """Game-thread-only, size-capped read of a built-in primitive value.

    Paths use the same bounded visible-descriptor traversal as favourite
    watches. User objects, properties, iterators and custom repr/str methods
    must never be invoked to produce full-value text.
    """
    scope, path, unused_offset, unused_size = validate_tree_request(
        scope, [[kind, value] for kind, value in path], 0, 1)
    if not path:
        raise ValueError('full-value inspection needs a path')
    value = providers[scope]()
    ancestors = set((id(value),))
    cycle = False
    for depth, segment in enumerate(path):
        descriptors, unused_truncated = child_descriptors(
            value, MAX_BRANCH, is_store_root=(depth == 0 and scope == 'store'))
        if segment not in [pair[0] for pair in descriptors]:
            value = MISSING
            break
        value = read_child(value, segment)
        if value is MISSING:
            break
        cycle = id(value) in ancestors
        if cycle:
            if depth != len(path) - 1:
                value = MISSING
            break
        ancestors.add(id(value))

    result = {
        'protocol': 1, 'scope': scope,
        'key': json.dumps([scope, path], ensure_ascii=True, separators=(',', ':')),
        'limit': MAX_FULL_VALUE_CHARS,
        'kind': 'unsupported', 'text': None, 'truncated': False,
        'length': None, 'length_unit': None,
    }
    if value is MISSING:
        result['kind'] = 'missing'
        result['reason'] = 'Variable is not available in the current game state'
    elif cycle:
        result['reason'] = 'Cyclic references cannot be displayed as a primitive'
    elif type(value) in string_types:
        # Slice BEFORE converting byte strings, keeping reads bounded even if
        # a host game holds an enormous text blob.
        result['kind'] = 'string'
        result['length'] = len(value)
        result['length_unit'] = 'bytes' if type(value) is binary_type else 'characters'
        result['truncated'] = len(value) > MAX_FULL_VALUE_CHARS
        prefix = value[:MAX_FULL_VALUE_CHARS]
        if type(value) is binary_type:
            # Python 2 str is bytes, not Unicode. Never silently replace
            # undecodable bytes and present a lossy conversion as exact.
            try:
                prefix = prefix.decode('utf-8')
            except UnicodeError:
                result['kind'] = 'unsupported'
                result['text'] = None
                result['reason'] = 'Byte string is not UTF-8 decodable within the display budget'
                return result
        result['text'] = to_text(prefix)
    elif type(value) is bool:
        result['kind'] = 'boolean'
        result['text'] = 'True' if value else 'False'
    elif value is None:
        result['kind'] = 'null'
        result['text'] = 'None'
    elif type(value) in integer_types:
        if value.bit_length() > MAX_FULL_INTEGER_BITS:
            result['reason'] = 'Integer exceeds the safe display budget'
        else:
            result['kind'] = 'number'
            result['text'] = str(value)
    elif type(value) is float:
        result['kind'] = 'number'
        result['text'] = repr(value)
    else:
        result['reason'] = 'Full value is available only for built-in primitives'
    return result
