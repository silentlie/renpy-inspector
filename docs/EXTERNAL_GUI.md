# External Ant Design workspace

**PR #32 Edit Safety & State Consistency (v0.7.14).** Each lock stores the exact primitive fingerprint/type from creation. The bridge checks at most eight rotating locked paths per snapshot publish on the Ren'Py interaction thread; a detected game-side value/type/path change marks the lock stale but keeps it active. **Refresh lock** explicitly rebases the baseline to the current eligible primitive; **Unlock variable** releases it. Detection is sampled and can miss a value that changes and reverts between checks. Conflicts return stable reason codes and the fresh current target; a browser draft is preserved but must be confirmed again. All browser tabs share one serialized generation and history, so same-generation concurrent writes cannot both apply.

**PR #31 Variable Locks (v0.7.13).** Locks are exact-path, session-only protections for the inspector's own Store primitive edit and Undo/Redo endpoints. They do not intercept game-script writes or freeze Ren'Py state. At most 128 paths / 32 KiB are retained, and locks clear on load, rollback, other generation resets, bridge restart or editing disablement. They require the existing trusted game-init edit opt-in.

**PR #30 Undo/Redo & Edit History (v0.7.12).** Read-only by default. A trusted game
init script can call `renpy_inspector.bridge.configure_variable_editing(True)`.
The browser then exposes a contextual, confirmation-gated primitive editor for
existing Store fields and plain dict/list entries only. Each write validates
generation, exact previous-value fingerprint and unchanged built-in type before
the interaction-thread mutation. Persistent/custom/immutable targets and all
Python evaluation remain forbidden. The Edits tab retains at most 50 explicit
writes / 64 KiB in bridge-session memory. Confirmed Undo/Redo use exact-value
compare-and-swap and retire conflicting entries; new edits discard the redo
branch. Load/rollback clears reversal history. Variable locks are now available as
an inspector-only guard; they do not prevent game scripts from assigning values.
Durable edit logs remain out of scope.
See [README opt-in instructions](../README.md#optional-store-primitive-editing-pr-29).

**PR #28 Better Value Rendering (v0.7.10).** Source excerpts in Scripts have escaped, browser-only Python/Ren'Py token colours; variable previews and on-demand values show explanatory type categories without interpreting game text as code. Runtime/Compare/detail source links are based on verified game-relative .rpy locations and never jump game execution. A sampled file:line is observation, not proven variable mutation causation.

**PR #27 Runtime & Rollback History (v0.7.9).** The dedicated Runtime tab displays bounded, in-memory script-location observations, after-load/default callback signals, and the optional sampled rollback indicator. A default callback alone does not prove a rollback, and no SugarCube turns or exact dialogue interaction history are invented. This uses the existing authenticated snapshots, with no new game-state writes or polling.

**PR #26 Structured Set Inspection (v0.7.8).** Safe scalar members of Python sets/frozensets can now expand, reveal and pin by typed value. **PR #25 Enhanced Compare & History (v0.7.7)** remains available. Small exact scalar captures and filtered, precision-labelled Compare histories now work in the existing read-only browser. **PR #24 Source Text Search (v0.7.6)** remains available. Scripts now supports bounded literal .rpy text lookup and Find References from variables. **PR #23 Direct Path Navigation (v0.7.5)** remains available. Exact store/persistent typed paths now navigate within the existing search popup, without evaluating Python. **PR #22 Full Value Inspector (v0.7.4)** also remains supported. The details drawer now provides bounded, on-demand primitive value inspection, including multiline text and explicit copy actions. **PR #20 graphical engine E2E (v0.7.3)** also remains supported. Native Ren'Py 7.8.7 and 8.5.3 SDK test games now exercise F8, browser startup, save/load, rollback and live Store values under Xvfb. Other versions and customised game overlays remain unverified automatically. See [E2E testing](E2E_TESTING.md).

## Install and launch

1. Back up the game directory and saves.
2. For the experimental graphical engine E2E build, get the engine-specific preview ZIP from [PR #32](https://github.com/silentlie/renpy-inspector/pull/32) after CI publishes it. Otherwise use the latest published GitHub release.
3. If downloading a CI artifact, extract the **outer artifact ZIP** first, then extract exactly one of the contained `-renpy7.zip` / `-renpy8.zip` installers into the game installation root.
4. Verify the actual installed paths:

   ```text
   <game root>/game/renpy_inspector.rpy
   <game root>/game/renpy_inspector_screens.rpy
   <game root>/game/renpy_inspector/bridge.py
   <game root>/game/renpy_inspector_web/index.html
   <game root>/game/renpy_inspector_web/assets/index-*.js
   <game root>/game/renpy_inspector_web/assets/index-*.css
   ```

5. Optionally run `python scripts/check_install.py "/path/to/game root"` from a source checkout to detect nested extraction, missing bundles and orphan legacy inspector files (read-only). Launch the game. Press **F8** to start the loopback service and open the Ant Design UI in the default browser.
6. Press **F8** again to reopen the existing session. No native drawer, Settings screen or Inspector tab is shown.
7. To stop the local server, exit the game. Closing the browser does not stop the service.

A short in-game error notification may appear if static assets are missing or the system cannot open a browser. The default read-only local service never starts automatically at game init.

## Browser interaction

The browser has top-level **Overview / Variables / Scripts / Runtime** tabs, nested **Store / Persistent / Favourites** scopes, a virtual tree, a popover search, details drawers and browser-local favourites. The tree occupies the available viewport, without permanent header or footer. Search via the icon or `/`; type at least two characters. Global name/path results are shown only in the popup and include bounded previews. Enter reveals the first result, or click a hit to materialise its verified ancestor chain, expand the path and scroll to it in the virtualised Store/Persistent tree. Escape closes search. No permanent search bar is added.

On branch expansion, the browser requests its first **80** children over the authenticated GET-only API. As the virtualised list scrolls and its pagination sentinel enters the viewport, it requests the next 80 automatically. The tree renders only visible rows, even if hundreds of nodes have been loaded. A retry control appears only after a failed page request. The connection state, capture timestamp, coverage warning, and write capability status live in **Overview**; the **Edits** scope and contextual lock controls appear only when the game author enabled primitive writes. There is no manual refresh button.

## Security and resource limits

- The server binds only to `127.0.0.1` on an OS-selected port, uses a **new 256-bit token when first started**, and validates Host/Origin headers. Do not share pairing URLs.
- The browser authenticates `GET /api/v1/snapshot`, `GET /api/v1/children`, `GET /api/v1/search` and `GET /api/v1/reveal` using the token header. The paging request sends typed JSON path segments, scope, offset and size as URL-encoded query fields. POST and unknown routes are rejected. The token lives in a URL fragment, not an HTTP path.
- Game values are inspected **only on the Ren'Py interaction thread**. HTTP workers validate and queue primitive requests; the game timer resolves at most two per 250ms tick and serialises responses before the HTTP worker returns them. Without trusted game init opt-in, nothing writes game state; even with it, only confirmed, same-type Store primitives can change through the interaction-thread queue. No user-supplied Python expression is evaluated. Locks are metadata for the inspector endpoints only; they do not monkey-patch Store fields, acquire Python object locks, or stop game code from changing values.
- Initial captures include shallow root pages only. Children are fetched on demand, **80 per request**, capped at **1,000 entries per branch**, **eight path levels** and **6,000 browser-loaded nodes**. HTTP response size is capped at **256 KiB** and the page-request queue holds at most eight jobs. The timer refreshes shallow roots about every 1.5 seconds. Overlay suppression may pause all requests.
- Browser-local favourites are separate from native legacy favourites, can expire with a local-origin port change, and are not gameplay saves.
- No telemetry or remote network server. The HTML/JS/CSS assets load from the localhost service.

## Development

Node.js is required only to build the frontend:

```sh
cd web
npm install --no-audit --no-fund
npm test
npm run build
```

Vite runs on `http://127.0.0.1:5173` during development. Start the game server with F8 first; to use Vite, enter a URL of the form:

```text
http://127.0.0.1:5173/#token=<session-token>&bridge=http%3A%2F%2F127.0.0.1%3A<port>
```

Alternatively, copy the `web/dist/` contents into `game/renpy_inspector_web/`. CI automates this for preview/release ZIPs.

## Manual smoke checklist

- Install the Ren'Py 7 package in a real game. Press F8 once: local server launches, browser opens, snapshot appears and **no native inspector GUI** appears.
- Press F8 a second time: browser opens the same URL, token and port. No second local server.
- Change a variable in-game, then verify the browser updates automatically.
- Search a name from the 100th root entry and a nested variable absent from the initial snapshot; click a hit and confirm its ancestors open, the result is highlighted and the virtual tree scrolls to it. Confirm partial-search warnings, stale-result handling, Escape, Enter, and unauthorised or malformed query rejection.
- Expand deep tree branches and verify that the initial page arrives. Scroll toward the end and confirm additional pages load automatically without a "Load More" click; verify Ant Design only renders visible rows. Search, pin/unpin, open details and navigate Overview/Scripts.
- Close and reopen the browser; gameplay and server should continue.
- Try running with web files missing: transient diagnostic, no game crash.
- Test save/load and rollback while connected. Confirm no stale snapshot persists after game load.
- Confirm unauthenticated requests return 401 and foreign Host/Origin requests return 403. Verify no external network socket is opened.
- Repeat on Ren'Py 8, at different resolutions and window sizes, and measure FPS.
- Exit the game and confirm the local server stops.

**Not yet confirmed:** Some heavily customised games may intercept F8 or suppress overlay screens. SDK lint does not prove in-game key capture or browser launch.

**Additional PR #9 caveat:** Loaded child-page previews are cached in the browser; a parent changing in-game may require collapsing/reloading or a new session before all previously fetched descendant values reflect replacement objects. Direct save/load invalidates the game generation and discards cached pages. Automatic server-side change subscriptions and Compare are separate future work.


## PR #13: bounded global search and reveal

The popup searches across Store and Persistent using the read-only,
authenticated `/api/v1/search` route. It is not a full index of Python
objects: each request is processed by Ren'Py's interaction thread and
bounded to 1,400 visited nodes, 30 results, five levels, at most 100
children per non-root branch and 160 queued branch candidates. The
initial Store/Persistent roots can inspect up to 1,000 visible names per
root, even if the browser currently displays only 80. Search examines
names/formatted paths rather than raw variable values. Private members
and unsafe getters remain inaccessible.

The optional `/api/v1/reveal` endpoint accepts **only typed paths**
and re-validates the visible child descriptor at each step. The
browser inserts the returned ancestor metadata into its tree and calls
Ant Design's virtual `scrollTo` to show the match. Off-page matches
do not force downloads of hundreds of preceding siblings. The normal
pagination cursor and read-only snapshot continue unchanged.

Browser search requests are debounced by 350ms and cancelled when the
popup closes or the query changes; the server's bounded HTTP request
queue and Ren'Py interaction-thread ownership remain unchanged.
Search results are approximate and may be partial; no guarantee that
all game objects or all possible nested properties are discoverable.


## PR #14: Scripts workspace

The Scripts tab exposes a bounded index of game labels and their compiled
runtime metadata using Ren'Py's get_all_labels() and script.lookup(). Search
matches label names and game-relative .rpy filenames, with 40 results per
page and a maximum of 4,000 eligible label names inspected. Engine/internal
labels, absolute source paths outside the game, and unsafe file types
are not exposed. A partial-index notice appears when the scan is capped.

Selecting a label shows its file and line, then requests a read-only window
of 10 source lines on either side (up to 21 lines and 240 characters each).
This optional excerpt is available only if a source .rpy exists within
config.gamedir and is no larger than 1 MiB. Paths are canonicalised before
opening; traversal, symlinks leaving game/, non-.rpy files, and malformed
line numbers are rejected. In compiled-only games, label metadata remains
available but the source viewer reports that the file was not installed.

The current statement's filename and line are surfaced from
renpy.get_filename_line() when available. Return-stack information is a
summary of return destinations, not a Python call stack or an exact current
label. Clicking View current navigates within the browser only. Copy
location copies file:line for an external editor. **There is no gameplay
jump, warp, save mutation, arbitrary file browser, or script execution.**

The HTTP server queues label/source requests just like child-page requests,
and only the Ren'Py interaction thread reads engine metadata or source files.
All requests require the existing loopback Host/Origin and session token
checks. Up to two queued requests are serviced per 250ms tick.

Manual smoke: inspect a normal label, a local label, and a game containing
only .rpyc files. Search across multiple .rpy files; click View current,
copy a source location, and verify gameplay remains in the same statement.
Verify that source is unavailable for protected files outside the game,
and that search remains responsive under a large label set.
