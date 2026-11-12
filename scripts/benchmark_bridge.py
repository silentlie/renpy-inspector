"""Synthetic bridge microbenchmark; not a Ren'Py FPS/compatibility test.

Run on Python 3.9+ to record bounded root, child-page and pinned-path costs.
No network server, game process, saves or source files are required.
"""
import argparse
import json
import sys
from pathlib import Path
from statistics import median
from time import perf_counter
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'game'))
from renpy_inspector.bridge_paging import build_lazy_snapshot, build_tree_page, build_tree_value
from renpy_inspector.bridge_snapshot import MAX_JSON_BYTES, encode_snapshot


def fixture():
    root = ModuleType('store')
    for i in range(240):
        setattr(root, 'variable_%03d' % i, i)
    root.profile = {'hp': 100, 'inventory': list(range(500))}
    persistent = {'unlocked': True}
    providers = {'store': lambda: root, 'persistent': lambda: persistent}
    return providers


def measure(label, action, iterations):
    samples = []
    response_bytes = 0
    for _ in range(iterations):
        started = perf_counter()
        result = action()
        samples.append(round((perf_counter() - started) * 1000.0, 4))
        encoded = encode_snapshot(result)
        response_bytes = max(response_bytes, len(encoded))
    ordered = sorted(samples)
    p95 = ordered[max(0, int((len(ordered) * 0.95 + 0.999999)) - 1)]
    if response_bytes > MAX_JSON_BYTES:
        raise ValueError('response size exceeded bridge budget')
    return {'operation': label, 'samples': iterations, 'median_ms': round(median(samples), 4),
            'p95_ms': p95, 'max_ms': ordered[-1], 'max_response_bytes': response_bytes}


def run_benchmark(iterations=30, warmup=3):
    if type(iterations) is not int or not 1 <= iterations <= 1000:
        raise ValueError('iterations must be between 1 and 1000')
    if type(warmup) is not int or not 0 <= warmup <= 100:
        raise ValueError('warmup out of range')
    providers = fixture()
    tasks = [
        ('root_scan', lambda: build_lazy_snapshot(providers)),
        ('expanded_page', lambda: build_tree_page(
            providers, 'store', (('attribute', 'profile'), ('key', 'inventory')), 80, 80)),
        ('favourite_value', lambda: build_tree_value(
            providers, 'store', (('attribute', 'profile'), ('key', 'hp')))),
    ]
    for _, action in tasks:
        for _ in range(warmup):
            action()
    cases = [measure(name, action, iterations) for name, action in tasks]
    return {
        'kind': 'synthetic_bridge_microbenchmark',
        'iterations': iterations,
        'warmup': warmup,
        'python': sys.version.split()[0],
        'limitations': 'No RenPy renderer, gameplay, socket latency or unmodified-game FPS baseline.',
        'cases': cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--warmup', type=int, default=3)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = run_benchmark(args.iterations, args.warmup)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
