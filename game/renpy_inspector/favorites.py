"""Serializable, root-relative locations for explicit variable watches.

Never retain inspected objects. Supported keys are string, integer, bool and None;
all other dictionary keys and non-scalar set members remain inspection-only.
"""

from __future__ import unicode_literals

import re
from .compat import integer_types, string_types, to_text

MAX_FAVORITES = 100
MAX_SEGMENTS = 12
MAX_STRING = 256
ROOTS = ('store', 'persistent')


def valid_scope(scope):
    """Named roots use a strict identifier, never a Python expression."""
    if scope in ROOTS or scope == 'favorites':
        return True
    if not isinstance(scope, string_types) or not scope.startswith('named:'):
        return False
    return (len(scope) <= 70 and re.match(
        r'\Anamed:[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\Z', scope
    ) is not None)



def _encode_key(value):
    if value is None:
        return {'type': 'none', 'value': None}
    if type(value) is bool:
        return {'type': 'bool', 'value': value}
    if type(value) in integer_types:
        return {'type': 'int', 'value': value}
    if isinstance(value, string_types) and len(value) <= MAX_STRING:
        return {'type': 'str', 'value': value}
    raise ValueError('unsupported dictionary key')


def encode_location(scope, path):
    """Validate and convert a root + path to a JSON-safe object."""
    if not valid_scope(scope) or scope == 'favorites' or not isinstance(path, (tuple, list)) or not 1 <= len(path) <= MAX_SEGMENTS:
        raise ValueError('invalid favourite root or path length')
    parts = []
    for segment in path:
        if not isinstance(segment, (tuple, list)) or len(segment) != 2:
            raise ValueError('invalid path segment')
        kind, value = segment
        if kind == 'attribute' and isinstance(value, string_types) and 0 < len(value) <= MAX_STRING:
            parts.append({'kind': 'attribute', 'name': value})
        elif kind == 'index' and type(value) in integer_types and 0 <= value <= 1000000:
            parts.append({'kind': 'index', 'index': value})
        elif kind == 'key':
            parts.append({'kind': 'key', 'key': _encode_key(value)})
        elif kind == 'member':
            # A stable scalar value identifies membership; never record the
            # unpredictable iteration position of a Python set.
            from .inspection import _safe_set_member
            if not _safe_set_member(value):
                raise ValueError('unsupported set member')
            parts.append({'kind': 'member', 'key': _encode_key(value)})
        else:
            raise ValueError('unsupported favourite segment')
    return {'root': scope, 'segments': parts}


def decode_location(data):
    """Validate untrusted JSON and return a (root, path) pair."""
    if not isinstance(data, dict):
        raise ValueError('location must be an object')
    scope = data.get('root')
    parts = data.get('segments')
    if not valid_scope(scope) or scope == 'favorites' or not isinstance(parts, list) or not 1 <= len(parts) <= MAX_SEGMENTS:
        raise ValueError('invalid location')
    path = []
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError('invalid location segment')
        kind = part.get('kind')
        if kind == 'attribute':
            segment = ('attribute', part.get('name'))
        elif kind == 'index':
            segment = ('index', part.get('index'))
        elif kind in ('key', 'member'):
            key = part.get('key')
            if not isinstance(key, dict):
                raise ValueError('invalid key')
            tag, val = key.get('type'), key.get('value')
            if tag == 'str' and isinstance(val, string_types):
                pass
            elif tag == 'int' and type(val) in integer_types and type(val) is not bool:
                pass
            elif tag == 'bool' and type(val) is bool:
                pass
            elif tag == 'none' and val is None:
                pass
            else:
                raise ValueError('invalid typed dictionary key')
            segment = (kind, val)
        else:
            raise ValueError('invalid segment kind')
        path.append(segment)
    path = tuple(path)
    # Round-trip through validation to reject out-of-bounds keys and attributes.
    encode_location(scope, path)
    return scope, path


def format_location(scope, path):
    """Create a human-readable path, leaving Ren'Py escaping to the renderer."""
    text = "store." + scope[6:] if scope.startswith("named:") else scope
    for kind, value in path:
        if kind == 'attribute':
            text += '.' + to_text(value)
        elif kind == 'index':
            text += '[' + str(value) + ']'
        elif kind == 'member':
            text += '{' + to_text(repr(value)) + '}'
        else:
            text += '[' + to_text(repr(value)) + ']'
    return text
