"""Browser favourites saved outside Ren'Py gameplay and rollback state.

Only this inspector-owned file may be written by the authenticated preferences
endpoint. Path validation never reads or evaluates game values (Python 2/3).
"""
from __future__ import unicode_literals

import io
import json
import os
import tempfile
import threading

from .bridge_paging import validate_tree_request
from .compat import atomic_replace

MAX_FAVOURITES = 100
MAX_PREFERENCE_BYTES = 64 * 1024
PREFERENCE_FILE = 'renpy-inspector-browser-favourites.json'


def validate_favourites(payload):
    if not isinstance(payload, list) or len(payload) > MAX_FAVOURITES:
        raise ValueError('invalid favourite collection')
    output, seen = [], set()
    for item in payload:
        if not isinstance(item, dict) or set(item) != set(('scope', 'key')):
            raise ValueError('invalid favourite entry')
        key, scope = item['key'], item['scope']
        if not isinstance(key, (str, bytes)) or len(key) > 2048:
            raise ValueError('invalid favourite key')
        try:
            pair = json.loads(key)
        except (TypeError, ValueError):
            raise ValueError('favourite key is not JSON')
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] != scope:
            raise ValueError('scope/key mismatch')
        decoded = validate_tree_request(scope, pair[1], 0, 1)
        if not decoded[1]:
            raise ValueError('favourite cannot be the scope root')
        canonical = json.dumps([scope, decoded[1]], ensure_ascii=True,
                               separators=(',', ':'))
        if canonical in seen:
            continue
        seen.add(canonical)
        output.append({'scope': scope, 'key': canonical})
    return output


class BrowserFavouritesStore(object):
    def __init__(self, savedir):
        if not savedir:
            raise ValueError('missing inspector save directory')
        self.path = os.path.join(savedir, PREFERENCE_FILE)
        self.lock = threading.RLock()

    def load(self):
        with self.lock:
            try:
                if os.stat(self.path).st_size > MAX_PREFERENCE_BYTES:
                    raise ValueError('preference file too large')
                with io.open(self.path, 'r', encoding='utf-8') as handle:
                    value = json.load(handle)
                if not isinstance(value, dict) or value.get('version') != 1:
                    raise ValueError('invalid preference version')
                favourites = validate_favourites(value.get('favourites'))
                return {'version': 1, 'initialized': True, 'favourites': favourites}
            except (OSError, UnicodeError, ValueError, TypeError):
                return {'version': 1, 'initialized': False, 'favourites': []}

    def save(self, favourites):
        parsed = validate_favourites(favourites)
        payload = json.dumps({'version': 1, 'favourites': parsed}, ensure_ascii=True,
                             separators=(',', ':')).encode('ascii')
        if len(payload) > MAX_PREFERENCE_BYTES:
            raise ValueError('too many favourite bytes')
        with self.lock:
            directory = os.path.dirname(self.path)
            if not os.path.isdir(directory):
                os.makedirs(directory)
            fd, temp = tempfile.mkstemp(prefix='.renpy-inspector-favourites-',
                                        suffix='.tmp', dir=directory)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                atomic_replace(temp, self.path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return {'version': 1, 'initialized': True, 'favourites': parsed}
