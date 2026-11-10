# External Ant Design workspace

**PR #8 experimental workflow.** The browser is the entire inspector UI. Ren'Py provides only the F8 key handler and read-only snapshot publishing.

## Install and launch

1. Back up the game directory and saves.
2. Get the correct engine-specific ZIP from the current [PR #8](https://github.com/silentlie/renpy-inspector/pull/8) preview or the appropriate release.
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

5. Launch the game. Press **F8** to start the loopback service and open the Ant Design UI in the default browser.
6. Press **F8** again to reopen the existing session. No native drawer, Settings screen or Inspector tab is shown.
7. To stop the local server, exit the game. Closing the browser does not stop the service.

A short in-game error notification may appear if static assets are missing or the system cannot open a browser. The read-only local service never starts automatically at game init.

## Browser interaction

The browser has top-level **Overview / Variables / Scripts** tabs, nested **Store / Persistent / Favourites** scopes, a virtual tree, a popover search, details drawers and browser-local favourites. The tree occupies the available viewport, without permanent header or footer. Search via the icon or `/`, then dismiss with Escape/Enter.

The connection state, capture timestamp, coverage warning, and read-only status live in **Overview**. The browser requests immutable snapshots automatically; there is no manual refresh button.

## Security and resource limits

- The server binds only to `127.0.0.1` on an OS-selected port, uses a **new 256-bit token when first started**, and validates Host/Origin headers. Do not share pairing URLs.
- The browser authenticates its `GET /api/v1/snapshot` requests with a token header. POST and unknown routes are rejected. The token lives in a URL fragment, not an HTTP path.
- Game values are inspected **only on the Ren'Py interaction thread**. HTTP worker threads return serialized bytes and cannot execute arbitrary Python or mutate game state.
- Each capture is bounded by 450 total nodes, 80 children per branch, four levels deep and 256 KiB. The timer publishes about every 1.5 seconds while the overlay key handler is active. Temporarily suppressed Ren'Py overlays can delay updates.
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
- Expand tree branches, search, pin/unpin, open details, and navigate Overview/Scripts.
- Close and reopen the browser; gameplay and server should continue.
- Try running with web files missing: transient diagnostic, no game crash.
- Test save/load and rollback while connected. Confirm no stale snapshot persists after game load.
- Confirm unauthenticated requests return 401 and foreign Host/Origin requests return 403. Verify no external network socket is opened.
- Repeat on Ren'Py 8, at different resolutions and window sizes, and measure FPS.
- Exit the game and confirm the local server stops.

**Not yet confirmed:** Some heavily customised games may intercept F8 or suppress overlay screens. SDK lint does not prove in-game key capture or browser launch.
