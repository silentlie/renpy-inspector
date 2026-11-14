"""Bounded, descriptor-free discovery of plain Python __slots__ storage.

Never call getattr(instance, name), inspect.getmembers, a property, or a
game-defined descriptor. The only slot reads are via CPython's exact built-in
member_descriptor type, after checking an actual class __slots__ declaration.
The class hierarchy and candidate counts are deliberately bounded. Python 2
new-style objects and Python 3 are supported.
"""
from __future__ import unicode_literals

from types import MemberDescriptorType

from .compat import string_types

MAX_SLOT_MRO = 12
MAX_SLOT_NAMES_PER_CLASS = 96
MAX_SLOT_FIELDS = 48
MAX_SLOT_NAME_CHARS = 80


def _static_class_dict(base):
    """Bypass metaclass overrides of __getattribute__."""
    try:
        return type.__getattribute__(base, '__dict__')
    except (AttributeError, TypeError):
        return None


def _declared_names(declaration):
    """Accept only actual built-in str/tuple/list declarations, never iterables."""
    if type(declaration) in string_types:
        return (declaration,), False
    if type(declaration) not in (tuple, list):
        return (), False
    count = len(declaration)
    return declaration[:MAX_SLOT_NAMES_PER_CLASS], count > MAX_SLOT_NAMES_PER_CLASS


def safe_slot_descriptors(value, limit=MAX_SLOT_FIELDS):
    """Return a bounded list of (public_name, native_descriptor), limited.

    Derived class attributes shadow inherited slots. Even class-level
    properties or custom descriptors are only *examined* as static metadata,
    not accessed on instances. Extension-defined members are excluded unless
    the owner declares them with a built-in __slots__ declaration.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_SLOT_FIELDS:
        raise ValueError('invalid slot discovery limit')
    try:
        hierarchy = type.__getattribute__(type(value), '__mro__')
    except (AttributeError, TypeError):
        return [], False
    if type(hierarchy) is not tuple:
        return [], False

    truncated = len(hierarchy) > MAX_SLOT_MRO
    seen_class_dicts = []
    found = []
    for base in hierarchy[:MAX_SLOT_MRO]:
        fields = _static_class_dict(base)
        if fields is None:
            continue
        declaration = fields['__slots__'] if '__slots__' in fields else ()
        names, cut = _declared_names(declaration)
        truncated = truncated or cut
        for name in names:
            if (type(name) not in string_types or not name or
                    len(name) > MAX_SLOT_NAME_CHARS or name.startswith('_')):
                continue
            if any(name in derived for derived in seen_class_dicts):
                # A more derived class may expose a property with this name.
                # Do not sidestep that override to access an inherited slot.
                continue
            descriptor = fields[name] if name in fields else None
            if type(descriptor) is not MemberDescriptorType:
                continue
            if len(found) < limit:
                found.append((name, descriptor))
            else:
                truncated = True
        seen_class_dicts.append(fields)
    return found, truncated


def safe_slot_values(value, limit=MAX_SLOT_FIELDS):
    """Read only initialized native slot storage; return (name, value) pairs."""
    descriptors, truncated = safe_slot_descriptors(value, limit)
    result = []
    for name, descriptor in descriptors:
        try:
            # Calling the *exact built-in* slot descriptor does not dispatch
            # user-defined __getattribute__, __getattr__ or properties.
            current = MemberDescriptorType.__get__(descriptor, value, type(value))
        except (AttributeError, TypeError):
            continue
        result.append((name, current))
    return result, truncated


def read_safe_slot(value, key):
    """Read a visible native slot by name, or report absence without lookup."""
    from .inspection import MISSING
    if type(key) not in string_types:
        return MISSING
    descriptors, unused = safe_slot_descriptors(value)
    for name, descriptor in descriptors:
        if key == name:
            try:
                return MemberDescriptorType.__get__(descriptor, value, type(value))
            except (AttributeError, TypeError):
                return MISSING
    return MISSING
