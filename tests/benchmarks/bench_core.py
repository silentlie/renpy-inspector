"""Opt-in core benchmark; does not measure native Ren'Py rendering or FPS.

From repository root: python tests/benchmarks/bench_core.py
"""
import sys
import time
from pathlib import Path
from statistics import median
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game'))
from renpy_inspector.controller import Inspector

for size in (100, 1000, 10000):
    root = SimpleNamespace(entries=list(range(size)))
    ins = Inspector()
    ins.bind(lambda: root, lambda: SimpleNamespace())
    ins.open()
    ins.toggle_node((('attribute', 'entries'),))
    durations = []
    for _ in range(50):
        start = time.perf_counter_ns()
        ins.refresh()
        durations.append((time.perf_counter_ns() - start) / 1e6)
    print('entries={} rows={} median_core_refresh_ms={:.3f}'.format(
        size, len(ins.rows), median(durations)))
