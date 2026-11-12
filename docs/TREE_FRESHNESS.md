# PR #18: Freshness and capture ordering (v0.7.1)

The browser uses HTTP polling and independently serviced child-page requests.
Those responses can finish in a different order from when Ren'Py inspected
values. A valid game-state generation only rules out responses from *older
loads/rollback epochs*. It does not by itself prevent a same-generation response
from overwriting a newer tree preview.

## What changed

- **Game-thread timestamps, not HTTP arrival order.** The browser stores the
  latest accepted `captured_at` on each loaded parent and each root paging
  cursor. A child-page reply older than that parent/root sample is ignored.
  Both background page refreshes and direct expansion are guarded.
- **Shallow root refresh.** Root page zero is stamped with its capture time.
  Cached root snapshots older than the latest watched root page are ignored,
  while newer snapshots preserve descendants that have an even fresher
  game-thread capture.
- **Child pages after structure changes.** A late child-page response cannot
  restore children beneath a now-scalar/missing parent. When the root becomes
  fully enumerated, old paginated tails and previously revealed off-page
  breadcrumbs are removed, and the root paging cursor is reset.
- **Independent favourites.** The browser remembers the latest accepted
  capture time for each pinned typed path. An older returned value never
  overwrites the newer preview, even within a single load generation.
  Favourites still survive load/rollback as paths, not object pointers.
- **No extra polls.** Existing 1.5-second snapshot/watch schedules and
  two-in-flight background cap remain unchanged. Invalidated pages may be
  fetched by the existing scroll sentinel on demand.

Backend response payloads already included `captured_at` at game-thread read
time. This change uses it entirely in the browser; there is no server protocol
change, gameplay write, WebSocket, new timer or permanent UI surface.

## Limitations

- The inspector shows **sampled previews**, not continuous state. Values that
  change and change back between captures may never appear.
- Typed paths and type/preview metadata cannot unambiguously distinguish two
  different custom Python objects with the same type and preview. A replaced
  object may have stale descendants until an observed parent/child watch,
  expansion or lifecycle generation change.
- `captured_at` is a wall-clock time. If the host clock is adjusted sharply,
  sample ordering may be temporarily unreliable; use monotonically increasing
  request sequence numbers in a later protocol revision if this becomes
  demonstrably important.
- This feature is not an FPS optimisation. Existing CI synthetic benchmarks
  and Overview diagnostics are sufficient until a reproducible regression is
  observed.

## Acceptance

Automated JavaScript tests must cover root shrink after previous pagination,
out-of-order page refreshes and appends, older cached root snapshots,
fresher nested captures, stale pages targeting scalar nodes, and ordinary
favourite sample ordering. Existing Python 2/3 and four Ren'Py SDK lint jobs
must remain green, as must engine-specific ZIP packaging.

Manually, in a disposable real Ren'Py 7/8 test game, open a collection of
more than 80 entries, scroll, remove items and confirm stale tail rows vanish.
Rapidly replace a nested container with a scalar, navigate elsewhere and back,
then save/load or rollback while the browser polls. Compare and favourites
must reflect the latest observed values without stale old-generation rows.
No gameplay variables or save files may be written by the inspector.
