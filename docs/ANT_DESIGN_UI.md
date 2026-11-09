# External Ant Design interface: SugarCube-inspired PR #8

## Information architecture

PR #8 reorganizes the external inspector around the navigational pattern of
[SugarCube Inspector `codex/dev`](https://github.com/silentlie/sugarcube-inspector/tree/codex/dev)
(commit `0f533358`), without copying its JavaScript-world introspection model:

- **Overview / Variables / Scripts** are the top-level tabs.
- **Variables** contains **Store / Persistent / Favourites**, search and the
  full-width, virtualized Ant Design tree. The tree is the primary workspace.
- Each row places `key: type` on the left, a bounded value preview on the right,
  and explicit Inspect and Star actions next to it. Clicking expandable names
  or chevrons expands/collapses their already captured children.
- **Inspect** opens an on-demand details drawer. Its value is explicitly called
  a *captured preview*: the bridge does not supply unrestricted string contents.
- **Favourites** is a tree scope, not a second dashboard panel. Its paths are
  resolved from the current Store/Persistent snapshot; missing favourites remain
  visible and can be unpinned.
- Scripts shows only the safely available runtime file/line fields. The bridge
  does not expose SugarCube/Twine source or Ren'Py source text.

## Deliberate safety boundaries

This is a **frontend-only** change. The bridge is still the opt-in, loopback,
authenticated, read-only version introduced in PR #7. The 450-node global,
80-children-per-parent and four-level snapshot limits are unchanged. Search
works only against captured data, and expanding a branch never executes an
untrusted expression or requests additional Python objects over HTTP.

Implementing lazy, typed-path, per-branch inspection remains a separate
security/performance milestone. Editing/locks/undo are also deferred because
Ren'Py save/rollback semantics must be designed separately.

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
