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
- Full-width virtualized tree with type and bounded value previews.
- Popover search (magnifying-glass icon or `/`), on-demand details, and browser-local favourites.
- Automatic snapshot updates while the game is running. No refresh button or browser footer.
- Read-only access: no variable editing, code evaluation, or writes to gameplay saves.

Snapshot limits are conservative: **450 nodes total**, **80 children per branch**, **four levels deep** and **256 KiB per response**. Search operates only on captured values, not arbitrary Python paths. Favourites are stored in the local browser origin and may not survive a port change.

## How it works

F8 calls an opt-in bridge launcher on Ren'Py's interaction thread. The server binds to `127.0.0.1` on an ephemeral port and generates a new pairing token when it starts. The token is passed in the local browser URL fragment and is required in an API header. The HTTP server only serves already serialized, bounded JSON and static Ant Design assets. Game values are collected on Ren'Py's interaction thread by a 1.5-second timer while the server runs.

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
