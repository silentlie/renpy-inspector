# Ren'Py Inspector

**Experimental external inspector for Ren'Py 7 and 8 desktop games. Read-only by default; optional, game-author-enabled Store primitive editing.**

The inspector uses a separate browser workspace built with **React + Ant Design**.
There is **no in-game inspector drawer, Inspect tab, or settings UI**.
The only in-game integration is an invisible **F8** hotkey plus a snapshot timer.

## Install

1. Back up the game's `game/` directory and existing save files.
2. Download the matching engine package (Ren'Py 7 or Ren'Py 8) from GitHub Releases or the PR preview.
3. Extract the **engine-specific ZIP** into the game installation root (the folder already containing `game/`), not into `game/` itself.
4. Check that `game/renpy_inspector_web/index.html` and `game/renpy_inspector_web/assets/` exist.
5. Start the game, then **press F8**.

On the first F8 press, the inspector starts its authenticated **127.0.0.1** server and opens the browser. Subsequent presses open the **same local session** in the browser without restarting the server or changing the token. You do not need Node.js on the game machine.

**Upgrading:** The new ZIP overwrites `renpy_inspector_screens.rpy` with a hotkey-only screen and overwrites `renpy_inspector_styles.rpy` with an empty compatibility stub. Any manually installed third-party or experimental `renpy_inspector_tree.rpy` file from older tests should be removed separately. Do not delete unrelated game files.

## What the browser provides

- Top-level **Overview / Variables / Scripts / Runtime** tabs and **Store / Persistent / Favourites / Pin history / Compare** scopes, plus game-author-opt-in **Locked** and **Edits** scopes.
- Full-width virtualised tree with **automatic paged loading** on expansion and near the end of scrolled branches. No routine "Load more" click.
- **PR #13: bounded global search and reveal.** Press `/` or the magnifying-glass icon to search Store and Persistent names/paths beyond the loaded tree. Click a hit to reveal its typed ancestor path and scroll directly to the result. Search results explicitly warn when the traversal budget is exhausted.
- Automatic snapshot updates while the game is running. No refresh button or browser footer.
- **Live watches:** one shared scheduler refreshes expanded branches and favourites without creating a timer per row.
- **Independent favourites:** pinned typed paths resolve without expanding ancestors, and favourites persist per game across localhost port changes.
- **PR #35 Favourites Management & Sync:** A confirmed **Clear all** control in the Favourites workspace removes the pins visible at confirmation, preserving pins concurrently added in another tab. Browser tabs reconcile per-game favourites through a lightweight authenticated preference GET (every 2.5 seconds, with same-origin local-storage notifications for faster updates). Explicit pin/unpin/clear actions use revision-checked, atomic file writes and bounded conflict retries so stale clients cannot overwrite unrelated changes. The revision is saved beside favourites in the existing inspector-owned file; old v1 files start at revision 0. If the save directory is unavailable, browser-local favourites remain usable but cross-origin synchronisation is not guaranteed. No extra Ren'Py game-thread work, gameplay writes or new persistent browser chrome.
- **PR #28 Better Value Rendering:** Syntax-coloured .rpy source excerpts use a bounded, browser-only lexer that escapes all game text; full primitive strings remain literal. The variable details drawer explains known types and gives semantic colours to raw previews, captured exact values and Compare samples without executing game-defined code. Runtime observations, sampled Compare locations and current script context can open the existing read-only Scripts excerpt. These observed locations **do not prove mutation causation**. No new API or polling.
- **PR #27 Runtime & Rollback History:** A compact **Runtime** tab shows the latest sampled script location, best-effort return-stack depth, optional sampled `renpy.in_rollback()` indicator, and up to **64 session-only runtime observations**. Location samples are deduplicated and lifecycle callbacks retain their source (`after_load`, `after_default`, or legacy rollback probe). A default-state callback can follow **rollback, startup, or load**, so the timeline never claims an exact rollback cause, number of interactions, SugarCube turns, or historical variable values. These signals survive browser generation resets in the bridge session, while variable Compare history still resets. No extra HTTP endpoint, polling loop, game mutation or persistent log.
- **PR #26 Structured Set Inspection:** Expand Python `set` and `frozenset` values to inspect **safe scalar members** (string, integer, boolean and None). Member paths are value-identified, e.g. `store.flags{"open"}` or `store.flags{42}`, not unstable iteration indexes. Use the existing search popup to reveal a member directly, pin it as a favourite, or read its full scalar value. Unsupported objects, huge member strings and large integers are excluded; partial branches are explicitly marked and do not trigger endless pagination. This remains read-only with bounded enumeration.
- **PR #25 Enhanced Compare & History:** up to 100 browser-session-only sampled changes with **before/after exact text for small built-in primitives** (up to 256 characters and 16 KiB across a fetched page), explicitly marked preview-only values otherwise. Filter by path, Store/Persistent, event kind or currently pinned variables; reveal an observed variable in the tree or open its details. A variable details drawer can jump to its focused Compare history. Sampling is not an exhaustive mutation log, and game load/rollback generation changes reset history.
- **PR #14 Scripts:** search a bounded list of Ren'Py labels and filenames, inspect the current file/line and return-stack summary, and navigate to a small source excerpt when a game-owned `.rpy` exists. No in-game jump or warp.
- **PR #15 Lifecycle:** cache-only invalidation uses Ren'Py's after-load and after-default callbacks where supported, plus a conservative interaction-time rollback probe on older engines. Queued old-generation reads receive 409; the next interaction tick refreshes state. The browser rejects stale epochs, clears cached tree/history/selection and re-resolves persisted favourite paths.
- **PR #16 Performance:** one shared, fair background watch scheduler now caps in-flight polling at two requests, skipping already-busy watches rather than building a backlog. Overview reports sampled game-thread root-scan and queue diagnostics; CI records synthetic bridge microbenchmarks (not game FPS).
- **PR #17 Release hardening:** installer builds refuse undocumented inspector code or missing compiled JS/CSS, verify SHA256 and both ZIP payloads before publishing, and provide a read-only local install checker for wrong nesting or leftover legacy screens.
- **PR #18 Tree freshness:** browser tree pages and favourite watches reject older game-thread samples even within the same load generation. Fully enumerated roots drop obsolete paginated tails after collections shrink; newer child-page results survive older root polls.
- **PR #19 Browser/bridge E2E:** headless Chromium exercises the production browser against the actual authenticated Python HTTP bridge and a synthetic game-thread fixture. CI verifies session authentication, navigation, favourites, changes, global search/reveal, Scripts and paged tree loading.
- **PR #20 Real-engine E2E:** CI launches disposable Ren'Py 7.8.7 and 8.5.3 games under Xvfb and uses native keyboard input to test F8, the real browser session, dialogue-driven Store updates, save/load and rollback lifecycle. Other SDK versions retain lint-only validation.
- **PR #24 Source Text Search:** Scripts has **Labels / Source text** modes. Search literal, case-insensitive text across game-owned `.rpy` files, open an exact source line and its nearby context, and continue a bounded search from its cursor. **Find references in Scripts** in variable details searches for a selected variable's literal name/key. Results are textual occurrences, **not** semantic read/write references; comments and strings can match. Files are restricted to the game source directory; no arbitrary filesystem reads, Python evaluation or game writes. Large files, compiled-only games and files outside the scan limits are labelled as partial or unavailable.
- **PR #23 Direct Path Navigation:** Open the search popup (`/` or magnifier) and enter an **exact typed path** such as `store.player["stats"][0]`, `persistent.flags["seen"]` or `persistent["flag"]`. Press Enter to fetch only the verified ancestor chain, expand the necessary nodes and scroll to the variable even if it was not previously loaded or is outside the bounded global search budget. Dot notation means a module/object attribute, quoted brackets mean a dictionary key, `[0]` means a list index, and `[key:42]` means an integer dictionary key. No Python evaluation or gameplay writes. Invalid and missing paths show errors in the popup. **Copy Path** from the details drawer is directly pasteable here.
- **PR #22 Full Value Inspector:** Select a variable, open its details and choose **Show full value** to read exact built-in string/number/boolean/None contents with a multiline viewer, **Copy Value**, and **Copy Path**. Text is capped at 16,384 characters (or source bytes on Python 2 byte strings), clearly marked when truncated; copying incomplete values is disabled. Unsupported game objects are not stringified. Requests use the authenticated read-only game-thread queue; this does not change automatic preview polling or Compare.
- **PR #29 Variable Editing MVP:** Safe primitive Store writes are **disabled by default**. A trusted game author must explicitly enable the capability in an `init python` block. Eligible *existing* Store variables (and values inside plain dictionaries/lists) can be edited from the details drawer after an exact-value read and affirmative per-edit confirmation. Types cannot change. Persistent values, tuple/set membership, custom objects, new/deleted keys and arbitrary Python expressions are excluded. Successful writes advance state generation and invalidate stale reads; this is **not** a game rollback or a complete mutation log.
- **PR #30 Undo/Redo & Edit History:** A separate **Edits** tab keeps up to 50 explicit inspector writes (64 KiB total) in bridge-session memory. Undo/Redo are individually confirmed and reapply only when the current Store primitive still matches the exact recorded value and type. A new edit discards the redo branch; conflicting entries are retired without overwriting game changes. Save/load, rollback and other state-generation resets clear reversal history. These records are not Ren’Py rollback steps, are never written to saves, and do not include mutations made by game scripts.
- **PR #31 Variable Locks:** The optional **Lock variable** control protects an exact existing Store primitive path from this inspector's explicit Edit, Undo and Redo actions. A lock is session-only (maximum 128 paths / 32 KiB), appears as a padlock in the tree, and clears on game load, rollback, other state resets, bridge restart or editing disablement. It does **not** prevent game scripts or Ren'Py from changing the variable during normal gameplay. Locks are available only when primitive editing is explicitly enabled by trusted game init.
- **PR #32 Edit Safety & State Consistency:** Locks capture the exact primitive fingerprint/type and are checked in rotating batches of at most eight paths per game-thread snapshot. External game-side changes mark a lock stale but do not release it; use **Refresh lock** to accept the current value as the new baseline, or unlock it. Stale edit conflicts return the current value and a reason while preserving the user's draft and requiring fresh confirmation. Multiple browser tabs share one serialized generation, so concurrent writes cannot both apply from the same stale generation. Sampling may miss a value that changes and reverts between checks.
- **PR #33 Locked Variables workspace:** When trusted game init enables primitive editing, a dedicated **Locked** scope lists every session lock with its typed path, baseline type, creation time and stale reason. Inspect, refresh stale locks, unlock individual paths or unlock all through sequential generation-checked game-thread requests. The workspace never stores or displays the raw baseline value; locks continue to protect Inspector Edit/Undo/Redo only, not gameplay assignments.
- **PR #34 Favourite History:** The **Pin history** scope keeps a separate bounded timeline of observed changes to currently pinned Store/Persistent paths. Monitoring begins with the first sample **after** pinning, so earlier Compare events are never presented as pinned observations. Retain up to 200 events total / 30 per pinned path, including exact small primitive samples and missing/recovery events where supported. Filter by path, event kind or individual pin; inspect/reveal captured paths, navigate to the observed source location, or clear pinned history without clearing Compare. Unpinning erases that path's history; save/load/rollback clears the entire timeline but leaves saved favourite paths intact. No new polling or gameplay writes.

The first snapshot contains only shallow root pages. Expanding a branch fetches up to **80 child nodes per request**; as the virtual tree scrolls close to a page boundary, it requests another page automatically. While a scope is active, the shared watcher polls already-loaded expanded pages and reconciles changed previews; favourites receive independent polling even if the scope is hidden. Structural changes reset affected pagination tails to avoid keeping stale positional cursors. Bounds remain: **1,000 nodes per branch, eight path levels, 6,000 browser-loaded nodes, eight queued requests and 256 KiB per HTTP response**. This is still not an unrestricted dump of all game state. Tree filtering applies to already loaded nodes, but the popup also performs a **separate bounded, read-only game-thread search** of unloaded names and formatted paths. Each query examines up to 1,400 visible entries, returns up to 30 results, descends at most five levels, and limits non-root branches to 100 children. Partial results are labelled. Search never evaluates user Python expressions, enumerates private members or searches full object values. Compare records bounded exact built-in scalar samples where available (maximum 256 characters and 16 KiB per page); older bridges, oversized strings, unsupported objects and exhausted sample budgets remain clearly preview-only or unavailable. It is not a full game-state mutation log and never reconstructs earlier values by re-reading the current state. It does not claim exact script/turn causality and resets on the bridge's save/load generation change. Documented after-default callbacks cover rollback in supported Ren'Py versions; heavily customised games that suppress these callbacks may still show misleading sampled changes. Favourites are stored in a separate inspector-owned `renpy-inspector-browser-favourites.json` file under the game's save directory. The browser imports old origin-local pins only when that file does not yet exist. Saved paths are independently sampled on the game interaction thread, even when their branches have never been opened. If the game has no writable save directory, favourites fall back to browser-local storage and Overview reports the limitation.

## Optional Store primitive editing (PR #29)

**Default: disabled.** Only the game author or someone authorised to modify its source should add this to a separate `.rpy` file, after the inspector's `init -100 python` block:

```renpy
init 1 python:
    import renpy_inspector
    renpy_inspector.bridge.configure_variable_editing(True)
```

Restart the game and press **F8**. The details drawer offers **Edit primitive**
only while the server advertises the game-configured capability. Open it to
capture the *current* exact value/type, enter the replacement literally, check
the explicit confirmation box, and click **Apply edit**. After a successful write, the **Edits** tab shows
its exact before/after record. Undo and Redo each require a separate explicit
confirmation and succeed only while the recorded current value still matches.
The details drawer also offers **Lock variable / Unlock variable** after a supported
primitive is inspected. A lock prevents this inspector's explicit writes and
Undo/Redo for that exact path; it does not freeze gameplay or intercept script
assignments. Game-side value/type/path changes mark the lock stale without
releasing it. **Refresh lock** rebases the fingerprint to the current primitive;
**Unlock variable** releases it. At most eight of up to 128 locks are checked per
snapshot publish, so detection is sampled rather than instantaneous. Locks are
session-only and clear on load/rollback or bridge reset.
There is no browser setting or HTTP request to enable editing, no automatic
writes and no edit button for Persistent values.

The server validates the pairing token, loopback Host/Origin, JSON size,
visible typed path, exact primitive type, value length, expected generation
and SHA256 fingerprint of the previously captured value. All reads/writes
execute exclusively on Ren'Py's interaction thread. Only existing Store
module fields and existing entries of plain built-in dictionaries/lists may
be replaced with the **same** built-in primitive type: Unicode text up to
1,024 characters / 4 KiB UTF-8, booleans, bounded integers or finite floats.
Python 2 byte strings, None values, custom objects, immutable containers,
computed attributes and Persistent changes are not writable. A successful
edit invalidates stale inspector requests and increments its generation.

**Caution:** Editing game variables can change gameplay logic, saves and
rollback behaviour. The Edits tab offers bounded, session-only Undo/Redo for
explicit inspector writes, but it is not a substitute for a save backup and
cannot reverse arbitrary game-script mutations. Undo/Redo require the exact
recorded current value; conflicting records are retired rather than forcing a
write. Game load, rollback or other state-generation resets clear the reversal
history. Locks protect only inspector-originated writes, not assignments made by
game scripts. No durable edit log exists. A timed-out request could have
completed on the game thread; inspect the fresh value before retrying.
The inspector does not assert Ren'Py's rollback system will reverse these
external edits.

## How it works

F8 calls an opt-in bridge launcher on Ren'Py's interaction thread. The server binds to `127.0.0.1` on an ephemeral port and generates a new pairing token when it starts. The token is passed in the local browser URL fragment and is required in an API header. The HTTP server only serves already serialised, bounded JSON and static Ant Design assets. Child-page HTTP requests queue validated typed paths; they never inspect game objects on HTTP threads. A 250ms Ren'Py interaction-thread timer services at most two queued requests per tick and publishes a shallow root refresh around every 1.5 seconds.

The authenticated `GET /api/v1/value` endpoint queues a single typed path for safe game-thread inspection. The separate `GET /api/v1/full-value` endpoint returns bounded primitive text only on explicit request, with generation/capture metadata; it cannot evaluate arbitrary Python or modify gameplay. `GET /api/v1/scripts` and `GET /api/v1/source` queue bounded read-only script requests. Label names and line numbers come from Ren'Py's runtime; source windows are read only from `.rpy` files resolving within `config.gamedir`, with symlink/traversal checks and size limits. Games distributing only `.rpyc` retain label metadata but cannot display source text. `PUT /api/v1/favourites` writes only inspector-owned preference metadata. **Only after trusted game init opt-in**, `GET /api/v1/edit-target` inspects eligible Store primitives and `PUT /api/v1/edit` queues a bounded, confirmed primitive mutation for the Ren'Py interaction thread. `PUT /api/v1/edit-history` queues a separately confirmed undo/redo operation using the same exact-value/type and generation checks. `PUT /api/v1/locks` queues exact-path lock/unlock/refresh metadata changes on the game thread; locks block inspector edits and reversals but never intercept game-script assignments. Concurrent browser clients share the same game generation and edit-history revision; only the first write from a generation can apply. The bridge retains at most 50 records / 64 KiB in memory; history resets on load/rollback and is never persisted. No endpoint enables edits; they are disabled by default. The game may subsequently save modified Store state through its normal mechanisms. PR #12 stamps each child and favourite sample with its Ren'Py game-thread capture time so delayed HTTP responses cannot produce misleading before/after events.

The server stays available until the game exits. Closing a browser tab does **not** stop the game or its server. The F8 handler displays a brief Ren'Py notification only if the local server or browser cannot be opened. Some games suppress Ren'Py overlay screens; F8 and refreshes may be unavailable during those moments.

## Development and validation

```sh
python -m unittest discover -s tests -v
cd web
npm install --no-audit --no-fund
npm test
npm run build
```

The CI matrix covers Python 2.7 and 3 plus lint on Ren'Py 7.4.11, 7.8.7, 8.4.1 and 8.5.3. That does **not** replace real-game checks for F8 interception, browser launch, connection security, ongoing snapshots, save/load/rollback, and frame rate. Use only games you are authorised to modify or inspect.

See [external inspector details](docs/EXTERNAL_GUI.md), [browser-to-bridge E2E testing](docs/E2E_TESTING.md), [tree freshness details](docs/TREE_FRESHNESS.md), [release and upgrade checklist](docs/RELEASE_CHECKLIST.md), [performance measurements and limits](docs/PERFORMANCE.md), [compatibility checklist](docs/COMPATIBILITY.md) and [development plan](PLAN.md).

## Uninstall

Remove the files installed by the inspector from `game/` (including the `renpy_inspector/` Python package and `renpy_inspector_web/` assets). Preserve all unrelated game files and saved games. The inspector's own preferences file, if present in the game's save directory, is separate from gameplay saves.
