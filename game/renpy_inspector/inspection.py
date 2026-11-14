"""Conservative, read-only inspection of game-owned Python values.

This module does not import Ren'Py. It never calls user-defined repr, str,
iteration, properties, or __getattr__ intentionally. As with all Python
introspection, hostile extension types cannot be made completely safe.
"""

from __future__ import unicode_literals

from itertools import islice
from .compat import integer_types, string_types, iter_keys, fold_text, to_text, binary_type
from types import ModuleType, FunctionType, BuiltinFunctionType, MethodType
from .safe_slots import MAX_SLOT_FIELDS, read_safe_slot, safe_slot_values


MISSING = object()
_SIMPLE_KEYS = string_types + integer_types + (bool, type(None))
# Set membership paths are value-based, not iteration-position based.
# Limit representable set elements to JSON-safe scalar values. Other elements
# stay in the displayed total but cannot be opened or pinned.
MAX_SET_MEMBER_TEXT = 256
MAX_SET_MEMBER_INTEGER = 9007199254740991  # JavaScript's safe-integer limit


def _safe_set_member(value):
    typ = type(value)
    if typ not in _SIMPLE_KEYS:
        return False
    if typ in integer_types:
        return abs(value) <= MAX_SET_MEMBER_INTEGER
    if typ in string_types:
        if len(value) > MAX_SET_MEMBER_TEXT:
            return False
        # Python 2 str can contain invalid UTF-8. Never expose a lossy or
        # unroundtrippable typed path for such a member.
        try:
            if typ is binary_type:
                value.decode('utf-8')
            else:
                value.encode('utf-8')
        except UnicodeError:
            return False
    return True
_SCALARS = string_types + integer_types + (float, bool, type(None))
_NON_EXPANDABLE = (type, FunctionType, BuiltinFunctionType, MethodType, ModuleType)


def escape_text(value):
    """Protect text tags and interpolation in the Ren'Py text renderer."""
    return value.replace("[", "[[").replace("{", "{{").replace("\u3016", "\u3016\u3016")


def clipped(value, limit=110):
    return value if len(value) <= limit else value[: limit - 1] + "\u2026"


def _has_builtin_base(value, classes):
    """Inspect the real type's hierarchy, not an instance-supplied __class__."""
    return issubclass(type(value), classes)


def _instance_dict(value):
    """Direct instance storage only. Never follow a property or __getattr__."""
    try:
        data = object.__getattribute__(value, str("__dict__"))
        return data if _has_builtin_base(data, dict) else None
    except (AttributeError, TypeError):
        return None


def _mapping(value):
    if _has_builtin_base(value, ModuleType):
        # A normal module's namespace, including Ren'Py's default store.
        return vars(value)
    if _has_builtin_base(value, _NON_EXPANDABLE):
        return None
    return _instance_dict(value)


def _is_expandable(value):
    if _has_builtin_base(value, (dict, list, tuple)):
        return True
    if _mapping(value) is not None:
        return True
    return bool(safe_slot_values(value)[0])


def read_child(parent, segment):
    """Return a child without performing arbitrary attribute lookup."""
    kind, key = segment
    if kind == "attribute":
        fields = _mapping(parent)
        if fields is not None:
            current = dict.get(fields, key, MISSING)
            if current is not MISSING:
                return current
        # Only a native member_descriptor declared by a plain Python class
        # __slots__ can be read, never a computed property or game getter.
        return read_safe_slot(parent, key)
    if kind == "member" and _has_builtin_base(parent, (set, frozenset)):
        if not _safe_set_member(key):
            return MISSING
        # Use built-in containment, never game-defined __iter__/__contains__.
        # The descriptor check at each parent rejects unenumerated members.
        found = (set.__contains__(parent, key) if _has_builtin_base(parent, set)
                 else frozenset.__contains__(parent, key))
        return key if found else MISSING
    if kind == "key" and _has_builtin_base(parent, dict):
        try:
            return dict.__getitem__(parent, key)
        except KeyError:
            return MISSING
    if kind == "index" and _has_builtin_base(parent, (list, tuple)):
        try:
            return list.__getitem__(parent, key) if _has_builtin_base(parent, list) else tuple.__getitem__(parent, key)
        except IndexError:
            return MISSING
    return MISSING


def child_descriptors(value, limit, is_store_root=False):
    """Return (segment, label) pairs, plus a truncation indicator.

    Uses at most 4 * limit dictionary keys, and at most limit visible nodes.
    Object-keyed dictionaries are deliberately omitted in this first MVP.
    """
    if _has_builtin_base(value, (list, tuple)):
        size = list.__len__(value) if _has_builtin_base(value, list) else tuple.__len__(value)
        n = min(size, limit)
        return [(('index', i), '[{}]'.format(i)) for i in range(n)], size > n

    if _has_builtin_base(value, (set, frozenset)):
        size = (set.__len__(value) if _has_builtin_base(value, set)
                else frozenset.__len__(value))
        scan = set.__iter__(value) if _has_builtin_base(value, set) else frozenset.__iter__(value)
        pairs = []
        for member in islice(scan, limit * 4):
            if not _safe_set_member(member):
                continue
            label = '{' + clipped(repr(member), 40) + '}'
            pairs.append((('member', member), label))
        # Never use set iteration positions as IDs. Sort the bounded scalar
        # prefix to keep pagination stable when membership has not changed.
        pairs.sort(key=lambda pair: (type(pair[0][1]).__name__, repr(pair[0][1])))
        return pairs[:limit], size > len(pairs) or len(pairs) > limit

    if _has_builtin_base(value, dict):
        size = dict.__len__(value)
        pairs = []
        for key in islice(iter_keys(value), limit * 4):
            if type(key) not in _SIMPLE_KEYS:
                continue
            label = '[' + clipped(repr(key), 40) + ']'
            pairs.append((('key', key), label))
            if len(pairs) == limit:
                break
        return pairs, size > len(pairs)

    fields = _mapping(value)
    # Slot values are read only via exact native member descriptors; discovery
    # examines static class dictionaries, never arbitrary Python getters.
    slots, slot_truncated = safe_slot_values(value, min(limit, MAX_SLOT_FIELDS))
    if fields is None and not slots:
        return [], slot_truncated
    # Key names from __dict__ are Python attributes; filter internal store names.
    names = []
    count = 0
    if fields is not None:
        for key in islice(iter_keys(fields), limit * 4):
            if not isinstance(key, string_types) or key.startswith('_'):
                continue
            if is_store_root:
                member = dict.__getitem__(fields, key)
                if _has_builtin_base(member, _NON_EXPANDABLE):
                    continue
            count += 1
            if len(names) < limit:
                names.append((('attribute', key), clipped(key, 60)))
    for name, unused_value in slots:
        if fields is not None and dict.__contains__(fields, name):
            continue
        count += 1
        if len(names) < limit:
            names.append((('attribute', name), clipped(name, 60)))
    # Sorting only the bounded prefix is deliberate.  We do not sort an
    # arbitrarily large store on every poll.
    names.sort(key=lambda item: fold_text(item[0][1]))
    field_truncated = fields is not None and dict.__len__(fields) > limit * 4
    return names, count > len(names) or field_truncated or slot_truncated


def snapshot(value, is_cycle=False):
    """Return (state, type_name, preview, expandable, comparison_token)."""
    if value is MISSING:
        return ('missing', 'missing', '<missing>', False, ('missing',))
    if is_cycle:
        return ('cycle', type(value).__name__, '<cycle>', False, ('cycle', id(value)))

    typ = type(value)
    name = typ.__name__
    if typ in _SCALARS:
        try:
            if typ in string_types:
                preview = repr(value[:100])
                if len(value) > 100:
                    preview += '\u2026'
            elif typ in integer_types:
                preview = str(value)
            else:
                preview = repr(value)
        except Exception:
            preview = '<unavailable>'
        return ('value', name, clipped(preview), False, (name, preview))

    if _has_builtin_base(value, (list, tuple, dict)):
        size = (list.__len__(value) if _has_builtin_base(value, list) else
                tuple.__len__(value) if _has_builtin_base(value, tuple) else dict.__len__(value))
        preview = '{} item{}'.format(size, '' if size == 1 else 's')
        return ('value', name, preview, True, (name, id(value), size))

    if _has_builtin_base(value, (set, frozenset)):
        size = set.__len__(value) if _has_builtin_base(value, set) else frozenset.__len__(value)
        return ('value', name, '{} item{} (bounded scalar members)'.format(
            size, '' if size == 1 else 's'), size > 0, (name, id(value), size))

    if _has_builtin_base(value, ModuleType):
        return ('value', name, '<module>', False, (name, id(value)))

    fields = _mapping(value)
    slots, slots_limited = safe_slot_values(value)
    if fields is not None or slots:
        size = dict.__len__(fields) if fields is not None else 0
        size += sum(1 for field, unused in slots
                    if fields is None or not dict.__contains__(fields, field))
        prefix = '{}+'.format(size) if slots_limited else str(size)
        preview = '{} attribute{}{}'.format(
            prefix, '' if size == 1 and not slots_limited else 's',
            ' (bounded slots)' if slots_limited else '')
        return ('value', name, preview, fields is not None or bool(slots),
                (name, id(value), size, slots_limited))
    return ('value', name, '<{}>'.format(name), False, (name, id(value)))
