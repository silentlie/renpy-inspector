"""Bounded read-only variable-name search and typed-path reveal (Python 2/3).

Only Ren'Py's interaction thread may call build_search_results and
build_reveal_chain. No arbitrary expressions, getters, or network-thread
access to the game. Search is deliberately budgeted and never exhaustive.
"""
from __future__ import unicode_literals

import json
from collections import deque

from .bridge_paging import MAX_BRANCH, MAX_DEPTH, validate_tree_request
from .bridge_snapshot import _safe_text
from .compat import string_types
from .favorites import encode_location, format_location
from .inspection import MISSING, child_descriptors, read_child, snapshot

SEARCH_VISIT_LIMIT = 1400
SEARCH_RESULT_LIMIT = 30
SEARCH_DEPTH_LIMIT = 5
SEARCH_QUEUE_LIMIT = 160
SEARCH_CHILD_LIMIT = 100


def validate_search_request(scope, query):
    if scope not in ('store', 'persistent', 'all'):
        raise ValueError('invalid search scope')
    if not isinstance(query, string_types):
        raise ValueError('invalid search query')
    query = query.strip()
    if not 2 <= len(query) <= 64 or any(ord(c) < 32 for c in query):
        raise ValueError('search query must be between 2 and 64 characters')
    return scope, query.lower()


def _render_node(scope, path, label, value, is_cycle):
    state, typename, preview, expandable, unused = snapshot(value, is_cycle=is_cycle)
    return {
        'key': json.dumps([scope, path], ensure_ascii=True, separators=(',', ':')),
        'scope': scope,
        'name': _safe_text(label, 90),
        'path': _safe_text(format_location(scope, path), 230),
        'type': _safe_text(typename, 48),
        'preview': _safe_text(preview),
        'state': _safe_text(state, 18),
        'expandable': bool(expandable and not is_cycle),
        'children': [],
    }


def build_search_results(providers, scope, query):
    """Bounded breadth-first discovery, including nodes never loaded by UI.

    Results search *names and formatted paths*, not raw object values.
    Every visited container has a bounded descriptor budget; extension
    objects with hidden/private attributes or cyclic references are excluded.
    """
    scope, needle = validate_search_request(scope, query)
    roots = ('store', 'persistent') if scope == 'all' else (scope,)
    queue = deque()
    limited = False
    for root_scope in roots:
        try:
            owner = providers[root_scope]()
            queue.append((root_scope, owner, (), 0, frozenset((id(owner),))))
        except Exception:
            limited = True
    results = []
    scanned = 0
    while queue and scanned < SEARCH_VISIT_LIMIT and len(results) < SEARCH_RESULT_LIMIT:
        root_scope, owner, path, depth, ancestors = queue.popleft()
        at_root = not path
        child_limit = MAX_BRANCH if at_root else SEARCH_CHILD_LIMIT
        try:
            descriptors, truncated = child_descriptors(
                owner, child_limit, is_store_root=(at_root and root_scope == 'store'))
        except Exception:
            limited = True
            continue
        if truncated:
            limited = True
        for segment, label in descriptors:
            if scanned >= SEARCH_VISIT_LIMIT or len(results) >= SEARCH_RESULT_LIMIT:
                limited = True
                break
            child_path = path + (segment,)
            try:
                encode_location(root_scope, child_path)
            except (TypeError, ValueError):
                limited = True
                continue
            scanned += 1
            try:
                display_path = format_location(root_scope, child_path)
                hit = needle in label.lower() or needle in display_path.lower()
                value = read_child(owner, segment)
                if value is MISSING:
                    continue
                is_cycle = id(value) in ancestors
                if hit:
                    results.append(_render_node(root_scope, child_path, label, value, is_cycle))
                if not is_cycle and depth + 1 < SEARCH_DEPTH_LIMIT:
                    # Do not traverse scalar values, arbitrary iterables or functions.
                    state, unused_type, unused_preview, expandable, unused_token = snapshot(value)
                    if state == 'value' and expandable:
                        if len(queue) < SEARCH_QUEUE_LIMIT:
                            queue.append((root_scope, value, child_path,
                                          depth + 1, ancestors | frozenset((id(value),))))
                        else:
                            limited = True
                elif depth + 1 >= SEARCH_DEPTH_LIMIT:
                    # A non-expanded child may still contain matching descendants.
                    state, unused_type, unused_preview, expandable, unused_token = snapshot(value)
                    if expandable:
                        limited = True
            except Exception:
                limited = True
                continue
    if queue:
        limited = True
    return {'protocol': 1, 'query': query, 'results': results,
            'scanned': scanned, 'limited': bool(limited),
            'max_depth': SEARCH_DEPTH_LIMIT, 'max_visits': SEARCH_VISIT_LIMIT}


def build_reveal_chain(providers, scope, path):
    """Provide only verified, visible ancestors for a typed target path.

    The client can materialise just this path in the virtual tree without
    downloading every preceding page. Ordinary paginated browsing remains
    bounded and the reveal chain carries no gameplay object references.
    """
    scope, path, ignored_offset, ignored_size = validate_tree_request(
        scope, [[kind, value] for kind, value in path], 0, 1)
    if not path:
        raise ValueError('cannot reveal the scope root')
    owner = providers[scope]()
    ancestors = set((id(owner),))
    nodes = []
    for depth, segment in enumerate(path):
        descriptors, unused = child_descriptors(
            owner, MAX_BRANCH, is_store_root=(depth == 0 and scope == 'store'))
        label = None
        for visible_segment, visible_label in descriptors:
            if visible_segment == segment:
                label = visible_label
                break
        if label is None:
            raise ValueError('path is not visible')
        value = read_child(owner, segment)
        if value is MISSING or id(value) in ancestors:
            raise ValueError('missing or cyclic path')
        nodes.append(_render_node(scope, path[:depth + 1], label, value, False))
        ancestors.add(id(value))
        owner = value
    return {'protocol': 1, 'scope': scope,
            'key': nodes[-1]['key'], 'chain': nodes}
