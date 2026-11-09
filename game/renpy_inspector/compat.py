"""Python 2.7 / 3.x shims shared by both Ren'Py release packages.

Keep all version-specific interpreter work here. This module imports no Ren'Py
objects, and the inspector's other modules use the same source in both ZIPs.
"""
from __future__ import unicode_literals

import os
import sys
import time

PY2 = sys.version_info[0] == 2

if PY2:
    text_type = unicode
    binary_type = str
    integer_types = (int, long)
    string_types = (str, unicode)
else:
    text_type = str
    binary_type = bytes
    integer_types = (int,)
    string_types = (str,)


def iter_keys(mapping):
    """Never allocate a full dictionary key list on Python 2."""
    # Call the built-in dict method, bypassing a game subclass __iter__.
    return dict.iterkeys(mapping) if PY2 else iter(dict.keys(mapping))


def fold_text(value):
    """Unicode-insensitive matching with the best case-fold available."""
    value = to_text(value)
    casefold = getattr(value, 'casefold', None)
    return casefold() if casefold is not None else value.lower()


def to_text(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        try:
            return value.decode('utf-8', 'replace')
        except (AttributeError, UnicodeError):
            pass
    return text_type(value)


def monotonic_time():
    timer = getattr(time, 'perf_counter', None)
    if timer is None:
        timer = getattr(time, 'monotonic', None)
    return timer() if timer is not None else time.time()


def atomic_replace(source, destination):
    """Replace a settings file atomically, including on Python 2 Windows.

    Python 2's os.rename refuses to overwrite existing files on Windows. Use
    MoveFileExW instead of deleting the destination first and risking data loss.
    """
    replacement = getattr(os, 'replace', None)
    if replacement is not None:
        return replacement(source, destination)
    if os.name != 'nt':
        return os.rename(source, destination)
    import ctypes
    import ctypes.wintypes
    move = ctypes.windll.kernel32.MoveFileExW
    move.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.wintypes.DWORD)
    move.restype = ctypes.wintypes.BOOL
    # MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH.
    if not move(to_text(source), to_text(destination), 0x1 | 0x8):
        raise ctypes.WinError()
