"""Conservative, read-only inspection of game-owned Python values.

This module does not import Ren'Py. It never calls user-defined repr, str,
iteration, properties, or __getattr__ intentionally. As with all Python
introspection, hostile extension types cannot be made completely safe.
"""

from __future__ import annotations

from itertools import islice
from types import ModuleType, FunctionType, BuiltinFunctionType, MethodType


MISSING = object()
_SIMPLE_KEYS = (str, int, bool, type(None))
_SCALARS = (str, bytes, int, float, bool, type(None))
_NON_EXPANDABLE = (type, FunctionType, BuiltinFunctionType, MethodType, ModuleType)


def escape_text(value: str) -> str:
    """Protect text tags and interpolation in the Ren'Py text renderer."""
    return value.replace("[", "[[").replace("{", "{{").replace("〖", "〖〖")


def clipped(value: str, limit: int = 110) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _instance_dict(value):
    """Direct instance storage only. Never follow a property or __getattr__."""
    try:
        data = object.__getattribute__(value, "__dict__")
        return data if isinstance(data, dict) else None
    except (AttributeError, TypeError):
        return None


def _mapping(value):
    if isinstance(value, ModuleType):
        # A normal module's namespace, including Ren'Py's default store.
        return vars(value)
    if isinstance(value, _NON_EXPANDABLE):
        return None
    return _instance_dict(value)


def _is_expandable(value) -> bool:
    if isinstance(value, (dict, list, tuple)):
        return True
    return _mapping(value) is not None


def read_child(parent, segment):
    """Return a child without performing arbitrary attribute lookup."""
    kind, key = segment
    if kind == "attribute":
        fields = _mapping(parent)
        if fields is None:
            return MISSING
        return dict.get(fields, key, MISSING)
    if kind == "key" and isinstance(parent, dict):
        try:
            return dict.__getitem__(parent, key)
        except KeyError:
            return MISSING
    if kind == "index" and isinstance(parent, (list, tuple)):
        try:
            return list.__getitem__(parent, key) if isinstance(parent, list) else tuple.__getitem__(parent, key)
        except IndexError:
            return MISSING
    return MISSING


def child_descriptors(value, limit: int, is_store_root: bool = False):
    """Return (segment, label) pairs, plus a truncation indicator.

    Uses at most 4 * limit dictionary keys, and at most limit visible nodes.
    Object-keyed dictionaries are deliberately omitted in this first MVP.
    """
    if isinstance(value, (list, tuple)):
        size = list.__len__(value) if isinstance(value, list) else tuple.__len__(value)
        n = min(size, limit)
        return [(('index', i), '[{}]'.format(i)) for i in range(n)], size > n

    if isinstance(value, dict):
        size = dict.__len__(value)
        pairs = []
        for key in islice(dict.keys(value), limit * 4):
            if type(key) not in _SIMPLE_KEYS:
                continue
            label = '[' + clipped(repr(key), 40) + ']'
            pairs.append((('key', key), label))
            if len(pairs) == limit:
                break
        return pairs, size > len(pairs)

    fields = _mapping(value)
    if fields is None:
        return [], False
    # Key names from __dict__ are Python attributes; filter internal store names.
    names = []
    count = 0
    for key in dict.keys(fields):
        if not isinstance(key, str) or key.startswith('_'):
            continue
        if is_store_root:
            member = dict.__getitem__(fields, key)
            if isinstance(member, _NON_EXPANDABLE):
                continue
        count += 1
        if len(names) < limit:
            names.append((('attribute', key), clipped(key, 60)))
    # Sorting only the bounded prefix is deliberate.  We do not sort an
    # arbitrarily large store on every poll.
    names.sort(key=lambda item: item[0][1].casefold())
    return names, count > len(names)


def snapshot(value, *, is_cycle: bool = False):
    """Return (state, type_name, preview, expandable, comparison_token)."""
    if value is MISSING:
        return ('missing', 'missing', '<missing>', False, ('missing',))
    if is_cycle:
        return ('cycle', type(value).__name__, '<cycle>', False, ('cycle', id(value)))

    typ = type(value)
    name = typ.__name__
    if typ in _SCALARS:
        try:
            if typ is str or typ is bytes:
                preview = repr(value[:100])
                if len(value) > 100:
                    preview += '…'
            elif typ is int:
                preview = str(value)
            else:
                preview = repr(value)
        except Exception:
            preview = '<unavailable>'
        return ('value', name, clipped(preview), False, (name, preview))

    if isinstance(value, (list, tuple, dict)):
        size = (list.__len__(value) if isinstance(value, list) else
                tuple.__len__(value) if isinstance(value, tuple) else dict.__len__(value))
        preview = '{} item{}'.format(size, '' if size == 1 else 's')
        return ('value', name, preview, True, (name, id(value), size))

    if isinstance(value, (set, frozenset)):
        size = set.__len__(value) if isinstance(value, set) else frozenset.__len__(value)
        return ('value', name, '{} items (not expandable)'.format(size), False, (name, id(value), size))

    if isinstance(value, ModuleType):
        return ('value', name, '<module>', False, (name, id(value)))

    fields = _mapping(value)
    if fields is not None:
        size = dict.__len__(fields)
        return ('value', name, '{} attribute{}'.format(size, '' if size == 1 else 's'), True,
                (name, id(value), size))
    return ('value', name, '<{}>'.format(name), False, (name, id(value)))
