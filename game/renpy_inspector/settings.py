"""Inspector-only settings, separate from gameplay saves and persistent fields."""

import json
import os
import tempfile
from pathlib import Path

from .favorites import MAX_FAVORITES, decode_location, encode_location, valid_scope

DEFAULT_INTERVAL = 250
DEFAULT_WIDTH = 460
MAX_SETTINGS_BYTES = 128 * 1024


def validate_interval(value):
    if type(value) is not int or (value != 0 and not 50 <= value <= 60000):
        raise ValueError('interval must be 0 or 50..60000 milliseconds')
    return value


def validate_width(value):
    if type(value) is not int or not 320 <= value <= 760:
        raise ValueError('width must be 320..760 pixels')
    return value


class SettingsStore:
    """A small atomic JSON store in the game's own saves directory."""

    def __init__(self, savedir):
        if not savedir:
            raise ValueError('no Ren\'Py save directory available')
        self.path = Path(savedir) / 'renpy-inspector-settings.json'

    def load(self):
        defaults = {'interval_ms': DEFAULT_INTERVAL, 'drawer_width': DEFAULT_WIDTH, 'favorites': [], 'scope': 'store'}
        try:
            if self.path.stat().st_size > MAX_SETTINGS_BYTES:
                return defaults
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError):
            return defaults
        if not isinstance(data, dict) or data.get('version') != 1:
            return defaults
        for key, validator in [('interval_ms', validate_interval), ('drawer_width', validate_width)]:
            try:
                defaults[key] = validator(data.get(key))
            except ValueError:
                pass
        if valid_scope(data.get('scope')):
            defaults['scope'] = data['scope']
        locations = data.get('favorites')
        if isinstance(locations, list):
            for item in locations[:MAX_FAVORITES]:
                try:
                    location = decode_location(item)
                except ValueError:
                    continue
                if location not in defaults['favorites']:
                    defaults['favorites'].append(location)
        return defaults

    def save(self, *, interval_ms, drawer_width, favorites, scope='store'):
        validate_interval(interval_ms)
        validate_width(drawer_width)
        if not valid_scope(scope):
            raise ValueError('invalid selected scope')
        if len(favorites) > MAX_FAVORITES:
            raise ValueError('too many favourites')
        data = {
            'version': 1,
            'interval_ms': interval_ms,
            'drawer_width': drawer_width,
            'scope': scope,
            'favorites': [encode_location(scope, path) for scope, path in favorites],
        }
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            fd, name = tempfile.mkstemp(prefix='.renpy-inspector-', suffix='.tmp', dir=str(parent))
            temporary = Path(name)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(data, handle, ensure_ascii=True, separators=(',', ':'))
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(self.path))
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
