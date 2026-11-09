"""Standalone bounded search timings. Not a Ren'Py FPS benchmark."""

import sys
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game'))
from renpy_inspector.search import search_tree


def main():
    print('Search benchmark (Python-only, no Ren\'Py renderer)')
    for size in (100, 1000, 10000):
        root = SimpleNamespace(inventory=[{'health': n} for n in range(size)])
        begin = perf_counter()
        result = search_tree(root, 'store', 'health')
        ms = (perf_counter() - begin) * 1000
        print('entries={} visited={} results={} truncated={} ms={:.3f}'.format(
            size, result.visited, len(result.matches), result.truncated, ms))


if __name__ == '__main__':
    main()
