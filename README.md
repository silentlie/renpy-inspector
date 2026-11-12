# Ren'Py Inspector

**Experimental, read-only external inspector for Ren'Py 7 and 8 desktop games.**

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

- Top-level **Overview / Variables / Scripts** tabs and **Store / Persistent / Favourites / Compare** scopes.
- Full-width virtualised tree with **automatic paged loading** on expansion and near the end of scrolled branches. No routine "Load more" click.
- **PR #13: bounded global search and reveal.** Press `/` or the magnifying-glass icon to search Store and Persistent names/paths beyond the loaded tree. Click a hit to reveal its typed ancestor path and scroll directly to the result. Search results explicitly warn when the traversal budget is exhausted.
- Automatic snapshot updates while the game is running. No refresh button or browser footer.
- **Live watches:** one shared scheduler refreshes expanded branches and favourites without creating a timer per row.
- **Independent favourites:** pinned typed paths resolve without expanding ancestors, and favourites persist per game across localhost port changes.
- **PR #12 Compare:** bounded, read-only before/after **primitive previews** observed during root refreshes, expanded-branch watches and favourite sampling. Shows the last 100 changes in this browser session, with script file/line context when available.
- **PR #14 Scripts:** search a bounded list of Ren'Py labels and filenames, inspect the current file/line and return-stack summary, and navigate to a small source excerpt when a game-owned `.rpy` exists. No in-game jump or warp.
- **PR #15 Lifecycle:** cache-only invalidation uses Ren'Py's after-load and after-default callbacks where supported, plus a conservative interaction-time rollback probe on older engines. Queued old-generation reads receive 409; the next interaction tick refreshes state. The browser rejects stale epochs, clears cached tree/history/selection and re-resolves persisted favourite paths.
- **PR #16 Performance:** one shared, fair background watch scheduler now caps in-flight polling at two requests, skipping already-busy watches rather than building a backlog. Overview reports sampled game-thread root-scan and queue diagnostics; CI records synthetic bridge microbenchmarks (not game FPS).
- **PR #17 Release hardening:** installer builds refuse undocumented inspector code or missing compiled JS/CSS, verify SHA256 and both ZIP payloads before publishing, and provide a read-only local install checker for wrong nesting or leftover legacy screens.
- **PR #18 Tree freshness:** browser tree pages and favourite watches reject older game-thread samples even within the same load generation. Fully enumerated roots drop obsolete paginated tails after collections shrink; newer child-page results survive older root polls.
- **PR #19 Browser/bridge E2E:** headless Chromium exercises the production browser against the actual authenticated Python HTTP bridge and a synthetic game-thread fixture. CI verifies session authentication, navigation, favourites, changes, global search/reveal, Scripts and paged tree loading.
- **PR #20 Real-engine E2E:** CI launches disposable Ren'Py 7.8.7 and 8.5.3 games under Xvfb and uses native keyboard input to test F8, the real browser session, dialogue-driven Store updates, save/load and rollback lifecycle. Other SDK versions retain lint-only validation.
- Read-only access: no variable editing, code evaluation, or writes to gameplay saves.

The first snapshot contains only shallow root pages. Expanding a branch fetches up to **80 child nodes per request**; as the virtual tree scrolls close to a page boundary, it requests another page automatically. While a scope is active, the shared watcher polls already-loaded expanded pages and reconciles changed previews; favourites receive independent polling even if the scope is hidden. Structural changes reset affected pagination tails to avoid keeping stale positional cursors. Bounds remain: **1,000 nodes per branch, eight path levels, 6,000 browser-loaded nodes, eight queued requests and 256 KiB per HTTP response**. This is still not an unrestricted dump of all game state. Tree filtering applies to already loaded nodes, but the popup also performs a **separate bounded, read-only game-thread search** of unloaded names and formatted paths. Each query examines up to 1,400 visible entries, returns up to 30 results, descends at most five levels, and limits non-root branches to 100 children. Partial results are labelled. Search never evaluates user Python expressions, enumerates private members or searches full object values. Compare is deliberately based on **sampled, bounded previews** rather than full values or every game-state mutation. It ignores unsupported objects and incomplete strings, does not claim exact passage/turn causality, and resets on the bridge's save/load generation change. Documented after-default callbacks cover rollback in supported Ren'Py versions; heavily customised games that suppress these callbacks may still show misleading sampled changes. Favourites are stored in a separate inspector-owned `renpy-inspector-browser-favourites.json` file under the game's save directory. The browser imports old origin-local pins only when that file does not yet exist. Saved paths are independently sampled on the game interaction thread, even when their branches have never been opened. If the game has no writable save directory, favourites fall back to browser-local storage and Overview reports the limitation.

## How it works

F8 calls an opt-in bridge launcher on Ren'Py's interaction thread. The server binds to `127.0.0.1` on an ephemeral port and generates a new pairing token when it starts. The token is passed in the local browser URL fragment and is required in an API header. The HTTP server only serves already serialised, bounded JSON and static Ant Design assets. Child-page HTTP requests queue validated typed paths; they never inspect game objects on HTTP threads. A 250ms Ren'Py interaction-thread timer services at most two queued requests per tick and publishes a shallow root refresh around every 1.5 seconds.

The authenticated `GET /api/v1/value` endpoint queues a single typed path for safe game-thread inspection. `GET /api/v1/scripts` and `GET /api/v1/source` queue bounded read-only script requests. Label names and line numbers come from Ren'Py's runtime; source windows are read only from `.rpy` files resolving within `config.gamedir`, with symlink/traversal checks and size limits. Games distributing only `.rpyc` retain label metadata but cannot display source text. Only the `PUT /api/v1/favourites` endpoint writes data, and it is restricted to bounded, validated inspector-owned preference metadata. Gameplay variables and Ren'Py save files remain read-only. PR #12 stamps each child and favourite sample with its Ren'Py game-thread capture time so delayed HTTP responses cannot produce misleading before/after events.

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
