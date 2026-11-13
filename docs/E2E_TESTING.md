# Browser-to-bridge end-to-end tests (PR #19, v0.7.2)

The automated end-to-end suite runs **the real React/Ant Design production
build and the real authenticated `InspectorBridge` HTTP server** in headless
Chromium. It tests the complete browser-to-Python transport path, including the
real queue, game-thread style tick, serializer, authentication and UI.

## How to run

From the repository root:

```sh
cd web
npm install --no-audit --no-fund
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

On Windows/macOS, install Chromium with `npx playwright install chromium`;
the `--with-deps` switch mainly provisions supported Linux dependencies.
To see the browser locally, run `npm run test:e2e:headed`.

The five scenarios each launch a new local Python 3 subprocess running
`scripts/e2e_bridge_fixture.py`; the fixture uses a random 127.0.0.1 port,
a fresh random token, a temporary inspector preferences directory and
controlled synthetic Store/Persistent providers. It serves the compiled files
from `web/dist`, not the Vite dev server. No internet service or game save
directory is used.

## Automated coverage

| End-to-end scenario | What it proves |
| --- | --- |
| Real localhost auth + navigation | Valid token, rejected missing/foreign origins, browser connects and Overview/Variables render |
| Live favourite + game replacement | Typed-path pin, snapshot/watch updates, simulated lifecycle generation reset, browser reload retains preference metadata |
| Search and reveal | Bounded search and reveal requests traverse the real bridge queue and update the visible virtual tree |
| Script index and source | Actual queued `scripts` and `source` routes display a game-directory-only excerpt |
| Expansion/pagination | A 170-item branch requests additional pages when scrolling near its virtualised end |

The suite changes fake game values through the child process's **stdin**;
it does not create a write endpoint or bypass the read-only inspector security
boundary. Every test starts and stops its own HTTP server and preferences file.

CI runs the suite as a required `browser-bridge-e2e` job on Linux with Node
22, Python 3.13 and Playwright Chromium. Failed runs upload screenshots,
traces, and an HTML report as a GitHub Actions artifact. Both Ren'Py 7 and
Ren'Py 8 preview installer ZIPs are gated on the result.

## Real Ren'Py graphical SDK smoke (PR #20, v0.7.3)

This is a **second, independent test layer**, using the real Ren'Py SDK
interpreter, game event loop, display, native overlay hotkey, save and
rollback semantics. It is not built on the fake bridge fixture.

GitHub Actions matrix runs **Ren'Py 7.8.7 and 8.5.3** on Ubuntu 24.04 under
Xvfb, with software OpenGL, dummy audio and `xdotool` keyboard injection.

- A disposable project is assembled from the repo's Ren'Py-compatible
  source and a fixture-only `script.rpy`. The production Vite `dist/`
  assets are copied to `game/renpy_inspector_web/`.
- The actual SDK game process runs in a virtual graphical display;
  the test finds its real window and sends **F8 twice**, confirming that
  the same authenticated token and localhost port are reused.
- The disposable fixture instruments Python's `webbrowser.open` only
  inside the test game: it records the actual URL passed by the real F8
  handler and returns success instead of opening an OS desktop browser.
  A `BROWSER` helper is also provided as a fallback. Playwright Chromium
  then opens that exact authenticated session and verifies the real React
  inspector and HTTP API. This **does not test OS default-browser
  associations**, which remain a manual compatibility check.
- It checks `e2e_value` in real Ren'Py Store, then sends **Space** to
  advance a real dialogue and observes the changed state in the HTTP
  snapshot and browser.
- Fixture-only **F5** and **F9** keys invoke Ren'Py's native `FileSave`
  and `FileLoad` actions. The test observes restored values and a
  new inspector generation after the real engine invokes callbacks.
- **PageUp** triggers the normal Ren'Py rollback key binding, with an
  expected lifecycle generation change. Rollback may settle at a different
  preceding dialogue checkpoint across supported versions, so the test
  checks generation correctness without inventing a universal exact line.
- The expanded runtime regression (PR #21) pins a real Store variable and
  verifies inspector-owned preferences through the authenticated GET,
  Ren'Py's native save/load cycle, and a genuine Chromium page reload.
- A 170-item Ren'Py list is expanded in the virtual tree. Playwright scrolls
  until the browser requests child offset 80, then uses a fixture-only **F6**
  SetVariable action to shrink the list to 12. Both HTTP pagination and the
  browser preview must report the reduced collection.
- A live nested dictionary is expanded, its `hp` child pinned, then replaced
  with an integer via fixture-only **F7**. The UI must drop the obsolete
  child, while the favourite transitions to `<missing>` and stays pinned
  after a browser reload. All mutations occur inside the disposable game,
  not via the bridge HTTP API.

To reproduce locally on Linux, install the Ren'Py SDK and prerequisites
(`xvfb`, `xauth`, `xdotool`, Playwright Chromium and its OS libraries),
and create the fixture as CI does:

```sh
python scripts/prepare_fixture.py /tmp/renpy-runtime-fixture
cp tests/fixtures/renpy-runtime-script.rpy /tmp/renpy-runtime-fixture/game/script.rpy
cd web
npm install --no-audit --no-fund
npm run build
mkdir -p /tmp/renpy-runtime-fixture/game/renpy_inspector_web
cp -R dist/. /tmp/renpy-runtime-fixture/game/renpy_inspector_web/
npx playwright install --with-deps chromium
RENPY_SDK_SCRIPT=/path/to/renpy-sdk/renpy.sh \
RENPY_E2E_PROJECT=/tmp/renpy-runtime-fixture \
RENPY_VERSION=8.5.3 \
xvfb-run -a -s "-screen 0 1920x1080x24" npm run test:e2e:engine
```

**Limitations:** This proves supported Linux graphical SDKs work in a
disposable game, not all operating systems, modified game overlay keymaps,
performance under heavy gameplay, source-only distributions, or every
Ren'Py release. CI keeps the older four-version **lint** matrix and only
uses two versions for expensive graphical execution. On failure, CI saves
the engine log, browser screenshot and Playwright trace as artifacts.
These are correctness tests, not FPS benchmarks.

## PR #22: On-demand full-value inspection

The browser details drawer has a **Show full value** action. It sends one
authenticated `GET /api/v1/full-value` request for the selected typed path
through the existing Ren'Py game-thread queue. Requests are never made from
ordinary tree polling, independent favourite watches or Compare.

Browser E2E tests verify a complete multiline/Unicode string, 16,384-character
truncation and disabled incomplete-value copying, unsupported objects and
HTTP authentication/Origin/method rejection. Python 2/3 tests verify safe
path resolution and that custom object repr/str/properties are not invoked.
The graphical SDK tests additionally read an actual Ren'Py Store integer
using the new route. These tests do not assert that arbitrary game objects
or strings beyond the budget can be fully captured.

## PR #23: Exact typed-path navigation

The same search popup recognises `store.` and `persistent.` paths. Plain
names still use bounded fuzzy search, while exact paths become validated
typed segments passed to the existing `/api/v1/reveal` job queue. UI results
scroll to a revealed row without downloading all intermediate pages.

The JS tests exercise escaped/Unicode mapping keys, integer mapping keys,
list indexes, scope switching, limits and malformed expressions. Chromium
tests verify deep reveal, navigation to an initially off-page list entry,
persistent dictionary keys and safe errors. Real Ren'Py 7.8.7/8.5.3 graphical
tests perform an exact Store reveal alongside F8 and native save/load.

Dot notation is an object/module attribute; quoted brackets indicate
dictionary keys. E.g. `store.player.stats` differs from
`store.player["stats"]` if `player` is a dictionary. This is **not**
Python `eval`, nor an unbounded name/value search; missing, private and
inaccessible members remain inaccessible.

## PR #24: Bounded source-text search and literal references

Scripts adds a Source text mode with case-insensitive literal .rpy matching,
cursor-based Continue search, and file/line opening through the existing
bounded excerpt route. The selected variable's Find references in Scripts
action launches the same text search for its last public name/key. These
are textual mentions, including possible comments/strings, not a semantic
read/write graph. Non-.rpy, compiled-only and unscanned files are not inferred.

The new authenticated `GET /api/v1/source-search?q=&cursor=0:0&size=20`
endpoint executes on the game interaction thread, with an explicit 12-file,
256 KiB per-job and 128 KiB per-file scan cap, 120 candidate-file limit,
shallow directory bounds and a 20-match response cap. Large source files
are skipped with a partial-coverage marker instead of freezing gameplay;
a continuation cursor allows the UI to search more slices explicitly.

Python 2/3 tests check UTF-8, case-insensitive search, cursor boundaries,
oversized files and symlinks, input rejection, authentication and load
invalidation. Browser/bridge E2E checks both Scripts modes, source excerpts,
Find References and method/Origin protection; graphical Ren'Py 7.8.7 and
8.5.3 E2E checks a real .rpy text lookup.

## PR #25: Precision-aware Compare and filtered variable history

The Ren'Py interaction-thread snapshot and child/favourite reads can attach
an exact built-in scalar `compare_sample.text` of at most 256 characters.
No arbitrary Python `repr`/getters run. Each child/root page limits this
additional metadata to 16 KiB, and Python 2 invalid UTF-8 byte strings are
excluded rather than decoded with replacement.

The browser compares exact scalar text when both observations contain it,
detecting differences beyond a truncated 100-character preview. Before and
after values individually say exact or preview/status. No post-hoc full-value
fetch is used to invent prior values. Events remain bounded to 100 in one
browser tab; history resets on game-generation changes.

JavaScript tests cover equal-preview/different-text detection, mixed precision,
stale sample ordering and path/scope/type/pin filters. Browser-to-bridge E2E
uses a synthetic Store string with an identical preview but a changed suffix,
exercises a focused variable history, pin-only filtering and tree reveal.
Real Ren'Py SDK E2E asserts exact small primitive metadata from a running
Ren'Py 7.8.7 or 8.5.3 Store. Native F8, save/load, rollback and ZIP package
verification remain mandatory.

## PR #26: Bounded set and frozenset inspection

Set/frozenset nodes are expandable for safe built-in scalar members. The
typed path segment `["member", value]` identifies a member by its stable
value, not by a positional index. Copy Path writes
`store.flags{"open"}` / `store.flags{42}` / `store.flags{True}`;
the search popup parses the same notation, without evaluating expressions.
Unlike dictionary keys and list indices, member paths survive hash-table
iteration-order changes and can be pinned or revealed directly.

Python 2/3 tests check bounded built-in enumeration, Unicode/invalid-byte
rejection, omitted hostile objects (no object repr/getters), frozen
collections, missing-member recovery, safe favourite serialization, and
global search/reveal/full-value integration. Browser-to-bridge E2E expands
scalar members, reveals a frozenset value, pins a live set member through
removal/readdition, and verifies read-only HTTP rejection. Real graphical
Ren'Py 7.8.7/8.5.3 E2E inspects an actual Store set via the game-thread API.

Only built-in strings (at most 256 characters), safe integers, booleans and
None are exposed as set members. Python set iteration is always bounded;
unsupported objects are counted but not evaluated. Partial collections
display a coverage warning rather than an endless Next page cursor.
No gameplay writes, editing or extra polling were introduced.

## What the synthetic suite does *not* test

The **synthetic bridge suite alone** is not a real Ren'Py runtime E2E test. The synthetic fixture
emulates the Ren'Py interaction-thread timer and lifecycle generation change,
but does not start Ren'Py 7/8, inject F8, observe native overlays, execute
real save/load/rollback callbacks, interact with the Ren'Py renderer, or
measure gameplay FPS. Those still require the separate manual acceptance
matrix in [COMPATIBILITY.md](COMPATIBILITY.md) and
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

The separate graphical SDK suite above now exercises this workflow for
Ren'Py 7.8.7 and 8.5.3; browser-only synthetic coverage still has its own
distinct contract and does not substitute for native engine tests.


## Runtime and restoration evidence (PR #27, v0.7.9)

Python 2/3 tests exercise bounded deduplicated location samples, callback source
labels, malicious filename objects, and optional rollback indicator sampling.
The Chromium browser-to-real-bridge test changes a **synthetic** script line
through the fixture process's stdin and checks timeline display and filtering.
The real graphical Ren'Py 7.8.7/8.5.3 suite separately asserts that native
FileLoad produces an `after_load` signal and rollback invalidation produces
an `after_default` (or legacy fallback) signal. These are callback observations,
not exact rollback destinations or interaction counts. The bridge timeline
keeps at most 64 events in RAM and adds no HTTP endpoint or background scanner.


## Value rendering and source navigation (PR #28, v0.7.10)

Node tests cover lossless text tokenisation, strings containing #, escaped quotes,
triple strings, keyword highlighting, type descriptions, bounded excerpts, and
unsafe source-path rejection. Chromium exercises source context navigation
from variable details, Runtime and Compare via the real authenticated bridge,
including syntax token elements. Graphical Ren'Py 7.8.7/8.5.3 E2E also checks
that an actual game-owned .rpy excerpt renders highlighted source tokens.
Full primitive values are not treated as Python source, all fragments render
as React text nodes, and navigation is read-only.


## Opt-in primitive editing validation (PR #29, v0.7.11)

The Python 2/3 tests verify exact built-in primitive types, strict Unicode
handling, visible path resolution, safe plain container writes, bounded numeric
conversion, compare-and-swap conflict handling, authentication and origin
rejection, disabled-by-default operation, interaction-thread ownership, and
queued-write cancellation on game generation changes. The Playwright fixture
starts **disabled unless the test process passes an explicit test-only opt-in**
flag. Tests cover no edit UI/no HTTP mutation by default, then separately
enable editing and exercise the full confirmation flow, same-generation
fingerprint conflicts, stale-generation rejection and snapshot refresh.
No game-owned Python code executes on HTTP worker threads.


## Undo/Redo and bounded edit history validation (PR #30, v0.7.12)

Python 2/3 tests verify bounded UTF-8 accounting, the 50-record retention
limit, exact same-type compare-and-swap reversals, conflicting game-side writes,
redo-branch invalidation after a new edit, stale-generation rejection and
history reset on load/rollback. HTTP tests prove authenticated requests only
queue primitive arguments and all target reads/writes execute on the game
interaction thread. Browser E2E covers the separate Edits tab, per-operation
confirmation, Undo/Redo round trips and redo-branch discard. Runtime history
labels explicit edit/undo/redo invalidations without calling them Ren'Py
rollback events or reconstructed turns.


## Variable lock validation (PR #31, v0.7.13)

Python 2/3 tests cover strict typed-path payload validation, Unicode paths,
idempotent lock/unlock, the 128-path / 32 KiB retention budget and lifecycle
resets. HTTP tests verify pairing-token and Origin/Host enforcement, game-thread
queue ownership, lock rejection for inspector edits and Undo/Redo (HTTP 423),
and that normal game-script assignments remain unaffected. Browser E2E covers
the contextual lock/unlock controls, tree padlock state and unchanged game
generation. Real Ren'Py 7/8 E2E confirms default-deny behavior and packaging
includes the lock manager in both closed-manifest engine installers.


## Edit safety and shared-session consistency (PR #32, v0.7.14)

Python 2/3 tests cover fingerprint/type baselines, sticky stale status, explicit
refresh/unlock, unsupported or missing targets, bounded rotating monitoring
(8 of at most 128 locks per snapshot publish), and accurate memory accounting.
HTTP tests verify fresh current-target conflict payloads, stable conflict codes,
stale-lock Edit/Undo rejection, history preservation until an actual value
conflict, and refresh without advancing gameplay generation. Concurrency tests
queue independent same-generation writes and lock/edit races on the same game
thread, proving that at most one conflicting operation applies. Repeated
load/rollback invalidations clear both locks and edit history.

Playwright starts two independent browser contexts against one synthetic bridge,
races edits from the same captured generation, and verifies one write plus one
409 conflict, one history record, and convergence of both clients. Browser E2E
also changes a locked value through the fixture, waits for bounded background
detection, refreshes the lock, and verifies the editor receives the current
primitive. Real Ren'Py 7/8 graphical suites continue to validate default-deny
editing and release packaging.
