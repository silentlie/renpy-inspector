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
