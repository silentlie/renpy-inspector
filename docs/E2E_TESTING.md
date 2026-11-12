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

## What this is *not*

This is **not yet a real Ren'Py runtime E2E test**. The synthetic fixture
emulates the Ren'Py interaction-thread timer and lifecycle generation change,
but does not start Ren'Py 7/8, inject F8, observe native overlays, execute
real save/load/rollback callbacks, interact with the Ren'Py renderer, or
measure gameplay FPS. Those still require the separate manual acceptance
matrix in [COMPATIBILITY.md](COMPATIBILITY.md) and
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

A future graphical SDK integration suite could run a disposable Ren'Py project
under a virtual display and inject keyboard/scene changes. That should be
implemented separately rather than overstating this browser/bridge coverage.
