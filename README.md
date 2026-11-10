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

- Top-level **Overview / Variables / Scripts** tabs and Store / Persistent / Favourites scopes.
- Full-width virtualised tree with **automatic paged loading** on expansion and near the end of scrolled branches. No routine "Load more" click.
- Popover search (magnifying-glass icon or `/`), on-demand details, and browser-local favourites.
- Automatic snapshot updates while the game is running. No refresh button or browser footer.
- **Experimental live watches (PR #10):** a single browser scheduler refreshes expanded branches in the active scope and independently pinned favourites without creating a timer per row.
- Read-only access: no variable editing, code evaluation, or writes to gameplay saves.

The first snapshot contains only shallow root pages. Expanding a branch fetches up to **80 child nodes per request**; as the virtual tree scrolls close to a page boundary, it requests another page automatically. While a scope is active, the shared watcher polls already-loaded expanded pages and reconciles changed previews; favourites receive independent polling even if the scope is hidden. Structural changes reset affected pagination tails to avoid keeping stale positional cursors. Bounds remain: **1,000 nodes per branch, eight path levels, 6,000 browser-loaded nodes, eight queued requests and 256 KiB per HTTP response**. This is still not an unrestricted dump of all game state. Search finds already loaded values only. Favourites are stored in the local browser origin and may not survive a port change; a pinned deep path may appear unavailable until its ancestors have been loaded.

## How it works

F8 calls an opt-in bridge launcher on Ren'Py's interaction thread. The server binds to `127.0.0.1` on an ephemeral port and generates a new pairing token when it starts. The token is passed in the local browser URL fragment and is required in an API header. The HTTP server only serves already serialised, bounded JSON and static Ant Design assets. Child-page HTTP requests queue validated typed paths; they never inspect game objects on HTTP threads. A 250ms Ren'Py interaction-thread timer services at most two queued requests per tick and publishes a shallow root refresh around every 1.5 seconds.

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

See [external inspector details](docs/EXTERNAL_GUI.md), [compatibility checklist](docs/COMPATIBILITY.md) and [development plan](PLAN.md).

## Uninstall

Remove the files installed by the inspector from `game/` (including the `renpy_inspector/` Python package and `renpy_inspector_web/` assets). Preserve all unrelated game files and saved games. The inspector's own preferences file, if present in the game's save directory, is separate from gameplay saves.
