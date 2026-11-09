"""Bounded, read-only path discovery; never retains game values after a search."""

from collections import deque
from dataclasses import dataclass

from .favorites import format_location
from .inspection import MISSING, child_descriptors, clipped, escape_text, read_child, snapshot

MAX_QUERY = 80
MAX_SEARCH_VISITS = 2400
MAX_SEARCH_MATCHES = 50
MAX_SEARCH_DEPTH = 6
MAX_SEARCH_CHILDREN = 200


@dataclass(frozen=True)
class SearchMatch:
    scope: str
    path: tuple
    label: str
    preview: str
    type_name: str
    state: str


@dataclass(frozen=True)
class SearchResult:
    matches: tuple
    visited: int
    truncated: bool
    errors: int


def search_tree(value, scope, query, *, max_visits=MAX_SEARCH_VISITS,
                max_matches=MAX_SEARCH_MATCHES, max_depth=MAX_SEARCH_DEPTH,
                max_children=MAX_SEARCH_CHILDREN):
    """Breadth-first search. Limits count work, not an exhaustive promise.

    The queue holds references transiently during a single explicit search.
    Neither results nor the controller cache retains these references.
    """
    if type(query) is not str:
        raise ValueError('search query must be text')
    if not 1 <= len(query.strip()) <= MAX_QUERY:
        return SearchResult((), 0, False, 0)
    if not all(type(x) is int and x > 0 for x in
               (max_visits, max_matches, max_depth, max_children)):
        raise ValueError('invalid search budget')
    needle = query.strip().casefold()
    queue = deque([(value, (), frozenset(), 0)])
    results = []
    visited = 0
    errors = 0
    truncated = False
    while queue and visited < max_visits and len(results) < max_matches:
        owner, path, ancestors, depth = queue.popleft()
        if owner is MISSING or id(owner) in ancestors:
            continue
        if depth >= max_depth:
            truncated = True
            continue
        next_ancestors = ancestors | {id(owner)}
        try:
            descriptors, cut = child_descriptors(owner, max_children, is_store_root=(scope == 'store' and not path))
            truncated |= cut
        except Exception:
            errors += 1
            continue
        for segment, _label in descriptors:
            if visited >= max_visits:
                truncated = True
                break
            visited += 1
            child_path = path + (segment,)
            try:
                name = format_location(scope, child_path)
                member = read_child(owner, segment)
                state, type_name, preview, expandable, _ = snapshot(member, is_cycle=id(member) in next_ancestors)
            except Exception:
                errors += 1
                continue
            if needle in name.casefold():
                results.append(SearchMatch(scope, child_path, escape_text(clipped(name, 130)),
                                           escape_text(clipped(preview, 100)),
                                           escape_text(clipped(type_name, 50)), state))
                if len(results) == max_matches:
                    truncated = True
                    break
            if expandable and member is not MISSING and id(member) not in next_ancestors:
                if depth + 1 < max_depth and visited + len(queue) < max_visits:
                    queue.append((member, child_path, next_ancestors, depth + 1))
                else:
                    truncated = True
        if len(results) >= max_matches:
            break
    return SearchResult(tuple(results), visited, truncated or bool(queue), errors)
