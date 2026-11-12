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
        # Bound bytes on the opened file, not only a preceding stat(). A file
        # can grow or be replaced between a size check and a line iterator;
        # even one enormous line would otherwise allocate unbounded memory.
        with io.open(full, 'rb') as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            return {'protocol': 1, 'available': False, 'file': filename,
                    'line': line, 'lines': [], 'reason': 'Source file exceeds read limit'}
        start = max(1, line - SOURCE_CONTEXT)
        stop = line + SOURCE_CONTEXT
        content = raw.decode('utf-8', 'replace')
        lines = [{'line': index, 'text': text[:MAX_SOURCE_LINE_LENGTH]}
                 for index, text in enumerate(islice(content.splitlines(True), stop), 1)
                 if index >= start]
        if not lines or line > lines[-1]['line']:
            return {'protocol': 1, 'available': False, 'file': filename,
                    'line': line, 'lines': [], 'reason': 'Line is not in available source'}
        return {'protocol': 1, 'available': True, 'file': filename,
                'line': line, 'lines': lines}
    except (IOError, OSError):
        return {'protocol': 1, 'available': False, 'file': filename,
                'line': line, 'lines': [], 'reason': 'Source .rpy not installed'}


# Literal, read-only source search is deliberately bounded per game-thread
# request. Results are not an index of all possible .rpy files or references.
SOURCE_SEARCH_PAGE_SIZE = 20
SOURCE_SEARCH_MAX_FILES = 120
SOURCE_SEARCH_MAX_DIRS = 80
SOURCE_SEARCH_DEPTH = 6
SOURCE_SEARCH_MAX_FILE_BYTES = 128 * 1024
SOURCE_SEARCH_PAGE_BYTES = 256 * 1024
SOURCE_SEARCH_PAGE_FILES = 12


def validate_source_search_request(query, cursor, size):
    """Reject expressions and oversized / malformed pagination inputs."""
    if not isinstance(query, string_types):
        raise ValueError('invalid source search term')
    query = query.strip()
    if not 2 <= len(query) <= 64 or any(ord(char) < 32 for char in query):
        raise ValueError('invalid source search term')
    if type(size) is not int or not 1 <= size <= SOURCE_SEARCH_PAGE_SIZE:
        raise ValueError('invalid source search size')
    if not isinstance(cursor, string_types) or len(cursor) > 24:
        raise ValueError('invalid source search cursor')
    parts = cursor.split(':')
    if (len(parts) != 2 or not all(p.isdigit() and 1 <= len(p) <= 8 for p in parts)):
        raise ValueError('invalid source search cursor')
    file_index, line_index = int(parts[0]), int(parts[1])
    if file_index > SOURCE_SEARCH_MAX_FILES or line_index > MAX_SOURCE_LINE:
        raise ValueError('source search cursor exceeds limits')
    return query, file_index, line_index, size


def _source_search_files(game_dir):
    """List only game-owned .rpy paths, never engine files or inspector code.

    Enumeration is bounded by both visited directory and eligible file counts.
    Per-file realpath checks and no-follow-symlink rules prevent traversal.
    """
    if not game_dir or not os.path.isdir(game_dir):
        return [], False
    root = os.path.realpath(game_dir)
    files = []
    limited = False
    directories = 0
    try:
        for directory, subdirs, names in os.walk(root, followlinks=False):
            directories += 1
            if directories > SOURCE_SEARCH_MAX_DIRS:
                limited = True
                break
            rel_dir = os.path.relpath(directory, root)
            depth = 0 if rel_dir == '.' else rel_dir.count(os.sep) + 1
            if depth >= SOURCE_SEARCH_DEPTH:
                if subdirs:
                    limited = True
                subdirs[:] = []
            else:
                excluded = []
                for name in subdirs:
                    candidate = os.path.join(directory, name)
                    if (name.startswith('.') or name.startswith('renpy_inspector') or
                            name in ('saves', '__pycache__') or os.path.islink(candidate)):
                        excluded.append(name)
                subdirs[:] = sorted(name for name in subdirs if name not in excluded)
            for name in sorted(names):
                if not name.lower().endswith('.rpy') or name.startswith('renpy_inspector'):
                    continue
                full = os.path.join(directory, name)
                if os.path.islink(full) or not os.path.isfile(full):
                    limited = True
                    continue
                real = os.path.realpath(full)
                if not real.startswith(root + os.sep):
                    limited = True
                    continue
                rel = os.path.relpath(real, root).replace(os.sep, '/')
                if _script_file(rel, root) != rel or len(rel) > 230:
                    limited = True
                    continue
                files.append((rel, real))
                if len(files) >= SOURCE_SEARCH_MAX_FILES:
                    limited = True
                    break
            if len(files) >= SOURCE_SEARCH_MAX_FILES:
                break
    except (IOError, OSError):
        limited = True
    # Directory walk order is deterministic but not necessarily global file
    # order. The same list is rebuilt for each continuation in a query.
    return files, limited


def _source_match_preview(line, position, query_length):
    """Return a bounded source fragment that actually contains the hit."""
    start = max(0, position - 75)
    end = min(len(line), max(start + MAX_SOURCE_LINE_LENGTH, position + query_length))
    text = line[start:end].strip('\r\n')
    if start:
        text = '\u2026' + text
    if end < len(line):
        text += '\u2026'
    return _safe_text(text, MAX_SOURCE_LINE_LENGTH + 2)


def search_source_text(game_dir, query, cursor='0:0', size=SOURCE_SEARCH_PAGE_SIZE):
    """Search literal .rpy text with a strict per-call I/O and output budget.

    Only call on the Ren'Py game thread through the authenticated queue. A
    cursor is an untrusted file-index:line-index pair, not a filesystem path.
    No regex, Python code evaluation, reads outside gamedir, or writes.
    """
    query, file_index, line_index, size = validate_source_search_request(
        query, cursor, size)
    files, limited = _source_search_files(game_dir)
    if not files:
        return {'protocol': 1, 'query': query, 'matches': [],
                'cursor': None, 'more': False, 'limited': limited,
                'available': False,
                'reason': 'No game-owned .rpy source files available',
                'scanned_files': 0, 'scanned_bytes': 0}

    hits = []
    visited = 0
    scanned_bytes = 0
    needle = query.lower()
    index = file_index
    start_line = line_index
    while index < len(files) and visited < SOURCE_SEARCH_PAGE_FILES:
        filename, full = files[index]
        try:
            # Read one bounded file, never open unbounded or follow symlinks.
            if os.path.islink(full):
                limited = True
                index += 1
                start_line = 0
                continue
            with io.open(full, 'rb') as stream:
                raw = stream.read(SOURCE_SEARCH_MAX_FILE_BYTES + 1)
            visited += 1
            if len(raw) > SOURCE_SEARCH_MAX_FILE_BYTES:
                limited = True
                index += 1
                start_line = 0
                continue
            if scanned_bytes and scanned_bytes + len(raw) > SOURCE_SEARCH_PAGE_BYTES:
                # Rescan the next file in a new job instead of exceeding a
                # single engine-thread read budget.
                break
            scanned_bytes += len(raw)
            lines = raw.decode('utf-8', 'replace').splitlines()
            for line_number in range(start_line, min(len(lines), MAX_SOURCE_LINE)):
                text = lines[line_number]
                position = text.lower().find(needle)
                if position < 0:
                    continue
                hits.append({'file': filename, 'line': line_number + 1,
                             'text': _source_match_preview(text, position, len(query))})
                if len(hits) >= size:
                    next_line = line_number + 1
                    next_cursor = ('{}:{}'.format(index, next_line)
                                   if next_line < len(lines)
                                   else '{}:0'.format(index + 1))
                    return {'protocol': 1, 'query': query,
                            'matches': hits, 'cursor': next_cursor,
                            'more': bool(index + 1 < len(files) or next_line < len(lines)),
                            'limited': limited, 'available': True,
                            'scanned_files': visited, 'scanned_bytes': scanned_bytes}
            if len(lines) > MAX_SOURCE_LINE:
                limited = True
        except (IOError, OSError, UnicodeError):
            limited = True
        index += 1
        start_line = 0
    more = index < len(files)
    return {'protocol': 1, 'query': query, 'matches': hits,
            'cursor': '{}:0'.format(index) if more else None,
            'more': more, 'limited': limited, 'available': True,
            'scanned_files': visited, 'scanned_bytes': scanned_bytes}
