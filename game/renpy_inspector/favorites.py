"""Serializable, root-relative locations for explicit variable watches.

Never retain inspected objects. Supported keys are string, integer, bool and None;
all other dictionary keys and set members remain inspection-only.
"""

MAX_FAVORITES = 100
MAX_SEGMENTS = 12
MAX_STRING = 256
ROOTS = ('store', 'persistent')


def valid_scope(scope):
    """Named roots use a strict identifier, never a Python expression."""
    if scope in ROOTS or scope == 'favorites':
        return True
    if type(scope) is not str or not scope.startswith('named:'):
        return False
    import re
    return (len(scope) <= 70 and re.fullmatch(
        r'named:[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*', scope
    ) is not None)



def _encode_key(value):
    if value is None:
        return {'type': 'none', 'value': None}
    if type(value) is bool:
        return {'type': 'bool', 'value': value}
    if type(value) is int:
        return {'type': 'int', 'value': value}
    if type(value) is str and len(value) <= MAX_STRING:
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
        if kind == 'attribute' and type(value) is str and 0 < len(value) <= MAX_STRING:
            parts.append({'kind': 'attribute', 'name': value})
        elif kind == 'index' and type(value) is int and 0 <= value <= 1000000:
            parts.append({'kind': 'index', 'index': value})
        elif kind == 'key':
            parts.append({'kind': 'key', 'key': _encode_key(value)})
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
        elif kind == 'key':
            key = part.get('key')
            if not isinstance(key, dict):
                raise ValueError('invalid key')
            tag, val = key.get('type'), key.get('value')
            if tag == 'str' and type(val) is str:
                pass
            elif tag == 'int' and type(val) is int:
                pass
            elif tag == 'bool' and type(val) is bool:
                pass
            elif tag == 'none' and val is None:
                pass
            else:
                raise ValueError('invalid typed dictionary key')
            segment = ('key', val)
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
            text += '.' + value
        elif kind == 'index':
            text += '[' + str(value) + ']'
        else:
            text += '[' + repr(value) + ']'
    return text
