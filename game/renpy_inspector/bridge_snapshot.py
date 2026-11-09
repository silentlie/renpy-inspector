"""Bounded, read-only snapshots for the optional external inspector.

This module is Python 2.7 / 3 compatible and has no Ren'Py dependency.
It MUST only be called by the Ren'Py interaction thread, not an HTTP thread.
"""
from __future__ import unicode_literals

import json
import time

from .compat import string_types, to_text
from .favorites import format_location
from .inspection import MISSING, child_descriptors, clipped, read_child, snapshot

PROTOCOL = 1
MAX_NODES = 450
MAX_CHILDREN = 80
MAX_DEPTH = 4
MAX_TEXT = 160
MAX_JSON_BYTES = 256 * 1024


def _safe_text(value, limit=MAX_TEXT):
    """Only convert inspection-owned primitive labels, never raw game objects."""
    return clipped(to_text(value), limit)


def capture_scope(root, scope, budget):
    """Return nested JSON-safe metadata; no game object references escape."""
    nodes = []
    visited = [0]
    truncated = [False]

    def capture_children(owner, path, depth, ancestors, root_node=False):
        if visited[0] >= budget:
            truncated[0] = True
            return []
        try:
            descriptors, cut = child_descriptors(owner, MAX_CHILDREN,
                                                  is_store_root=(root_node and scope == 'store'))
        except Exception:
            return []
        if cut:
            truncated[0] = True
        result = []
        for segment, label in descriptors:
            if visited[0] >= budget:
                truncated[0] = True
                break
            child_path = path + (segment,)
            visited[0] += 1
            try:
                value = read_child(owner, segment)
                is_cycle = value is not MISSING and id(value) in ancestors
                state, type_name, preview, expandable, _ = snapshot(value, is_cycle=is_cycle)
            except Exception:
                state, type_name, preview, expandable = 'error', 'error', '<unavailable>', False
                value = MISSING
                is_cycle = False
            item = {
                'key': json.dumps([scope, child_path], ensure_ascii=True, separators=(',', ':')),
                'name': _safe_text(label, 90),
                'path': _safe_text(format_location(scope, child_path), 230),
                'type': _safe_text(type_name, 48),
                'preview': _safe_text(preview),
                'state': _safe_text(state, 18),
                'expandable': bool(expandable and not is_cycle),
                'children': [],
            }
            if expandable and not is_cycle and depth + 1 < MAX_DEPTH and visited[0] < budget:
                item['children'] = capture_children(value, child_path, depth + 1,
                                                    ancestors | {id(value)})
            elif expandable and not is_cycle:
                item['limited'] = True
                truncated[0] = True
            result.append(item)
        return result

    if root is not MISSING:
        nodes = capture_children(root, (), 0, frozenset((id(root),)), root_node=True)
    return nodes, visited[0], truncated[0]


def build_snapshot(providers, game_info=None, max_nodes=MAX_NODES):
    """Build one immutable metadata snapshot for the local bridge.

    Only the explicit Store/Persistent providers are evaluated. They must be
    trusted, no-argument callables. No arbitrary eval or mutation is possible.
    """
    if type(max_nodes) is not int or not 1 <= max_nodes <= MAX_NODES:
        raise ValueError('invalid snapshot budget')
    output = {
        'protocol': PROTOCOL,
        'captured_at': time.time(),
        'scopes': {},
        'counts': {},
        'truncated': {},
        'game': {},
    }
    if isinstance(game_info, dict):
        for key in ('game', 'version', 'filename', 'line'):
            value = game_info.get(key)
            if type(value) in (int, float) or isinstance(value, string_types):
                output['game'][key] = _safe_text(value)
    remaining = max_nodes
    for scope in ('store', 'persistent'):
        try:
            root = providers[scope]()
            nodes, count, cut = capture_scope(root, scope, remaining)
        except Exception:
            nodes, count, cut = [], 0, False
        output['scopes'][scope] = nodes
        output['counts'][scope] = count
        output['truncated'][scope] = cut
        remaining -= count
    return output


def encode_snapshot(snapshot_data):
    """Serialize an already-bounded, JSON-only snapshot into HTTP bytes."""
    data = json.dumps(snapshot_data, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    if len(data) > MAX_JSON_BYTES:
        raise ValueError('snapshot exceeds transport limit')
    return data
