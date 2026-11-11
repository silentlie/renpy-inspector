"""Bounded, read-only Ren'Py label navigation and local .rpy excerpts.

Only Ren'Py's interaction thread calls these functions. The HTTP worker
queues validated, primitive arguments. No jump, warp, execution, arbitrary
filesystem access, or mutation of gameplay is available through this API.
Compatible with both Python 2.7 (Ren'Py 7) and Python 3 (Ren'Py 8).
"""
from __future__ import unicode_literals

import io
import os
from itertools import islice

from .compat import integer_types, string_types
from .bridge_snapshot import _safe_text

MAX_LABEL_SCAN = 4000
LABEL_PAGE_SIZE = 40
MAX_LABEL_OFFSET = 3960
MAX_QUERY = 64
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_LINE = 100000
SOURCE_CONTEXT = 10
MAX_SOURCE_LINE_LENGTH = 240


def validate_label_request(query, offset, size):
    if not isinstance(query, string_types):
        raise ValueError('label query must be text')
    query = query.strip()
    if len(query) > MAX_QUERY or any(ord(c) < 32 for c in query):
        raise ValueError('invalid label query')
    if type(offset) is not int or offset < 0 or offset > MAX_LABEL_OFFSET:
        raise ValueError('invalid label offset')
    if type(size) is not int or not 1 <= size <= LABEL_PAGE_SIZE:
        raise ValueError('invalid label page size')
    return query, offset, size


def _script_file(filename, game_dir):
    """Return a safe path relative to gamedir, or None for engine files.

    Absolute paths are accepted only when already inside this game's directory.
    All source reads revalidate the final path using realpath.
    """
    if not isinstance(filename, string_types) or not game_dir:
        return None
    if not filename or len(filename) > 360 or '\x00' in filename:
        return None
    # Ren'Py metadata may include game/ even when config.gamedir already
    # resolves to the actual game directory.
    normalized = filename.replace('\\', '/')
    if normalized.startswith('game/'):
        normalized = normalized[5:]
    if os.path.isabs(normalized):
        candidate = os.path.realpath(normalized)
    else:
        parts = normalized.split('/')
        if any(part in ('', '.', '..') for part in parts):
            return None
        candidate = os.path.realpath(os.path.join(game_dir, *parts))
    root = os.path.realpath(game_dir)
    if not candidate.startswith(root + os.sep):
        return None
    rel = os.path.relpath(candidate, root).replace(os.sep, '/')
    if rel.startswith('../') or not rel.lower().endswith('.rpy'):
        return None
    return rel


def validate_source_request(filename, line):
    if not isinstance(filename, string_types) or len(filename) > 360 or not filename:
        raise ValueError('invalid script filename')
    if '\x00' in filename or '\\' in filename or filename.startswith('/'):
        raise ValueError('invalid script filename')
    parts = filename.split('/')
    if any(part in ('', '.', '..') for part in parts) or not filename.lower().endswith('.rpy'):
        raise ValueError('invalid script filename')
    if type(line) not in integer_types or type(line) is bool or not 1 <= line <= MAX_SOURCE_LINE:
        raise ValueError('invalid script line')
    return filename, line


def list_labels(renpy_api, game_dir, query='', offset=0, size=LABEL_PAGE_SIZE):
    """Return bounded label metadata, not game objects or AST instances."""
    query, offset, size = validate_label_request(query, offset, size)
    if renpy_api is None:
        raise ValueError('RenPy runtime not connected')
    raw = renpy_api.get_all_labels()
    candidates = []
    truncated = False
    for label in raw:
        if not isinstance(label, string_types) or not 1 <= len(label) <= 160:
            continue
        if label.startswith('_') or any(ord(c) < 32 for c in label):
            continue
        if len(candidates) >= MAX_LABEL_SCAN:
            truncated = True
            break
        candidates.append(label)
    candidates.sort(key=lambda name: name.lower())
    entries = []
    match_count = 0
    scanned = 0
    seen = set()
    script = getattr(getattr(renpy_api, 'game', None), 'script', None)
    if script is None:
        raise ValueError('RenPy script not available')
    for label in candidates:
        if label in seen:
            continue
        seen.add(label)
        scanned += 1
        try:
            node = script.lookup(label)
            filename = _script_file(getattr(node, 'filename', None), game_dir)
            line = getattr(node, 'linenumber', None)
            if not filename or type(line) not in integer_types or not 1 <= line <= MAX_SOURCE_LINE:
                continue
        except Exception:
            continue
        if query and query.lower() not in label.lower() and query.lower() not in filename.lower():
            continue
        if match_count >= offset and len(entries) < size:
            entries.append({'name': _safe_text(label, 160),
                            'file': _safe_text(filename, 230), 'line': int(line)})
        match_count += 1
    return {'protocol': 1, 'labels': entries, 'query': query,
            'offset': offset, 'next_offset': offset + len(entries),
            'more': match_count > offset + len(entries),
            'limited': bool(truncated), 'scanned': scanned,
            'total_matches': match_count}


def source_excerpt(game_dir, filename, line):
    """Read a tiny source window from a game-owned .rpy, never arbitrary files."""
    filename, line = validate_source_request(filename, line)
    if not game_dir:
        return {'protocol': 1, 'available': False, 'file': filename,
                'line': line, 'lines': [], 'reason': 'Source directory unavailable'}
    root = os.path.realpath(game_dir)
    full = os.path.realpath(os.path.join(root, *filename.split('/')))
    if not full.startswith(root + os.sep) or not full.lower().endswith('.rpy'):
        raise ValueError('script path leaves game directory')
    try:
        if os.path.getsize(full) > MAX_SOURCE_BYTES:
            return {'protocol': 1, 'available': False, 'file': filename,
                    'line': line, 'lines': [], 'reason': 'Source file exceeds read limit'}
        start = max(1, line - SOURCE_CONTEXT)
        stop = line + SOURCE_CONTEXT
        with io.open(full, 'r', encoding='utf-8', errors='replace') as stream:
            lines = [{'line': index, 'text': text[:MAX_SOURCE_LINE_LENGTH]}
                     for index, text in enumerate(islice(stream, stop), 1)
                     if index >= start]
        if not lines or line > lines[-1]['line']:
            return {'protocol': 1, 'available': False, 'file': filename,
                    'line': line, 'lines': [], 'reason': 'Line is not in available source'}
        return {'protocol': 1, 'available': True, 'file': filename,
                'line': line, 'lines': lines}
    except (IOError, OSError):
        return {'protocol': 1, 'available': False, 'file': filename,
                'line': line, 'lines': [], 'reason': 'Source .rpy not installed'}
