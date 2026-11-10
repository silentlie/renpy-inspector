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

## PR #11: Independent favourites and durable storage

Favourite values now use an authenticated `GET /api/v1/value` with a typed root-relative location. These reads are queued and resolved on Ren'Py's interaction thread, even when a favourite is not part of an expanded tree. Missing values stay pinned and are sampled again as the game changes. The browser shares the existing bounded watcher scheduler, issuing at most two sample jobs per tick. With many pinned locations, update latency grows.

Browser pins persist across localhost port changes in `renpy-inspector-browser-favourites.json` within the game's inspector-specific save directory. `GET /api/v1/favourites` reads this metadata and authenticated `PUT /api/v1/favourites` writes only this one JSON file after strict validation. It cannot write gameplay values, scripts, or Ren'Py saves. If no writable save directory exists, the UI displays a local-only storage status. On a fresh preference file, the browser imports its previous origin-local favourites once.

Safety: at most 100 favourites, 8 typed path segments, 1,000 enumerated members per path component, 64 KiB preference file, 4 KiB GET URL and a bounded queue. These limits can cause a valid-but-beyond-limit game variable to report missing; they are intentional rather than a reason to enable expression evaluation. Save/load generations reject stale responses.

Test in-game: pin a deep value, collapse all ancestors, switch to Overview and change the variable, then return to Favourites. Restart the game, reopen the browser on a different port and confirm pins survive. Remove an object and recreate it; the watch should move from Missing to its new value. Check a read-only save directory and unauthenticated/preflight requests.
