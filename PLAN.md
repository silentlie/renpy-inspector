# Current delivery plan (9 November 2026)

> **Active plan.** The detailed plan below this section is the original native-only proposal and is retained for historical context. Its "not implemented", "Ren'Py 8 only", and "no external UI" statements no longer describe the repository.

## Milestone: PR #7 — external Ant Design foundation (v0.6.0 experimental)

**Goal:** Ship the optional separate browser-based inspector without breaking the native F8 overlay or Ren'Py 7/8 drop-in installation.

- ✅ Python 2.7/3-compatible, opt-in authenticated loopback server; serialized read-only snapshots and bounded inspection.
- ✅ React + Ant Design 6 client, connected Store/Persistent tree, browser-local favourites, basic overview and details.
- ✅ Responsive layout fix based on real screenshots; package static assets inside both engine ZIPs without Node.js at runtime.
- ✅ Unit tests, all four Ren'Py SDK lint targets, frontend build and both preview packages pass CI.
- ⚠️ Real-game testing confirms browser connects and UI renders on a Ren'Py 7 game; save/load/rollback, FPS, startup on varied OSes and Ren'Py 8 interactive testing remain open.
- **Merge gate:** Green CI and documented experimental limitations. Publish only a *prerelease*; retain read-only semantics and native fallback.

## Milestone: PR #8 — SugarCube codex/dev-inspired external-only interface

**Reference:** [SugarCube Inspector codex/dev](https://github.com/silentlie/sugarcube-inspector/tree/codex/dev) at `0f533358` (version 1.0.0). Copy design patterns, not its MAIN-world JavaScript inspection/editing.

1. Replace permanent explorer/sidebar + details dashboard with a single full-width Ant Design variable workspace.
2. Top-level **Overview / Variables / Scripts** tabs. Variables has nested **Store / Persistent / Favourites** scopes.
3. Show key and type together, right-aligned short preview, and explicit pin actions in each virtualized tree row. Maintain keyboard and mouse expansion and selection.
4. Show longer values and full paths **on demand** in a detail drawer or expandable panel, never by squeezing the main tree.
5. Keep bounded snapshots and the authenticated read-only bridge; preserve existing overview, search and browser-local favourites.
6. Remove the native inspector UI entirely; F8 starts the bridge and opens a browser, or reopens the existing browser session when already running.
7. Add focused UI/tree tests and responsive checks; package Ren'Py 7/8 preview ZIPs. Keep PR #8 a draft until browser geometry and game smoke tests are satisfactory.

## Milestone: PR #9 — auto-paged virtual tree (v0.6.2 experimental)

- Retain Ant Design virtual scrolling, but let entering a visible pagination
  sentinel **automatically** request the next bounded page.
- Expand a node to fetch its first children; no ordinary "Load More" button.
- Python 2.7/3 typed-path validation and authenticated read-only GET-only
  paging. HTTP workers queue only primitive arguments; Ren'Py's timer resolves
  requests on the game thread, then serialises bounded JSON results.
- Limit each page to 80 children, each branch to 1,000 entries, depth to eight,
  browser-loaded nodes to 6,000 and queued jobs to eight.
- Preserve expanded pages when shallow root previews update; cancel requests
  and reset generation after game load.
- **Open questions for real-game testing:** virtual sentinel visibility,
  stale descendant previews, rapid expand/collapse, pause during menu overlays,
  FPS cost, and browser-favourite paths loaded out of order.
- **Do not merge** until CI plus Ren'Py 7 and 8 real-game tests pass.

## Milestone: PR #10 — SugarCube codex/dev-style live watcher (v0.6.3 experimental)

**Reference:** `silentlie/sugarcube-inspector`, branch `codex/dev`,
commit `0f533358`: `src/variables/watcher.ts`,
`src/variables/ui/VariableTree.tsx`,
`src/variables/nodes.ts`, and `src/variables/favorites.ts`.

- One shared scheduler; no per-node browser interval, no WebSocket dependency.
- Active Store/Persistent tree scopes own expanded-branch watches; collapsing
  a parent suspends descendant watches. Hidden scopes are paused.
- Favourites are independent watches and remain active while another tab is
  selected, as long as their pages are already present in browser memory.
- Poll at most two bounded page requests per tick, rotate across up to twelve
  subscribed pages, and reuse PR #9's read-only Ren'Py game-thread queue.
- Reconcile stable child keys, update live value previews, reset subsequent
  positional pages when direct child structure changes, and preserve expanded
  descendants when safe. Discard updates from stale save/load generations.
- Keep full-history Compare, persistent cross-port favourites, full-value
  inspection, editing, locking, and write APIs out of scope.

**Known gap:** A favourite from a branch never loaded in the current session
cannot yet subscribe by direct path. Live watches sample bounded pages (up to
twelve) rather than all visible and pinned data simultaneously. Python object
identity and full change records are not exposed. These require later backend
work and real-game performance validation.

**Merge order:** PR #9 must pass real-game validation and merge first. PR #10
is stacked on PR #9 and remains draft until its own CI and interactive tests pass.

## Milestone: PR #11 — independent and durable favourites (v0.6.4 experimental)

- Add authenticated, read-only direct-path value observation over the existing game-thread queue; avoid requiring ancestor expansion.
- Keep favourites watched in all browser tabs, with bounded scheduler throughput.
- Persist validated typed favourite paths in a dedicated inspector preferences file in Ren'Py's save directory, unaffected by localhost port rotation.
- Maintain strict Host/Origin and token enforcement. The sole PUT endpoint is scoped to inspector preferences, not gameplay or save data.
- Differentiate missing variables from uncollected ones, and resume when a path becomes available again.
- Provide migration from older origin-local favourite storage, Python 2/3 tests, and both engine packages.
- Gate merge on game-thread safety, failure handling, save/load and rollback smoke tests.

**Next:** capture bounded primitive change history and a Compare workspace after favourites are reliably sourced.

## Milestone: PR #12 — Change History and Compare (v0.6.5 experimental)

Reference: `silentlie/sugarcube-inspector`, branch `codex/dev`,
`src/variables/comparison.ts`, `src/variables/ui/VariableComparison.tsx` and
`src/variables/ui/FavoriteHistory.tsx` at commit `0f533358`.

- Observe existing shallow root snapshots, expanded-branch page polls and
  independently watched favourites; never inspect Ren'Py objects from HTTP
  workers and do not introduce a WebSocket dependency.
- Timestamp page/value observations on the game interaction thread. The browser
  ignores delayed older samples and deduplicates overlapping observations
  by stable typed variable path and sampled preview.
- Record the most recent 100 *observed primitive-preview transitions* in browser
  memory only. Track changes, added and removed variables where a complete
  parent sample or a direct path watch supports the conclusion.
- Reuse the second tab row for a full-height **Compare** workspace with change
  kind, before/after previews, capture timestamp, available script location and
  inspect-current-variable action. Add recent history in the details drawer.
- Retain the last selected Store/Persistent scope's watches while Compare
  is active; independent favourites are always watched.
- Clear comparison history and baselines on game load generation changes,
  and offer manual **Clear history** without resetting reliable baselines.
- Test deduplication, bounded retention, partial-page shifts, save/load epochs,
  long/truncated previews, and no history writes to gameplay saves.

**Limitations:** This is sampled polling, not full mutation tracking or a
transaction log. Ren'Py does not expose SugarCube's turns/passages; file/line
reflect only runtime metadata where available and are not necessarily the
cause of a change. Strings may be clipped, so Compare explicitly labels them
as previews. Rollback that does not advance the load generation may look like
a regular value transition. Real-game Ren'Py 7/8 interaction and FPS testing
remain required before merging.

## Milestone: PR #13 — bounded global variable Search & Reveal (v0.6.6)

- Follow SugarCube Inspector `codex/dev`'s search-and-reveal navigation
  behaviour without bringing unrestricted JavaScript reflection into Ren'Py.
- Add authenticated read-only `GET /api/v1/search` for Store/Persistent
  variable names and formatted typed paths, beyond the loaded tree.
  Queries are debounced (350ms), at least 2 characters and at most 64.
- Budget each game-thread search: 1,400 visited entries, 30 hits,
  five path levels, at most 100 children per non-root branch and 160 queued
  candidate branches. Report partial/limited results explicitly.
- Add `GET /api/v1/reveal` to revalidate an individual typed path on the
  game interaction thread and return its bounded ancestor chain.
- Browser materialises only the returned path, expands its ancestors,
  highlights the target and virtual-scrolls to its stable key without
  downloading every previous pagination page.
- Keep search results only inside the existing popup. No new permanent
  header, toolbar or footer. Esc closes; Enter reveals the first match.
- Confirm Python 2.7/3 compatibility, SDK lint, Chrome interaction tests,
  invalid/stale-path rejection and FPS with large Store namespaces.

**Limitations:** Search is not an exhaustive Python graph index; inaccessible
object members, children beyond per-branch budgets and changes occurring
between searches may not appear. Real-game Ren'Py 7/8 smoke testing is
required before merging.

## Milestone: PR #14 — Script Navigation (v0.6.7 experimental)

- Search user-facing labels and game-relative filenames from a bounded Ren'Py
  get_all_labels()/script.lookup() index, paginated at 40 labels. Scan up to
  4,000 candidate labels and report a partial index when capped.
- Show current file and line via renpy.get_filename_line() and best-effort
  return-stack summary, without misrepresenting return labels as the current
  call stack or change causes.
- Add a full-height Scripts workspace: independently scrolling label index,
  search, selected location, Copy location, and a source window centered on a
  selected label or current statement.
- Read at most 21 lines, 240 characters each from game-owned .rpy files up to
  1 MiB. Reject path traversal and symlinks leaving the game directory; do
  not expose arbitrary files or attempt to decode .rpyc source.
- Use only authenticated GET requests, a bounded game-thread queue, and the
  existing F8-only game integration. No gameplay jump/warp, labels execution,
  write APIs or external editor launch.
- Test Python 2.7/3, SDK lint Ren'Py 7/8, frontend responsiveness, compiled-only
  games, missing source and invalid path handling; package v0.6.7 previews.
- **Merge gate:** green CI plus interactive script index/source checks in a
  real Ren'Py 7 and 8 game, save/load and FPS verification.

## Milestone: PR #15 — Lifecycle correctness (v0.6.8 experimental)

- Register one cache-only restoration callback for `after_load_callbacks` and
  `after_default_callbacks`. Ren'Py documents default processing after
  rollback, save loads, and game startup. Older engines without the callback
  use a conservative in_rollback() probe on new interactions. Duplicate callbacks during load may
  advance the epoch twice; this is harmless and remains intentionally fail-safe.
- Clear Python inspector caches, increment the browser bridge generation,
  invalidate queued work with HTTP 409, and force the next game-thread tick
  to publish a fresh read-only snapshot. Never touch gameplay variables.
- Enforce monotonic epochs in browser tree and Compare tracking. Clear
  selection, expanded page state, old watch previews and transient search on
  restore, while retaining typed path favourites for independent re-resolution.
- Run Python 2/3 tests for queued work and restored snapshots, and browser tests
  for stale out-of-order epochs and change-history reset.
- **Merge gate:** green dual-engine CI **and** real-game Ren'Py 7/8 save/load,
  rollback, new-game, queued-request, favourites and FPS smoke. Tests of
  simulated callbacks do not establish that every customised game's overlay
  allows the callback and tick to run.

## Milestone: PR #16 — Bounded polling and performance evidence (v0.6.9 experimental)

- Cap concurrent **background** page and favourite watches to two, skipping
  requests already in flight while preserving fair round-robin scheduling.
  Do not change the transport or add per-row timers; interactive requests
  still use the existing authenticated, eight-job game-thread queue.
- Surface primitive-only, snapshot-sampled diagnostics in Overview: root
  scan duration, pending/peak/rejected queue jobs, completion counts, latest
  queue wait and game-thread request duration.
- Add reproducible Python 3 synthetic microbenchmarks for shallow root,
  nested child page and independent favourite value; record response bytes
  and median/p95/max timing in CI artifacts without inventing FPS claims.
- Run Python 2/3 regression and four Ren'Py SDK lint targets plus dual-engine
  preview packaging. Keep F8-only browser UI and gameplay data read-only.
- **Merge gate:** green CI, real-game Ren'Py 7/8 FPS, frame-time percentile,
  scrolling, overlay pause and queue-burst smoke against an unmodified game
  baseline. CI synthetic timings are diagnostic evidence, not live acceptance.
- Full measurement protocol: [docs/PERFORMANCE.md](docs/PERFORMANCE.md).

## Milestone: PR #17 — Installability and release reliability (v0.7.0 experimental)

- Fail closed when a release accidentally includes old inspector-native
  Ren'Py screens or unknown Python source modules. Require built JS/CSS.
- Verify pre-release ZIPs for SHA256, safe archive paths, missing payload,
  compiled browser references and Ren'Py 7/8 byte-for-byte parity.
- Add tests for incomplete/tampered archives, stale native UI files,
  incorrect installation nesting and missing browser bundles.
- Provide a read-only installation checker and actionable upgrade checklist.
- Align the main release series to v0.7.x; validate merged prerelease ZIPs
  before publication. Preserve F8-only browser architecture and read-only data.
- Do not require more FPS micro-optimisation without an observed regression.
- **Merge gate:** all CI jobs green, engine-specific preview artifacts verify,
  and interactive Ren'Py 7/8 F8, live reads, save/load, rollback and
  upgrade-game smoke. Manual coverage must be identified if incomplete.
- Full checklist: [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Milestone: PR #18 — Same-generation tree freshness (v0.7.1 experimental)

- Order root, child-page and independent favourite samples by their
  Ren'Py interaction-thread capture timestamps, not HTTP completion order.
- Reject stale page replies for a parent or root after newer captures, and
  avoid resurrecting child pages beneath scalar or missing containers.
- Trim previously loaded root tails and obsolete off-page breadcrumbs when
  the complete root now contains fewer entries.
- Preserve fresher descendants across shallow-root snapshots while keeping
  the same virtualised browser layout, bounds, two-in-flight background cap,
  authenticated HTTP protocol and read-only semantics.
- Run JS out-of-order/shrink regression tests and all Python 2/3, Ren'Py SDK,
  frontend build and dual-engine preview checks.
- **Merge gate:** CI green plus manual rapid mutation, paging, save/load and
  rollback smoke in Ren'Py 7 and 8; document limitations of preview-only
  detection when same-type objects are replaced without visible changes.
- Details: [docs/TREE_FRESHNESS.md](docs/TREE_FRESHNESS.md).

## Milestone: PR #19 — Browser-to-bridge end-to-end test automation (v0.7.2 experimental)

- Use Playwright Chromium against a compiled production React/Ant Design UI
  served by the real authenticated 127.0.0.1 Python bridge, not an API mock.
- Run synthetic game-thread providers in a disposable Python subprocess;
  drive state changes via private process stdin, never gameplay HTTP writes.
- Automate auth, browser connection, script source, global search/reveal,
  independent favourites and generation reset, and virtualised pagination.
- Wire a required CI E2E job (with traces/screenshots on failure) to gate
  preview packaging; keep Python 2/3 and four SDK lint jobs.
- Explicitly separate this suite from real Ren'Py F8, overlay, native
  save/load/rollback and FPS E2E, which still require actual engine execution.
- **Merge gate:** all CI green, stable browser/bridge scenarios, manual
  engine smoke or explicit disclosure of missing real-engine automation.
- Details: [docs/E2E_TESTING.md](docs/E2E_TESTING.md).

## Later milestones (not PR #9)

- **Freshness for expanded branches:** refresh only watched/visible child pages,
  reconcile object replacements, and invalidate nested paths after rollback.
  Add tests for deep favourites and concurrent page requests.
- **Compare/history:** bounded, read-only primitive change history, with named context and clear retention semantics.
- **Scripts/source navigation:** only data Ren'Py safely exposes; do not imply SugarCube's Twine passage-source APIs transfer.
- **Editing, locks and undo/redo:** explicitly out of scope pending separate rollback/write-safety design.

## Validation rules

Passing SDK lint is not an interactive runtime certification. Before claiming production reliability, check browser connection, save/load/rollback, stale data invalidation, FPS and UI geometry in actual games. Do not silently merge experimental features or treat available previews as final releases.

---

# Historical proposal (superseded)

# Ren'Py Inspector: Complete Development Plan

> **Status:** Proposed architecture and implementation plan. No mod has been implemented yet.
>
> **Reference project:** [SugarCube Inspector](https://github.com/silentlie/sugarcube-inspector)
>
> **Target repository:** `silentlie/renpy-inspector` (public)

## Project summary

Build a standalone, drop-in Ren'Py mod that provides live inspection of game state through a native in-game drawer. Reuse the *design principles*, not the browser-specific implementation, of SugarCube Inspector: lazy expansion, path-based locations, scoped subscriptions, stable tree nodes, explicit favourites, and low-overhead refresh.

### Agreed decisions

| Decision | Approach |
| --- | --- |
| Platform | Existing Ren'Py desktop games |
| Packaging | Drop-in `.rpy` files plus a pure-Python package inside `game/` |
| UI | Native Ren'Py Screen Language |
| Architecture | Inspection core separate from UI and Ren'Py integration |
| Access | Direct in-process Python inspection; no RPC or external application |
| Scheduler | One native screen timer for all active subscriptions |
| Refresh interval | User-configurable, 250 ms default |
| Polling disabled | `0` means manual refresh only |
| Tree | Lazy expansion, structural snapshots, stable-node reconciliation |
| Rendering | Fixed-height rows using native `vpgrid`, subject to benchmarking |
| Favourites | Root-relative paths, independently watched while inspector is open |
| Configuration | Separate user settings, not gameplay save variables |
| Initial feature scope | Read-only |
| Initial compatibility target | Ren'Py 8.x desktop; test 8.4 and 8.5 first |
| Deferred compatibility | Ren'Py 7.x, mobile, heavily customised or locked-down runtimes |

**Assumptions and verification:** Compatibility targets, update performance, save isolation, and `vpgrid` scalability are design hypotheses until exercised against real game fixtures. A mod that works on stock Ren'Py cannot automatically be guaranteed to work with every shipped game.

## 1. Goals and non-goals

### Goals

1. Install in a supported existing desktop game without editing its original story scripts.
2. Inspect live Python store values and persistent data directly.
3. Browse nested values with lazy tree expansion and meaningful type/value previews.
4. Follow changes to displayed values and expanded structures with one shared, configurable polling system.
5. Maintain favourites that survive object replacement and missing paths.
6. Keep UI and runtime overhead low enough not to interfere materially with gameplay.
7. Treat save, load, and rollback compatibility as primary correctness requirements.
8. Keep the inspection core independently testable outside the Ren'Py renderer.

### Non-goals for the first release

- Mutating game variables, evaluating arbitrary Python code, or offering a cheat console.
- Debugger-level stepping, breakpoints, or arbitrary source navigation.
- A separate React or desktop client, network bridge, or process injection.
- Guaranteed support for every existing Ren'Py game and every engine fork.
- Ren'Py 7.x / Python 2, mobile builds, and games that reject modified content.
- Per-variable refresh schedules, adaptive polling, or background worker threads.

## 2. Feature priorities

| Feature | Priority | Milestone |
| --- | --- | --- |
| Drop-in mod installation | P0 | 1 |
| Native open/close drawer | P0 | 1 |
| Default Python store inspection | P0 | 1–2 |
| Persistent-variable inspection | P0 | 2 |
| Nested Python values | P0 | 2 |
| Lazy child discovery and cycle prevention | P0 | 2 |
| Live value and structural updates | P0 | 3 |
| Custom refresh interval and manual refresh | P0 | 3 |
| Scrollable and efficient tree | P0 | 4 |
| Error isolation and save/load/rollback safety | P0 | 2–6 |
| Favourites and explicit watches | P1 | 5 |
| Search and filtering | P1 | 5 |
| Configurable drawer width and appearance | P1 | 4–5 |
| Configured named stores, then discovery | P1 | 5 |
| Overview and script/context panel | P1 | 5 |
| Screen-local variable inspection | P2 | Later |
| Variable editing | P2 | Later |
| Snapshot export, change history | P2 | Later |

**Release interpretation:** P0 is the minimum useful read-only inspector. P1 completes the planned first read-only release. P2 follows only after the core design is validated.

## 3. Architecture

```text
Ren'Py Inspector UI
  ├─ Drawer / tabs / variable tree
  ├─ Favourites / Overview / Scripts / Settings
  └─ User interactions
               │
               ▼
Inspector Controller
  ├─ Drawer lifecycle and active scope
  ├─ Expanded nodes and visible rows
  └─ UI invalidation / refresh requests
               │
               ▼
Inspection Core (pure Python where practical)
  ├─ Locations and path resolution
  ├─ Safe reads, snapshots, formatting
  ├─ Child discovery and node reconciliation
  ├─ Scoped subscriptions and watcher
  ├─ Favourites
  └─ Configuration
               │
               ▼
Ren'Py Runtime Adapter
  ├─ Default / named stores
  ├─ persistent
  ├─ game lifecycle hooks
  └─ Ren'Py interaction/timer integration
```

### Separation of responsibilities

- **Runtime adapter:** Obtains trusted root objects and responds to Ren'Py lifecycle events. Does not render the interface.
- **Inspection core:** Reads and compares Python objects. Does not depend on drawer layout or screen widgets.
- **Controller:** Owns selected scope, expansion state, active subscriptions, and one-time UI invalidation after a changed polling cycle.
- **UI:** Displays snapshots and invokes controller methods; it does not recursively inspect arbitrary game objects while rendering.

### Repository layout

```text
renpy-inspector/
├── PLAN.md
├── README.md
├── game/
│   ├── renpy_inspector.rpy
│   ├── renpy_inspector_screens.rpy
│   ├── renpy_inspector_styles.rpy
│   └── renpy_inspector/
│       ├── __init__.py
│       ├── config.py
│       ├── controller.py
│       ├── location.py
│       ├── inspection.py
│       ├── structure.py
│       ├── nodes.py
│       ├── watcher.py
│       ├── favorites.py
│       └── formatting.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── benchmarks/
├── scripts/
└── docs/
```

This is a proposed layout, not an instruction to create empty modules in advance. Add each module when its responsibilities are implemented.

### Save/rollback isolation principle

Keep inspector-owned caches and watchers outside gameplay store state whenever practical, using an imported Python package. Never store live Python game-object references in persisted inspector settings. Avoid accidentally putting mutable inspector bookkeeping into rollback-aware gameplay variables.

**Caution:** Being read-only is necessary but not sufficient for safe installation and removal. Load/save tests must verify that the mod does not introduce unwanted serialised references or alter normal rollback behaviour.

## 4. Scope and location model

### 4.1 Root scopes

| Scope | Purpose | Default behaviour |
| --- | --- | --- |
| **Store** | Default `store` namespace and game variables | Filter Ren'Py internals by default, with an option to reveal them |
| **Persistent** | Variables on `persistent` | Separate tab, read-only |
| **Named stores** | Other game namespaces such as `store.characters` | Support configured roots first, then safe discovery |
| **Favourites** | Explicitly pinned root-relative locations | Watch across scope changes while drawer remains open |

Screen-local variables are deferred: a selected screen's variables may be readable through supported Ren'Py APIs, but enumerating every local across every screen is not assumed to be available.

### 4.2 Location representation

Represent a location as a trusted root plus typed path segments. Suggested segments include:

- Object attribute name.
- Dictionary key (with type and identity considerations).
- Sequence index.
- Set member (inspection-only for the initial implementation).

There are two relevant lifetimes:

- **Tree locations:** May retain a current owner for efficient direct reads while the node is live.
- **Favourite locations:** Always store a root-relative path and re-resolve it against the current game state after replacements and load/rollback.

A missing path remains a valid subscribed location and is displayed as *missing*, rather than silently deleted.

### 4.3 Snapshot model

Use a discriminated read result:

```python
# Conceptual model, not implementation code.
VariableRead = Value(value) | Accessor(kind) | Missing() | Error(details)
VariableSnapshot = VariableRead + stable type/preview metadata
```

Compare value identity and captured previews separately from structural information. This is important for Python lists, dictionaries and custom objects that can mutate in place without changing identity.

A snapshot should carry only the information required for display and comparison. Do not deep-clone entire game objects merely to check whether one field changed.

## 5. Python value support and safe inspection

| Python value | Behaviour |
| --- | --- |
| `None`, `bool`, integers, floats | Leaf with typed preview |
| `str`, `bytes` | Escaped, length-limited preview |
| `list`, `tuple` | Children by index |
| `dict` | Entries by key; handle non-string/object keys carefully |
| `set`, `frozenset` | Members inspectable, initially non-favouritable |
| Instances | Inspect ordinary instance attributes where available |
| Functions/classes/modules | Limited metadata, avoid uncontrolled expansion |
| `property` and descriptors | Show accessor marker without invoking arbitrary getter |
| Cyclic references | Mark and stop descending the ancestor cycle |
| Unsupported/problematic objects | Error state or conservative preview |

### Required safeguards

- Do not call arbitrary `repr()`, `str()`, properties, or custom getters during routine polling.
- Prefer `vars()` / `__dict__` and static attribute inspection where applicable, with explicit handling of `__slots__` and descriptors.
- Do not assume introspection itself is side-effect free; isolate errors per location.
- Cap preview lengths and enumeration work per expansion to avoid freezing the game on hostile or huge collections.
- Escape values for Ren'Py's text markup before displaying them.
- Avoid introspecting most engine/internal objects by default, but allow users to reveal filtered variables.
- Support Ren'Py rollback-aware list/dictionary/set variants where practical.

### Lazy expansion and reconciliation

1. Render a node without recursively constructing all descendants.
2. When expanded, read the current value and enumerate only immediate children.
3. Match new child locations against existing children using stable, typed identities.
4. Reuse unchanged child nodes and arrays; replace only changed branches.
5. Retain expanded-node structural watches even if the corresponding rows are scrolled offscreen.
6. Mark ancestor references so cycles cannot trigger unbounded traversal.
7. Re-resolve root-relative paths after replacement, load, and rollback.

For dictionary keys or set members that are arbitrary objects, the initial solution may use inspection-only identities rather than promise stable, persisted paths. Define and test these semantics instead of hiding the ambiguity.

## 6. Shared polling and subscriptions

### 6.1 Behaviour

Use **one** active timer, never one timer per variable. The timer exists only while the inspector is open, an active subscription requires checking, and the interval is greater than zero.

The scheduler checks watched value snapshots and expanded structural snapshots, compares them, reconciles changed nodes, and requests **one** UI refresh if displayed data changed.

Ren'Py can refresh screens during user interactions, but it does not give the inspector a general notification whenever an arbitrary nested Python value changes. Polling is therefore appropriate for reliable live updates.

### 6.2 Configuration

Use milliseconds in settings and seconds for Ren'Py's timer API.

```json
{
  "refresh_interval_ms": 250,
  "poll_when_hidden": false,
  "show_private_variables": false,
  "drawer_width": 440
}
```

| Setting | Proposed semantics |
| --- | --- |
| `refresh_interval_ms: 0` | Manual refresh only; no recurring timer |
| `100` | Nominal 10 polls/sec |
| `250` | Default, nominal 4 polls/sec |
| `500` | Nominal 2 polls/sec |
| `1000` | Nominal 1 poll/sec |
| Any supported custom interval | Applied immediately after validation |

Recommended validation: integer milliseconds, with 0 as the sole disabled value and a practical minimum of **50 ms** for positive values. Keep this minimum configurable in the implementation if benchmarks justify a different bound.

Intervals are scheduling targets, not hard real-time deadlines. A busy game/render thread can delay checks.

### 6.3 Integration sketch

```renpy
# Illustration only; final definitions will depend on the integration layer.
screen renpy_inspector_drawer():
    if inspector.is_open and inspector.interval > 0:
        timer inspector.interval repeat True action Function(
            inspector.tick,
            _update_screens=False
        )
```

`inspector.tick()` should return `None`, perform all inspections on the Ren'Py/game thread, suppress routine errors per subscription, and invoke `renpy.restart_interaction()` only if a visible result changed. Explicit manual refresh should use the same check/reconcile code path. Guard against duplicate polling caused by interaction restarts or stale timer instances.

### 6.4 Lifecycle table

| Event | Watcher action |
| --- | --- |
| Drawer opens | Activate the selected scope and catch up immediately |
| Drawer closes | Suspend timer and release inactive subscriptions |
| Scope changes | Deactivate old scope; activate and immediately refresh new scope |
| Node expands | Discover immediate children; add structural subscription |
| Node collapses | Release descendant subscriptions |
| Expanded node scrolls offscreen | Retain structural watch for logical tree correctness |
| Favourite is offscreen | Continue its explicit value watch while drawer is open |
| Refresh interval changes | Replace/update the one active timer |
| Interval becomes 0 | Stop periodic timer; keep manual refresh |
| Save/load/rollback/new game | Re-resolve current state, invalidate stale cache as necessary |

### 6.5 Scope rules

Keep one shared scheduler with scope groups such as `store`, `persistent`, `named:<name>`, `favorites`, and `favorites-tree`. Only the selected main variable scope is active; favourites are independent explicit subscriptions while the drawer is open. Disable descendant/tree polling when the corresponding favourites tree is not displayed unless those descendants are required elsewhere.

This intentionally follows the working SugarCube Inspector subscription design without bringing over its JavaScript scheduler.

## 7. Native user interface

### 7.1 Layout

A right-edge drawer with tabs: **Overview**, **Variables**, **Scripts**, and **Settings**. Under Variables: **Store**, **Persistent**, **Named Stores** and **Favourites** as applicable.

Conceptual text mockup:

```text
┌──────────────────────────────────────────┐
│ ▣ Ren'Py Inspector                 [ × ] │
├──────────────────────────────────────────┤
│ Overview   Variables   Scripts  Settings │
│ [Store]  Persistent  Favourites          │
├──────────────────────────────────────────┤
│ ▾ player: object                        ☆ │
│   name: str                       "Alice" │
│   health: int                        100 │
│   ▾ inventory: list               3 items │
│     0                             "Sword" │
│     1                            "Potion" │
│     2                               "Key" │
├──────────────────────────────────────────┤
│ ↻ Refresh: 250 ms             Read-only   │
└──────────────────────────────────────────┘
```

### 7.2 Interaction behaviour

- Open and close via an unobtrusive right-edge tab and configurable keyboard shortcut.
- Implement click-to-toggle first. Add hover-to-open and a draggable tab only after the core UI is stable.
- Support adjustable width, constrained to the game viewport.
- Row title and chevron both expand or collapse a container.
- Type appears next to the key; value is right-aligned when space permits.
- Use connectors/indentation to convey tree hierarchy.
- Support mouse wheel and keyboard navigation; test input capture against the game's keymaps.
- Keep settings and controls visually scoped so they do not disturb the host game's layout.

### 7.3 Tree performance

Flatten *expanded logical nodes* into a row sequence and display fixed-height rows through Ren'Py's `vpgrid`, which supports viewport-based rendering under its sizing constraints.

Do not assume this makes every stage cheap: benchmark child displayable construction, text rendering, scroll performance, and any Ren'Py layout work. If a 10,000-row logical tree is still expensive, build a custom windowed adapter only after measuring the bottleneck.

### 7.4 Predictable rendering

Do not perform mutation, polling, user-defined attribute access, or tree reconciliation directly in screen expressions. Screens may be evaluated more than once for reasons unrelated to a user-visible refresh. Keep expensive and effectful work in the controller/watcher and render cached snapshots.

## 8. Favourites and explicit watches

Examples of intended user-facing paths:

```python
store.player.health
store.inventory["weapon"]
persistent.unlocked_gallery
```

A favourite stores a canonical, root-relative path, not a long-lived reference to the currently held game object. It should:

1. Continue to exist when a path becomes temporarily missing.
2. Reconnect when the path becomes valid again.
3. Follow replacement of ancestor objects at the same path.
4. Update its displayed snapshot while the drawer is open, even when another scope tab is selected.
5. Persist its serialisable path definition in inspector settings.

Initially permit favourites for named attributes, stable string/int dictionary keys and sequence indices. Document that an index follows the *position*, not the original list element. Defer persistence for object-valued dictionary keys and set members until a safe, deterministic model exists.

## 9. Save, load, rollback and installation safety

### Invariants

- Never mutate inspected gameplay values in read-only mode.
- Do not serialize inspector-owned caches, live object references, watcher callbacks, or UI state into gameplay saves.
- After loading, discard stale snapshots and resolve paths against the newly loaded state.
- After rollback, display the restored state rather than previous cached values.
- When a new game starts, clear session-specific tree/cache state but preserve user settings.
- Removal should leave original game scripts unchanged; save compatibility must be tested rather than assumed.

### Lifecycle integration

Use documented Ren'Py lifecycle hooks where appropriate (for example, after-load callbacks) for invalidation. Do not rely exclusively on a callback for rollback; path-based reads and explicit UI refresh are also required.

Run dedicated regression scenarios: save with inspector closed, save with drawer open, load after changing variables, rollback nested mutations, save/load with favourites, new game, and load after mod removal. On reload, old direct-owner tree locations must be invalidated even when root-relative favourites survive.

**Risk:** Some games customise save screens, overlays, keymaps or startup behaviour; the mod must fail safely, not break gameplay when an integration hook is unavailable.

## 10. Error handling and security boundaries

- Handle inspection errors per node/subscription and continue checking independent watches.
- Distinguish missing values from exceptions and unsupported/unsafe values.
- Do not silently swallow a persistent failure: surface an unobtrusive error marker and optionally diagnostic details.
- Bound work per tick and per expansion. Avoid unbounded recursion and enormous previews.
- Do not execute arbitrary expressions or custom getters merely to inspect them.
- Render escaped text and cap display lengths.
- Run locally; no telemetry, network connectivity, debugger attachment, or external communication.
- Ensure inspectable game objects cannot force inspector crashes via malicious `repr`, `str`, iteration or descriptor behaviour where avoidable.

## 11. Overview and script/context panels

### Overview

Show game title when available, Ren'Py version, selected inspection scope, active favourites, configured polling interval, and optional watcher diagnostics (number of active subscriptions, most recent poll duration, and whether a change was observed).

### Scripts

Show currently available script location and execution/return context using documented Ren'Py APIs where supported. This is contextual read-only information, **not** a complete debugger. Source browsing, jumping, stepping, breakpoints, and arbitrary evaluation are deferred.

## 12. Development milestones

### Phase 1: Runtime integration proof of concept

**Work:** Create drop-in files, register the overlay screen, add a stable open/close interaction, read a few simple default-store values.

**Exit criteria:** Installs in a clean fixture game without changing original scripts; does not prevent normal game input.

### Phase 2: Inspection core

**Work:** Implement typed locations, safe snapshots, Python collection support, lazy child discovery, cycles, node IDs/reconciliation and isolated errors.

**Exit criteria:** Unit tests cover nested objects, replacement, in-place mutations, missing locations, descriptor safety, and unsupported values.

### Phase 3: Watcher and custom polling

**Work:** Implement shared subscriptions, structural/value comparisons, timer integration, active scopes, immediate catch-up, manual refresh, and settings persistence.

**Exit criteria:** Values and structural changes refresh at configured intervals; no hidden polling; disabled mode works; switching scopes produces no stale state.

### Phase 4: Native variable tree and drawer

**Work:** Implement row rendering, expand/collapse, scrolling, type syntax styling, width controls, input handling, and initial viewport performance measurements.

**Exit criteria:** Large nested collections remain navigable; no eager deep recursion; UI remains usable on supported game resolutions.

### Phase 5: Favourites and supporting panels

**Work:** Add path favourites, independent subscriptions, settings, search/filtering, named-store support, Overview and minimal Scripts panel.

**Exit criteria:** Favourites survive restart, missing paths, and ancestor replacement; other panels do not introduce unnecessary polling.

### Phase 6: Correctness, compatibility and performance

**Work:** Save/load/rollback regression tests, malformed-object tests, UI conflict tests, multiple engine versions and benchmark suites.

**Exit criteria:** Release compatibility matrix passes, known limitations are documented, and measured overhead is acceptable.

### Phase 7: Release and documentation

**Work:** Produce versioned release ZIP, installation/uninstallation instructions, configuration docs, examples, troubleshooting and known-compatibility notes.

**Exit criteria:** A supported user can copy the provided files into a game's `game/` directory and use the inspector without installing developer tools.

## 13. Test plan and benchmarks

### Functional tests

| Scenario | Expected result |
| --- | --- |
| Scalar value changes | Preview updates at the next supported check |
| Parent object replaced | Watched root-relative paths resolve the new object |
| List append/remove | Child structure updates without rebuilding unrelated branches |
| Dictionary key add/remove | Added/removed nodes reconcile correctly |
| Nested in-place mutation | Relevant value or structure watcher detects it |
| Cyclic object graph | Expansion stops at ancestor cycle |
| Getter with side effects | Not invoked during inspection |
| Object's `repr()` raises | Inspector continues, shows safe fallback |
| Favourite path disappears | Still pinned and reports missing |
| Favourite path reappears | Automatically reconnects |
| Hidden drawer | No recurring polling |
| Poll interval changed | Updated interval applies without duplicate timers |
| Interval 0 | Only explicit/manual and relevant interaction refreshes occur |
| Save/load/rollback | Correct restored state, no stale references |
| Mod removed | Original scripts unchanged; tested save compatibility |
| Large tree (1k+/10k entries) | Usable expansion and scrolling within measured limits |

### Benchmark matrix

Measure at least four states:

1. Game without mod.
2. Mod installed, drawer closed.
3. Drawer open, values idle.
4. Drawer open, multiple values/structures actively changing.

Vary:

- 100 / 1,000 / 10,000 discovered logical entries.
- Few vs many active subscriptions.
- 100 ms / 250 ms / 500 ms intervals (plus disabled mode).
- Shallow objects vs deeply nested / cyclic collections.

Record poll duration, reconciliation duration, UI refresh time, frame-time distribution, memory footprint and perceived scroll responsiveness. Distinguish time spent in our inspection core from Ren'Py layout/rendering work. Define measurable release thresholds **after baseline runs**, not by guessing an FPS number beforehand.

### Benchmark-driven simplification rule

Do not add adaptive polling, worker threads, per-variable timers, speculative caches or custom tree virtualization unless profiling identifies a problem and an alternative demonstrably improves results. Preserve the simplest measured-correct design.

## 14. Distribution and compatibility

### Packaging

Ship a versioned ZIP whose contents can be copied directly into the supported game's `game/` directory. Include the `.rpy` entrypoints and the Python package. Do not overwrite or patch the game's existing story files.

### Documentation

Provide:

- Install and uninstall instructions.
- Supported Ren'Py versions/platforms and compatibility limitations.
- Keyboard shortcut and drawer controls.
- Configuration syntax and interval semantics.
- Favourites and path identity limitations.
- Save/load/rollback caveats and troubleshooting.
- A read-only disclaimer and security/inspection limitations.

### Version and compatibility policy

Start with Ren'Py 8.x desktop support and test designated minor releases before claiming compatibility. Treat Ren'Py 7.x as separate due to Python runtime differences. Mobile and aggressively customised games remain unverified until tested.

## 15. First-release definition of done

- [ ] Works as a drop-in mod on the supported compatibility matrix.
- [ ] Opens/closes a native drawer without breaking normal game input.
- [ ] Displays default store, persistent and configured named stores.
- [ ] Inspects nested Python structures safely and lazily.
- [ ] Updates values and structures after mutation or object replacement.
- [ ] Retains active watches for expanded offscreen branches.
- [ ] Has one configurable shared refresh timer; supports arbitrary valid intervals and `0`.
- [ ] Provides a manual refresh path and immediate catch-up on scope activation.
- [ ] Allows favourites with safe, persisted root-relative paths.
- [ ] Remains correct after save/load/rollback and new-game transitions.
- [ ] Isolates problematic objects and errors rather than terminating gameplay.
- [ ] Has benchmark evidence against an unmodified baseline.
- [ ] Has an installable release ZIP and complete setup/troubleshooting documentation.

## 16. Implementation order and decisions to validate

**Recommended starting order:** Runtime integration proof of concept → pure-Python inspection core → shared watcher and configurable timer → UI tree → favourites → compatibility/performance → release. The early integration proof should establish that overlay input and screen timers work in a real Ren'Py game without affecting gameplay.

Design questions to settle through prototypes and tests, not assumptions:

1. Which exact Ren'Py 8.x versions and released games are included in the support matrix?
2. Can native `vpgrid` meet frame-time and scrolling goals without a custom windowing layer?
3. Which Python/Ren'Py collection types need specialised structural comparison?
4. How should favourite paths behave with non-primitive dictionary keys and set members?
5. Where can user JSON settings safely persist across all supported desktop platforms?
6. What lifecycle hooks and invalidation rules are necessary for load, rollback, and mod removal?
7. What performance threshold is appropriate relative to an unmodified fixture game?

The core design intentionally remains read-only. Variable editing and arbitrary code execution should only be considered as separate features with explicit semantics for Ren'Py rollback and persistent state.

---

### Reference documentation to consult during implementation

- [Ren'Py documentation](https://www.renpy.org/doc/html/)
- [Ren'Py Screens and Screen Actions](https://www.renpy.org/doc/html/screens.html)
- [Ren'Py Screen Language](https://www.renpy.org/doc/html/screen_language.html)
- [Ren'Py Python Statements and Modules](https://www.renpy.org/doc/html/python.html)
- [Ren'Py Save, Load, and Rollback](https://www.renpy.org/doc/html/save_load_rollback.html)
- [SugarCube Inspector reference implementation](https://github.com/silentlie/sugarcube-inspector)

> Documentation links above are implementation references. Before release, validate behaviours against the exact Ren'Py engine versions supported by the mod.