"""Session-only tree, explicit root-relative favourites and one polling controller."""

from __future__ import unicode_literals

from collections import namedtuple
from .compat import monotonic_time, string_types, integer_types, iter_items
from types import ModuleType

from .favorites import MAX_FAVORITES, encode_location, format_location, valid_scope
from .inspection import MISSING, child_descriptors, clipped, escape_text, read_child, snapshot
from .settings import DEFAULT_WIDTH, validate_interval, validate_width
from .search import SearchMatch, SearchResult, search_tree, MAX_QUERY

MAX_CHILDREN = 200
MAX_ROWS = 1200
MAX_DEPTH = 12
MAX_NAMED_STORES = 8
MAX_DISCOVERY_SCAN = 1000


Row = namedtuple('Row',
    'path label preview type_name depth expandable expanded state favorite pinnable')
# Older call-sites omit favourite/pinnable flags.
Row.__new__.__defaults__ = (False, False)
FavoriteRow = namedtuple('FavoriteRow',
    'location label preview type_name state')


class Node(object):
    """Mutable tree metadata; never stores inspected values."""
    def __init__(self, path=(), label='', expanded=False, children=None):
        self.path = path
        self.label = label
        self.expanded = expanded
        self.children = {} if children is None else children


class Inspector(object):
    """Owns paths and previews, never long-lived references to game values."""

    def __init__(self, on_change=None):
        self.is_open = False
        self.scope = 'store'
        self.panel = 'variables'
        self.search_query = ''
        self.applied_search = ''
        self.search_matches = ()
        self.search_visited = 0
        self.search_truncated = False
        self.search_errors = 0
        self._search_scope = 'store'
        self.last_poll_ms = 0.0
        self.overview_rows = ()
        self.script_rows = ()
        self._context_provider = None
        self._named = {}
        self.named_scope_options = ()
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

    def bind(self, store_provider, persistent_provider, settings=None, context_provider=None):
        self._providers = {'store': store_provider, 'persistent': persistent_provider}
        self._context_provider = context_provider
        self._settings = settings
        if settings is not None:
            loaded = settings.load()
            self.interval_ms = loaded['interval_ms']
            self.drawer_width = loaded['drawer_width']
            self.favorites = list(loaded['favorites'])
            self.scope = loaded.get('scope', 'store')
        self.reset()

    def _persist(self):
        if self._settings is None:
            return
        try:
            self._settings.save(interval_ms=self.interval_ms,
                                drawer_width=self.drawer_width,
                                favorites=self.favorites, scope=self.scope)
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
        self.search_matches = ()
        self.applied_search = ''
        self.search_visited = 0
        self.search_truncated = False
        self.search_errors = 0
        self.overview_rows = ()
        self.script_rows = ()

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

    def register_named_store(self, name, provider):
        """Register a trusted no-argument provider, normally from game init."""
        if not isinstance(name, string_types) or not callable(provider):
            raise ValueError('invalid named store registration')
        scope = 'named:' + name
        if not valid_scope(scope):
            raise ValueError('invalid named store registration')
        if scope not in self._named and len(self._named) >= MAX_NAMED_STORES:
            raise ValueError('named store limit reached')
        self._named[scope] = provider

    def named_scopes(self):
        """Safely discover store.* module attributes, without arbitrary getters."""
        names = set(self._named)
        try:
            store = self._providers['store']()
            if not isinstance(store, ModuleType):
                return tuple(sorted(names))
            fields = vars(store)
            for number, (name, member) in enumerate(iter_items(fields)):
                if number >= MAX_DISCOVERY_SCAN or len(names) >= MAX_NAMED_STORES:
                    break
                if (isinstance(name, string_types) and isinstance(member, ModuleType) and
                        member.__name__ == 'store.' + name and
                        valid_scope('named:' + name)):
                    names.add('named:' + name)
        except Exception:
            pass
        return tuple(sorted(names)[:MAX_NAMED_STORES])

    def _get_root(self, scope):
        if scope in self._providers:
            return self._providers[scope]()
        if scope in self._named:
            return self._named[scope]()
        if valid_scope(scope) and scope.startswith('named:'):
            name = scope[6:]
            store = self._providers['store']()
            member = read_child(store, ('attribute', name))
            if (isinstance(member, ModuleType) and member.__name__ == 'store.' + name):
                return member
        return MISSING

    def set_scope(self, scope):
        if scope not in self._providers and scope != 'favorites' and scope not in self.named_scopes():
            raise ValueError('unknown scope: ' + str(scope))
        self.scope = scope
        self.search_matches = ()
        self.applied_search = ''
        self._persist()
        if self.is_open:
            self.refresh()

    def show_named(self):
        scopes = self.named_scopes()
        if scopes:
            self.set_scope(self.scope if self.scope in scopes else scopes[0])

    def set_panel(self, panel):
        if panel not in ('variables', 'overview', 'scripts', 'settings'):
            raise ValueError('unknown panel')
        self.panel = panel
        if self.is_open:
            self.refresh()

    def run_search(self):
        """Search only when submitted; do not traverse game state per keystroke."""
        query = self.search_query.strip()
        if len(query) > MAX_QUERY:
            query = query[:MAX_QUERY]
        self.applied_search = query
        self._search_scope = self.scope
        if not self.is_open or self.scope == 'favorites' or not query:
            self.search_matches = ()
            self.search_visited = 0
            self.search_truncated = False
            self.search_errors = 0
            return
        try:
            result = search_tree(self._get_root(self.scope), self.scope, query)
        except Exception:
            result = SearchResult((), 0, False, 1)
        self.search_matches = result.matches
        self.search_visited = result.visited
        self.search_truncated = result.truncated
        self.search_errors = result.errors
        if self.is_open:
            self.refresh()

    def clear_search(self):
        self.applied_search = ''
        self.search_matches = ()
        self.search_query = ''
        if self.is_open:
            self.refresh()

    def reveal_search(self, scope, path):
        """Show parent branches of a found location, if still reachable."""
        if scope != self.scope or not isinstance(path, tuple):
            return
        self.panel = 'variables'
        self.applied_search = ''
        self.search_matches = ()
        root = self._roots.setdefault(scope, Node(expanded=True))
        node = root
        for segment in path[:-1]:
            node.expanded = True
            if segment not in node.children:
                node.children[segment] = Node(path=node.path + (segment,))
            node = node.children[segment]
        node.expanded = True
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
        """Refresh visible view and independent favourite subscriptions."""
        if not self.is_open:
            return False
        self.named_scope_options = self.named_scopes()
        rows, lookup = [], {}
        if self.panel == 'variables' and self.scope != 'favorites':
            root = self._roots.setdefault(self.scope, Node(expanded=True))
            try:
                value = self._get_root(self.scope)
                if value is MISSING:
                    rows = [Row((), 'Named store unavailable', '<missing>',
                                'missing', 0, False, False, 'missing')]
                else:
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
        if self._search_scope == self.scope and self.search_matches and self.panel == 'variables':
            search_rows = tuple(self._update_search_match(m) for m in self.search_matches)
            if search_rows != self.search_matches:
                self.search_matches = search_rows
                changed = True
        if self.panel in ('overview', 'scripts'):
            info = self._context_info()
            overview = (
                ('Game', info.get('game', 'Unavailable')),
                ('Ren\'Py', info.get('version', 'Unavailable')),
                ('Scope', self.scope),
                ('Favourites', str(len(self.favorites))),
                ('Polling', 'manual' if self.interval_ms == 0 else '{} ms'.format(self.interval_ms)),
                ('Last poll', '{:.2f} ms'.format(self.last_poll_ms)),
            )
            scripts = (
                ('Current file', info.get('filename', 'Unavailable')),
                ('Current line', info.get('line', 'Unavailable')),
                ('Return depth', info.get('return_depth', 'Unavailable')),
                ('Return labels', info.get('return_labels', 'Unavailable')),
            )
            new_overview = tuple((escape_text(clipped(k, 60)), escape_text(clipped(str(v), 160))) for k, v in overview)
            new_scripts = tuple((escape_text(clipped(k, 60)), escape_text(clipped(str(v), 160))) for k, v in scripts)
            if new_overview != self.overview_rows or new_scripts != self.script_rows:
                changed = True
            self.overview_rows, self.script_rows = new_overview, new_scripts
        return changed

    def _context_info(self):
        try:
            data = self._context_provider() if self._context_provider else {}
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return {key: value for key, value in data.items() if isinstance(key, string_types) and type(value) in string_types + integer_types + (float,)}

    def _update_search_match(self, match):
        try:
            member = self._get_root(match.scope)
            for part in match.path:
                member = read_child(member, part)
                if member is MISSING:
                    break
            state, typ, preview, _, _ = snapshot(member)
        except Exception as exc:
            state, typ, preview = 'error', 'error', type(exc).__name__
        return SearchMatch(match.scope, match.path, match.label,
                           escape_text(clipped(preview, 100)), escape_text(clipped(typ, 50)), state)

    def _read_favorite(self, scope, path):
        location = (scope, path)
        label = escape_text(clipped(format_location(scope, path), 110))
        try:
            value = self._get_root(scope)
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
            else:
                child.label = label
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
            rows.append(Row(node.path + (('truncated',),), '\u2026 more entries hidden',
                            'per-node limit {}'.format(MAX_CHILDREN), 'info',
                            depth, False, False, 'info'))

    def tick(self):
        """Sole scheduler callback; one invalidation regardless of changed count."""
        if self.is_open and self.interval_ms > 0:
            start = monotonic_time()
            changed = self.refresh()
            self.last_poll_ms = (monotonic_time() - start) * 1000.0
            if changed and self._on_change is not None:
                self._on_change()
        return None
