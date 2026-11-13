# PR #16: Request scheduling and performance evidence (v0.6.9)

This is an **experimental, read-only** optimisation. It does not change the
transport (authenticated HTTP polling), render a native Ren'Py interface, or
modify gameplay state.

## Browser request scheduling

- One shared scheduler still plans expanded tree pages plus independent
  favourite-path watches. Each 1.5-second tick selects at most two ready jobs.
- At most **two background watch requests are concurrently in flight**, even
  if Ren'Py's interaction/overlay is suspended. Already-running watches and
  foreground-request duplicates are skipped.
- Round-robin selection walks past unavailable jobs, so an already-pending
  favourite does not prevent another favourite or expanded page from being
  sampled. On a game generation change, old watch slots are discarded; late
  responses still cannot enter the restored tree.
- Direct expansion, user-driven search/reveal, and script browsing remain
  interactive. Their separate requests can temporarily add to the bridge's
  queue, which stays capped at eight; a full queue returns HTTP 429.
- An in-flight limit protects queue load but **cannot guarantee FPS**: the
  duration of a single allowed game-thread lookup still depends on the game.

## Overview diagnostics

A root snapshot (about every 1.5 seconds while the interaction timer runs)
also publishes bounded, primitive-only `diagnostics`:

| Field | Interpretation |
| --- | --- |
| `root_scan_ms` | Wall-clock time to collect the last shallow game-thread snapshot, excluding bounded lock checks, JSON encoding, network transfer and browser rendering |
| `lock_checks` / `lock_check_ms` | At most eight rotating exact-path checks per snapshot publish and their separate game-thread cost; not included in `root_scan_ms` |
| `queue_pending` | Jobs waiting **at the time of the last snapshot**; it is not a continuously updated queue graph |
| `queue_capacity` | Eight queued jobs, not total running HTTP threads |
| `queue_peak` | Maximum queued jobs observed in the current game-state generation |
| `queue_rejected` | Rejections for full queue, in the current generation |
| `requests_completed` | Handled game-thread jobs in the current generation (including error responses) |
| `last_request_ms` | Last handled queued job's game-thread execution plus serialisation time |
| `last_queue_wait_ms` | Last handled job's wait from queue admission until game-thread service begins |

These values are sampled, reset across load/rollback epochs and intentionally
contain no inspected paths or game values. They are **not** p95/p99 latency,
network RTT, CPU utilisation or game frame-time evidence.

## Synthetic microbenchmark

From the repository root, run:

```sh
python scripts/benchmark_bridge.py --iterations 100 --warmup 5 \
  --output bridge-benchmark.json
```

It measures `root_scan`, `expanded_page` and `favourite_value` using
a fixed synthetic Python Store object and bounded JSON output. It reports
median, nearest-rank p95, maximum duration and maximum encoded response size
for each operation. No network request, Ren'Py game engine, browser DOM, F8,
save/load or real FPS is involved. Treat numbers as a reproducible component
baseline, **not** claims of live performance or proof of speedup.

CI saves JSON results for Python 3.9 and 3.13, runs Python 2.7 compatibility
tests and lint with Ren'Py 7.4.11/7.8.7/8.4.1/8.5.3. Do not compare CI runs as
controlled performance experiments because runner hardware/load can vary.

## Real-game acceptance before merging

Test both Ren'Py 7 and Ren'Py 8 with the same game build and hardware.
Collect frame-time distributions (including p95), input responsiveness,
service queue depth/rejections, memory, and CPU under:

1. Game without inspector installed.
2. Inspector installed but F8 never pressed.
3. Inspector active, browser open, idle values.
4. Inspector active with many expanded branches, favourites, rapid mutations,
   load/rollback and a deliberately paused overlay.

Repeat with approximately 100, 1,000 and 10,000 logical entries, staying
within the documented branch/browser caps. Confirm F8, keyboard navigation,
scrolling and watch freshness remain usable. Compare equivalent scenes and
durations to a clean game baseline. Investigate regressions using the
`diagnostics` counters and synthetic results; **do not set FPS pass thresholds
without measured baseline data**.

Security remains localhost-bound with token, Host and Origin checks, and
inspects game objects only on Ren'Py's interaction thread.
