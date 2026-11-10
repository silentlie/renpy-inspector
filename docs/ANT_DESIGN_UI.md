# External Ant Design interface: SugarCube-inspired PR #8

> **PR #12 development:** v0.6.4 is the published baseline. Draft PR #12 adds
> bounded, browser-session Change History and Compare. Use its v0.6.5
> preview installers to test new behaviour; the code is not yet on `main`.

## F8-only game integration

Since PR #8, the Ren'Py game has **no native Inspector GUI**. F8 starts the local server and immediately opens the browser if stopped, or reopens the same authenticated browser session if already running. In PR #9 the invisible overlay uses a 250ms request-processing timer and refreshes shallow root snapshots approximately every 1.5 seconds; connection/coverage information belongs in the browser's Overview tab.

## Information architecture

PR #8 reorganizes the external inspector around the navigational pattern of
[SugarCube Inspector `codex/dev`](https://github.com/silentlie/sugarcube-inspector/tree/codex/dev)
(commit `0f533358`), without copying its JavaScript-world introspection model:

- **Overview / Variables / Scripts** are the top-level tabs.
- **Variables** contains **Store / Persistent / Favourites / Compare**, search and the
  full-width, virtualized Ant Design tree. The tree is the primary workspace.
- Each row places `key: type` on the left, a bounded value preview on the right,
  and explicit Inspect and Star actions next to it. Clicking expandable names
  or chevrons expands/collapses their already captured children.
- **Inspect** opens an on-demand details drawer. Its value is explicitly called
  a *captured preview*: the bridge does not supply unrestricted string contents.
- **Favourites** is a tree scope, not a second dashboard panel. Its paths are
  resolved independently by the authenticated, read-only path API; missing favourites remain
  visible and can be unpinned. **Compare** has a separate scrollable workspace and
  never consumes space in the normal variable tree.
- Scripts shows only the safely available runtime file/line fields. The bridge
  does not expose SugarCube/Twine source or Ren'Py source text.

## Deliberate safety boundaries

PR #9 retains the loopback-authenticated, read-only bridge and adds a *bounded*
typed-path paging API. The first snapshot includes shallow Store/Persistent
roots; expanding a node requests its first page on the game thread. Virtual
pagination sentinels automatically request more pages as they become visible.
HTTP worker threads queue only primitive arguments and serve serialised bytes.

Limits: 80 children/page, 1,000 entries/branch, eight levels, 6,000 loaded nodes
in the browser and 256 KiB per response. Search remains restricted to *loaded*
data and favourites may be unresolved until the path is loaded. Editing,
locking, full-value access and undo/redo are still excluded.

## Verification

Run from `web/`:

```sh
npm install --no-audit --no-fund
npm test
npm run build
```

The PR CI additionally runs Python 2.7/Python 3 tests, official Ren'Py
7.4.11/7.8.7/8.4.1/8.5.3 lint and preview ZIP construction. Perform an
interactive browser smoke test at narrow and wide widths with a live Ren'Py
7/8 game before approving the UI. A successful build is not visual evidence.
