"""Session-only, path-based tree state and shared polling controller."""

from __future__ import annotations

from dataclasses import dataclass, field

from .inspection import MISSING, child_descriptors, escape_text, read_child, snapshot


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


@dataclass
class Node:
    path: tuple = ()
    label: str = ''
    expanded: bool = False
    children: dict = field(default_factory=dict)


class Inspector:
    """Owns no game objects, only typed paths and cached display strings."""

    def __init__(self, on_change=None):
        self.is_open = False
        self.scope = 'store'
        self.interval_ms = 250
        self._providers = {}
        self._roots = {}
        self._lookup = {}
        self.rows = ()
        self._on_change = on_change

    def bind(self, store_provider, persistent_provider):
        self._providers = {'store': store_provider, 'persistent': persistent_provider}
        self.reset()

    def reset(self):
        """Used by Ren'Py after a save is loaded; drops all cached tree state."""
        self._roots = {}
        self._lookup = {}
        self.rows = ()
        # Don't interrogate the restored store during an after-load callback.

    def open(self):
        self.is_open = True
        self.refresh()

    def close(self):
        self.is_open = False
        self.reset()  # release subscriptions, especially while drawer is hidden

    def toggle_open(self):
        self.close() if self.is_open else self.open()

    def set_scope(self, scope):
        if scope not in self._providers:
            raise ValueError('unknown scope: ' + scope)
        self.scope = scope
        if self.is_open:
            self.refresh()

    def set_interval(self, milliseconds):
        if (type(milliseconds) is not int or
                (milliseconds != 0 and not 50 <= milliseconds <= 60000)):
            raise ValueError('interval must be 0 or 50..60000 milliseconds')
        self.interval_ms = milliseconds

    def toggle_node(self, path):
        node = self._lookup.get(path)
        if node is None:
            return
        node.expanded = not node.expanded
        if not node.expanded:
            node.children.clear()  # stop watching all descendants
        self.refresh()

    def refresh(self):
        """Read selected root once; build rows without storing game references."""
        if not self.is_open:
            return False
        root = self._roots.setdefault(self.scope, Node(expanded=True))
        lookup = {}
        rows = []
        try:
            value = self._providers[self.scope]()
            self._visit(root, value, 0, set(), rows, lookup, is_root=True)
        except Exception as exc:
            # Per-root failure; rendering a diagnostic is preferable to a crash.
            rows = [Row((), 'Inspection unavailable', type(exc).__name__,
                        'error', 0, False, False, 'error')]
            lookup = {}
        changed = tuple(rows) != self.rows
        self.rows = tuple(rows)
        self._lookup = lookup
        return changed

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
                      node.expanded and expandable and not is_cycle, state)
            rows.append(row)
            lookup[node.path] = node

        if (not node.expanded or not expandable or is_cycle or depth >= MAX_DEPTH
                or len(rows) >= MAX_ROWS):
            return

        # Each ancestor identity is only active along its own branch.  This
        # handles cycles without treating shared, non-cyclic values as cycles.
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
            # Avoid invoking equality of untrusted object-valued dictionary keys.
            key = segment
            child = node.children.get(key)
            if child is None:
                child = Node(path=node.path + (segment,), label=label)
            new_children[key] = child
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
        """Sole timer callback, with one screen invalidation for a changed poll."""
        if self.is_open and self.interval_ms > 0 and self.refresh():
            if self._on_change is not None:
                self._on_change()
        return None
