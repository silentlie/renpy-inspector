# SugarCube-style live watches in the Ren'Py browser (PR #10)

Reference: [SugarCube Inspector `codex/dev` at 0f533358](https://github.com/silentlie/sugarcube-inspector/tree/0f533358c32ce7177a8412fef9218c3057aa0ae4).

## What carries across

The useful conceptual design is:
- **`watcher.ts`**: one scheduler; scope activation/suspension; batch sampling; independent favourites.
- **`VariableTree.tsx`**: root and expanded logical nodes own structural watches, even when React's virtual tree does not mount their rows.
- **`nodes.ts`**: preserve stable child locations and expanded descendants; reconcile direct-child structure.
- **`favorites.ts`**: favourites keep independent subscriptions rather than being tied to whichever variable tab is visible.
- **`comparison.ts`**: bounded, deduplicated, before/after primitive history is a future milestone, *not* a prerequisite for trustworthy live previews.

## Ren'Py adaptation

SugarCube's `readLocation` operates directly on JavaScript values in the same browser world. Ren'Py's Python runtime is in a different process. The browser must **never** retain live Python objects or tell a network thread to inspect them.

PR #9 provides a strictly typed, authenticated read-only `GET /api/v1/children` API. HTTP workers queue primitive path/page requests. The Ren'Py interaction-thread timer resolves a small batch and serialises each result.

This PR adds the **browser-side scope scheduler** in `web/src/watch.js` and a watched-page reconciliation path in `web/src/tree.js`. The scheduler refreshes *already loaded* pages using the existing endpoint. Each 1,500ms tick issues at most two page requests, rotated across at most twelve subscriptions. No additional server dependency is required.

Favourites get first priority; the active Store/Persistent scope owns root pages beyond page zero and expanded branches. Collapsed descendants pause. Root page zero is refreshed through the normal snapshot endpoint, avoiding redundant page requests.

When a watched page keeps the same stable keys, its value/type previews update without losing loaded subtrees. When children are inserted, removed, or reordered, stale later pages are discarded and the scroll sentinel can reload them. If a container becomes a scalar or changes type, previously loaded descendants are removed.

## Deliberate boundaries

- Read-only, loopback-authenticated, bounded game-thread access.
- No direct JavaScript-to-Python object subscriptions. This is *sampled* change tracking, not an engine-native event stream.
- Search remains limited to loaded data. Favourites outside loaded branches do not yet resolve independently.
- Browser-local favourites may not survive a localhost port change.
- Cached nested values may be stale until their watch is sampled; no claim of instantaneous change detection.
- Save/load generation IDs invalidate pending requests; rollback behaviour still needs interactive tests.
- No editing, locking, undo, full strings, or historical Compare in this PR.

## Review checklist

1. First verify PR #9 infinite pagination and stable F8 launch in Ren'Py 7 and 8.
2. Expand a nested object; change a scalar in-game; verify preview changes without collapsing.
3. Replace a container with a scalar; verify stale children vanish on the next watch cycle.
4. Add/remove a dict entry; verify structural reconciliation and subsequent lazy reload.
5. Collapse a branch and verify it stops consuming watch requests.
6. Pin a value, switch to Overview or another scope, change its value, then reopen Favourites.
7. Save/load while requests are in flight and verify no old-generation data reappears.
8. Inspect request rate, latency and FPS with 12 watches and large branches.
9. Check narrow-screen virtual scroll, keyboard controls and no extra scrollbars.

SDK lint and unit tests do not prove runtime or browser interaction behaviour.
