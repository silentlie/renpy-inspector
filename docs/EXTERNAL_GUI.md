# External Ant Design Inspector (v0.6 proof of concept)

**Status:** Experimental. This is a separate browser window, not a webview inside Ren'Py. The existing F8 native inspector stays available as a fallback. The external GUI is **read-only** and opt-in.

## Install and launch

1. Back up your game's original `game/` directory and saves.
2. Get the appropriate `renpy7` or `renpy8` ZIP from the local build or, after merge, GitHub Releases. It includes the prebuilt browser application under `game/renpy_inspector_web/`. **You do not need Node.js to use the packaged build.**
3. Extract that ZIP into the game's installation root, where `game/` already exists. Do not install both engine versions.
4. Start the game. Open the native inspector using **F8 → Settings → External inspector**.
5. Click **Start local server**, then **Open external window**. Your system browser opens the local application. The browser URL includes a fresh 64-character pairing token in its `#fragment` (not in network requests).
6. Browse Store/Persistent, use search, expand variables, view details and pin browser-local favourites. Return to Settings and click **Stop server** to disconnect.

The web application only connects to `127.0.0.1` and requests `/api/v1/snapshot` with the pairing token. The game does not transmit data to any remote service. Refreshing a snapshot does not execute user-supplied expressions or mutate gameplay data.

### Developing the web UI

From `web/`, run `npm install`, `npm run test`, and `npm run dev`. The Vite server opens at `http://127.0.0.1:5173` (Node.js 22 recommended). Start the in-game bridge first, then copy the `bridge` URL and token from the game's Settings:

```
http://127.0.0.1:5173/#token=<64-hex-token>&bridge=http%3A%2F%2F127.0.0.1%3A<bridge-port>
```

Alternatively, run `npm run build` and copy the contents of `web/dist/` into `game/renpy_inspector_web/`. Open the external window from the game. CI builds and includes this directory automatically in both release ZIPs.

### Important limits

- **Browser favourites:** They are saved by the browser for the current local origin; because the bridge uses an available port that may change, favourites might not carry across game sessions. Native Ren'Py favourites remain independent.
- **No game writes:** The HTTP bridge accepts only authenticated `GET /api/v1/snapshot`; POST and unknown paths are rejected. Browser favourites persist in that browser's origin storage, not in the game's save state or native favourites.
- **Security:** The server binds only to `127.0.0.1` on a free OS-assigned port; it uses a fresh 256-bit token each time it starts, checks the Host and Origin headers, and never includes the token in logs. Do not share the pairing URL. The browser HTML and static assets are served without a token; game data needs authentication.
- **Performance:** The game samples up to **450 nodes total**, at most **80 per branch**, and at most **four levels**. It publishes about every **1.5 seconds**, using the game interaction thread. When Ren'Py suppresses overlay screens, sampling can pause; the browser indicates when its last capture was made. These limits are *not* an exhaustive view of large game stores.
- **Thread safety:** Only serialized bytes are handled by the background HTTP thread. Game objects are inspected exclusively during the periodic native screen action.
- **Resilience:** Closing the browser has no effect on gameplay. If the loopback server cannot start, the game should show an error rather than crash. Closing the server disconnects clients.
- **Platform:** Desktop Ren'Py 7.4/7.8 and 8.4/8.5 are targeted. Browser launch, interaction and frame time still require manual smoke tests in real games. Lint does not certify runtime behaviour.
- **Browser UI is not the native overlay:** You can keep playing while looking at a separate browser/desktop window. The native inspector remains a fallback.

## Manual acceptance checklist

- Start the bridge on Ren'Py 7, open the browser GUI, expand and search a nested store variable.
- Pin a browser favourite; change the value in-game; confirm the new preview appears after a snapshot.
- Stop the server; confirm the browser reports disconnected and gameplay continues.
- Start again; confirm the prior session token no longer authorizes requests.
- Test saving/loading/rollback while connected and inspect that stale data is invalidated.
- Confirm the bridge listens on loopback only; a request without the token returns 401 and a foreign Origin/Host returns 403.
- Repeat on Ren'Py 8 and measure FPS/CPU with the native and external inspectors off/on.
