"""Explicitly opted-in, compare-and-swap primitive editing on the game thread.

The only editable targets are existing built-in unicode/number/bool fields
stored directly in a Store module, a *plain* dictionary or a *plain* list.
Persistent state, custom objects, set members, custom accessors, type-changing
operations and creation/deletion are deliberately out of scope.

HTTP workers may validate JSON and queue a request, but MUST NOT resolve or
mutate gameplay objects. The game-thread tick performs resolution and writes.
Python 2.7 / Python 3 compatible; no eval, exec, pickle or untrusted repr.
"""
from __future__ import unicode_literals

import hashlib
import json
import math
import re
from types import ModuleType

from .bridge_paging import MAX_BRANCH, validate_tree_request
from .compat import text_type, integer_types
from .inspection import MISSING, child_descriptors, read_child

MAX_EDIT_TEXT = 1024
MAX_EDIT_BYTES = 4096
MAX_EDIT_INTEGER_BITS = 512
MAX_EDIT_PATH = 8
MAX_EDIT_REQUEST_BYTES = 6144
_HEX = re.compile(r'\A[a-f0-9]{64}\Z')
_INTEGER = re.compile(r'\A[+-]?[0-9]{1,160}\Z')
_FLOAT = re.compile(r'\A[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


class EditConflict(Exception):
    """Expected generation or exact primitive changed since the editor opened."""


class EditUnsupported(Exception):
    """The current location or primitive is not editable under the MVP rules."""


def validate_edit_request(payload):
    if type(payload) is not dict or set(payload) != set((
            'scope', 'path', 'generation', 'expected', 'type', 'text')):
        raise ValueError('invalid edit request fields')
    scope, path, unused_offset, unused_size = validate_tree_request(
        payload['scope'], payload['path'], 0, 1)
    if scope != 'store' or not 1 <= len(path) <= MAX_EDIT_PATH:
        raise ValueError('edits require a Store variable path')
    if any(kind == 'member' for kind, unused_value in path):
        raise ValueError('set members are not editable')
    if type(payload['generation']) is not int or not 0 <= payload['generation'] < 2 ** 53:
        raise ValueError('invalid edit generation')
    expected = payload['expected']
    if type(expected) is not text_type or _HEX.match(expected) is None:
        raise ValueError('invalid edit precondition')
    typename = payload['type']
    if type(typename) is not text_type or typename not in ('str', 'unicode', 'int', 'long', 'float', 'bool'):
        raise ValueError('invalid edit primitive type')
    value = payload['text']
    if type(value) is not text_type or len(value) > MAX_EDIT_TEXT:
        raise ValueError('invalid edit value')
    try:
        if len(value.encode('utf-8')) > MAX_EDIT_BYTES:
            raise ValueError('edit exceeds UTF-8 budget')
    except UnicodeError:
        raise ValueError('invalid Unicode edit value')
    return scope, path, payload['generation'], expected, typename, value


def _scalar(value):
    """Return a bounded exact (kind, text), or None. No user code executes."""
    kind = type(value)
    if kind is text_type:
        if len(value) <= MAX_EDIT_TEXT:
            try:
                if len(value.encode('utf-8')) <= MAX_EDIT_BYTES:
                    return kind.__name__, value
            except UnicodeError:
                pass
        return None
    if kind is bool:
        return 'bool', 'True' if value else 'False'
    if kind in integer_types:
        if value.bit_length() <= MAX_EDIT_INTEGER_BITS:
            return kind.__name__, str(value)
        return None
    if kind is float and not math.isnan(value) and not math.isinf(value):
        return 'float', repr(value)
    return None


def _fingerprint(kind, text):
    # Fingerprint binds the exact prior value and built-in type, not a preview.
    return hashlib.sha256((kind + '\x00' + text).encode('utf-8')).hexdigest()


def _target(providers, scope, path):
    """Revalidate every descriptor; reject arbitrary user objects and writes."""
    if scope != 'store':
        raise EditUnsupported('Only Store variables can be edited')
    owner = providers['store']()
    if not isinstance(owner, ModuleType):
        raise EditUnsupported('Store provider is not a plain module')
    for depth, segment in enumerate(path):
        kind, key = segment
        # All intermediates must be built-in containers or the trusted module.
        if isinstance(owner, ModuleType):
            if depth != 0 or kind != 'attribute':
                raise EditUnsupported('Only direct Store module fields are allowed')
        elif type(owner) is dict:
            if kind != 'key':
                raise EditUnsupported('Only plain dictionary keys are editable')
        elif type(owner) is list:
            if kind != 'index':
                raise EditUnsupported('Only plain list elements are editable')
        else:
            raise EditUnsupported('Custom objects and immutable containers are not editable')
        visible, unused = child_descriptors(
            owner, MAX_BRANCH, is_store_root=(depth == 0))
        if segment not in [entry[0] for entry in visible]:
            raise EditConflict('Variable is no longer visible')
        child = read_child(owner, segment)
        if child is MISSING:
            raise EditConflict('Variable no longer exists')
        if depth == len(path) - 1:
            return owner, segment, child
        owner = child
    raise EditUnsupported('Editing a scope root is forbidden')


def inspect_edit_target(providers, scope, path):
    """Explicit GET; never expose or retain a reference to the game object."""
    scope, path, unused_offset, unused_size = validate_tree_request(
        scope, [[kind, value] for kind, value in path], 0, 1)
    result = {
        'protocol': 1, 'scope': scope, 'key': json.dumps(
            [scope, path], ensure_ascii=True, separators=(',', ':')),
        'editable': False,
    }
    try:
        unused_parent, unused_segment, current = _target(providers, scope, path)
        scalar = _scalar(current)
        if scalar is None:
            raise EditUnsupported('Only bounded built-in primitives are editable')
        typename, text = scalar
        if typename not in ('str', 'unicode', 'int', 'long', 'float', 'bool'):
            raise EditUnsupported('Primitive type is not editable')
        result.update({'editable': True, 'type': typename, 'text': text,
                       'expected': _fingerprint(typename, text),
                       'max_chars': MAX_EDIT_TEXT})
    except (EditUnsupported, EditConflict) as reason:
        result['reason'] = str(reason)
    return result


def _parse_candidate(typename, text, original):
    if typename != type(original).__name__:
        raise EditConflict('Variable type changed')
    if typename in ('str', 'unicode'):
        # Python 2 byte strings are intentionally NOT exposed as editable.
        if type(original) is not text_type:
            raise EditUnsupported('Byte strings are not editable')
        return text
    if typename == 'bool':
        if text not in ('True', 'False'):
            raise ValueError('Boolean must be True or False')
        return text == 'True'
    if typename in ('int', 'long'):
        if _INTEGER.match(text) is None:
            raise ValueError('Integer must be a decimal literal')
        value = type(original)(text, 10)
        if value.bit_length() > MAX_EDIT_INTEGER_BITS:
            raise ValueError('Integer exceeds edit limit')
        return value
    if typename == 'float':
        if len(text) > 160 or _FLOAT.match(text) is None:
            raise ValueError('Float must be a finite decimal')
        value = float(text)
        if math.isnan(value) or math.isinf(value):
            raise ValueError('Float must be finite')
        return value
    raise EditUnsupported('Unsupported primitive type')


def apply_primitive_edit(providers, scope, path, expected, typename, text):
    """Run only on Ren'Py's interaction thread after epoch validation."""
    scope, path, unused_offset, unused_size = validate_tree_request(
        scope, [[kind, value] for kind, value in path], 0, 1)
    owner, segment, current = _target(providers, scope, path)
    scalar = _scalar(current)
    if scalar is None:
        raise EditConflict('Variable is no longer a supported primitive')
    kind, old_text = scalar
    if kind != typename or _fingerprint(kind, old_text) != expected:
        raise EditConflict('Variable value or type changed')
    candidate = _parse_candidate(typename, text, current)
    if type(candidate) is not type(current):
        raise EditUnsupported('Type-changing writes are forbidden')
    candidate_scalar = _scalar(candidate)
    # Equality alone collapses +0.0 and -0.0, although their IEEE-754 sign
    # bits differ and are observable (for example via copysign or division).
    # Compare the exact supported scalar representation instead.
    if candidate_scalar == scalar:
        raise ValueError('No change to apply')
    last_kind, key = segment
    if isinstance(owner, ModuleType) and last_kind == 'attribute':
        fields = ModuleType.__getattribute__(owner, '__dict__')
        dict.__setitem__(fields, key, candidate)
    elif type(owner) is dict and last_kind == 'key':
        dict.__setitem__(owner, key, candidate)
    elif type(owner) is list and last_kind == 'index':
        list.__setitem__(owner, key, candidate)
    else:
        raise EditUnsupported('Target is not a writable built-in container')
    return {'protocol': 1, 'applied': True, 'type': typename,
            'before': old_text, 'after': candidate_scalar[1]}
