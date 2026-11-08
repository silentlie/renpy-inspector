"""Session-only tree, explicit root-relative favourites and one polling controller."""

from __future__ import annotations

from dataclasses import dataclass, field

from .favorites import MAX_FAVORITES, encode_location, format_location
from .inspection import MISSING, child_descriptors, clipped, escape_text, read_child, snapshot
from .settings import DEFAULT_WIDTH, validate_interval, validate_width

MAX_CHILDREN = 200
MAX_ROWS = 1200
MAX_DEPTH = 12


@dataclass(frozen=True)
class Row:
    path: tuple
    label: str
    preview: str
    type_name: str
    depth: int
    expandable: bool
    expanded: bool
    state: str
    favorite: bool = False
    pinnable: bool = False


@dataclass(frozen=True)
class FavoriteRow:
    location: tuple
    label: str
    preview: str
    type_name: str
    state: str


@dataclass
class Node:
    path: tuple = ()
    label: str = ''
    expanded: bool = False
    children: dict = field(default_factory=dict)


class Inspector:
    """Owns paths and previews, never long-lived references to game values."""

    def __init__(self, on_change=None):
        self.is_open = False
        self.scope = 'store'
        self.interval_ms = 250
        self.drawer_width = DEFAULT_WIDTH
        self.favorites = []
        self.favorite_rows = ()
        self.settings_error = ''
        self._settings = None
        self._providers = {}
        self._roots = {}
        self._lookup = {}
        self.rows = ()
        self._on_change = on_change

    def bind(self, store_provider, persistent_provider, settings=None):
        self._providers = {'store': store_provider, 'persistent': persistent_provider}
        self._settings = settings
        if settings is not None:
            loaded = settings.load()
            self.interval_ms = loaded['interval_ms']
            self.drawer_width = loaded['drawer_width']
            self.favorites = list(loaded['favorites'])
        self.reset()

    def _persist(self):
        if self._settings is None:
            return
        try:
            self._settings.save(interval_ms=self.interval_ms,
                                drawer_width=self.drawer_width,
                                favorites=self.favorites)
            self.settings_error = ''
        except (OSError, ValueError) as exc:
            # A denied/read-only save folder must never interrupt gameplay.
            self.settings_error = 'Settings not saved: ' + type(exc).__name__

    def reset(self):
        """Discard cache after load, preserving user preferences and favourite paths."""
        self._roots = {}
        self._lookup = {}
        self.rows = ()
        self.favorite_rows = ()

    def open(self):
        if self.is_open:
            return
        self.is_open = True
        self.refresh()

    def close(self):
        self.is_open = False
        self.reset()  # No expensive subscriptions while drawer is closed.

    def toggle_open(self):
        self.close() if self.is_open else self.open()

    def set_scope(self, scope):
        if scope not in self._providers and scope != 'favorites':
            raise ValueError('unknown scope: ' + str(scope))
        self.scope = scope
        if self.is_open:
            self.refresh()

    def set_interval(self, milliseconds):
        self.interval_ms = validate_interval(milliseconds)
        self._persist()

    def set_width(self, width):
        self.drawer_width = validate_width(width)
        self._persist()

    def adjust_width(self, delta):
        self.set_width(max(320, min(760, self.drawer_width + delta)))

    def can_favorite(self, scope, path):
        try:
            encode_location(scope, path)
        except ValueError:
            return False
        return True

    def has_favorite(self, scope, path):
        return (scope, tuple(path)) in self.favorites

    def toggle_favorite(self, scope, path):
        """Add/remove only stable root-relative locations, including missing ones."""
        path = tuple(path)
        encode_location(scope, path)
        location = (scope, path)
        if location in self.favorites:
            self.favorites.remove(location)
        else:
            if len(self.favorites) >= MAX_FAVORITES:
                raise ValueError('favourite limit reached')
            self.favorites.append(location)
        self._persist()
        if self.is_open:
            self.refresh()

    def toggle_node(self, path):
        node = self._lookup.get(path)
        if node is None:
            return
        node.expanded = not node.expanded
        if not node.expanded:
            node.children.clear()
        self.refresh()

    def refresh(self):
        """One pass for selected tree plus independent favourite subscriptions."""
        if not self.is_open:
            return False
        rows = []
        lookup = {}
        if self.scope != 'favorites':
            root = self._roots.setdefault(self.scope, Node(expanded=True))
            try:
                value = self._providers[self.scope]()
                self._visit(root, value, 0, set(), rows, lookup, is_root=True)
            except Exception as exc:
                rows = [Row((), 'Inspection unavailable', type(exc).__name__,
                            'error', 0, False, False, 'error')]
                lookup = {}
        changed = tuple(rows) != self.rows
        self.rows = tuple(rows)
        self._lookup = lookup
        fav_rows = tuple(self._read_favorite(scope, path) for scope, path in self.favorites)
        if fav_rows != self.favorite_rows:
            changed = True
        self.favorite_rows = fav_rows
        return changed

    def _read_favorite(self, scope, path):
        location = (scope, path)
        label = escape_text(clipped(format_location(scope, path), 110))
        try:
            value = self._providers[scope]()
            for segment in path:
                if value is MISSING:
                    break
                value = read_child(value, segment)
            state, type_name, preview, _, _ = snapshot(value)
        except Exception as exc:
            state, type_name, preview = 'error', 'error', type(exc).__name__
        return FavoriteRow(location, label, escape_text(preview),
                           escape_text(type_name), state)

    def _visit(self, node, value, depth, ancestors, rows, lookup, is_root=False):
        if len(rows) >= MAX_ROWS:
            return
        is_cycle = value is not MISSING and id(value) in ancestors
        state, type_name, preview, expandable, _token = snapshot(value, is_cycle=is_cycle)
        if is_root:
            expandable = value is not MISSING
        if not is_root:
            row = Row(node.path, escape_text(node.label), escape_text(preview),
                      escape_text(type_name), depth, expandable and depth < MAX_DEPTH,
                      node.expanded and expandable and not is_cycle, state,
                      self.has_favorite(self.scope, node.path),
                      self.can_favorite(self.scope, node.path))
            rows.append(row)
            lookup[node.path] = node

        if (not node.expanded or not expandable or is_cycle or depth >= MAX_DEPTH
                or len(rows) >= MAX_ROWS):
            return

        next_ancestors = ancestors | {id(value)}
        try:
            descriptors, truncated = child_descriptors(
                value, MAX_CHILDREN, is_store_root=is_root and self.scope == 'store')
        except Exception as exc:
            if len(rows) < MAX_ROWS:
                rows.append(Row(node.path + (('error',),), 'Inspection error',
                                type(exc).__name__, 'error', depth + 1,
                                False, False, 'error'))
            return

        new_children = {}
        for segment, label in descriptors:
            child = node.children.get(segment)
            if child is None:
                child = Node(path=node.path + (segment,), label=label)
            new_children[segment] = child
            try:
                member = read_child(value, segment)
                self._visit(child, member, depth + (0 if is_root else 1),
                            next_ancestors, rows, lookup)
            except Exception as exc:
                if len(rows) < MAX_ROWS:
                    rows.append(Row(child.path, escape_text(label), type(exc).__name__,
                                    'error', depth, False, False, 'error'))
            if len(rows) >= MAX_ROWS:
                break
        node.children = new_children
        if truncated and len(rows) < MAX_ROWS:
            rows.append(Row(node.path + (('truncated',),), '… more entries hidden',
                            'per-node limit {}'.format(MAX_CHILDREN), 'info',
                            depth, False, False, 'info'))

    def tick(self):
        """Sole scheduler callback; one invalidation regardless of changed count."""
        if self.is_open and self.interval_ms > 0 and self.refresh():
            if self._on_change is not None:
                self._on_change()
        return None
