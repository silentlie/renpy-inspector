/** SugarCube-style scoped subscriptions for Ren'Py's paginated tree.
 *
 * One shared scheduler in App reads this pure plan. No per-row timers, direct
 * Python object references, or HTTP access here. Favourites remain sampled
 * even when their owning tab is inactive.
 */
import { decodeTreeKey } from './tree.js';

export const WATCH_INTERVAL_MS = 1500;
export const MAX_WATCH_PAGES = 12;
export const WATCHES_PER_TICK = 2;
const PAGE_SIZE = 80;

function pagesForChildren(scope, parentKey, length, emit) {
  for (let offset = 0; offset < length; offset += PAGE_SIZE) {
    // Shallow root page zero is refreshed by the existing snapshot publisher.
    if (parentKey !== null || offset !== 0) emit(scope, parentKey, offset);
  }
}

/** Return stable primitive requests, not game references. */
export function collectWatchedPages(pages, expanded, activeScope, section, favourites,
  limit = MAX_WATCH_PAGES) {
  if (!pages || !pages.scopes || limit < 1) return [];
  const results = [];
  const seen = new Set();
  const add = (scope, parentKey, offset) => {
    if (results.length >= limit) return;
    const id = JSON.stringify([scope, parentKey, offset]);
    if (!seen.has(id)) {
      seen.add(id);
      results.push({ scope, parentKey, offset, id });
    }
  };
  // A favourite watches the page containing its value, even when its scope
  // is hidden or the parent is collapsed. It never requests unseen branches.
  const pins = new Map();
  for (const fav of (favourites ?? []).slice(0, 100)) {
    if (!['store', 'persistent'].includes(fav.scope) ||
        !decodeTreeKey(fav.key)) continue;
    const id = fav.scope + ':' + fav.key;
    pins.set(id, true);
  }
  const findPinned = (scope, nodes, parentKey) => {
    for (let i = 0; i < (nodes ?? []).length; i += 1) {
      const node = nodes[i];
      if (pins.has(scope + ':' + node.key)) {
        const offset = Math.floor(i / PAGE_SIZE) * PAGE_SIZE;
        // Root page 0 is already updated by the normal snapshot.
        if (parentKey !== null || offset > 0) add(scope, parentKey, offset);
      }
      findPinned(scope, node.children ?? [], node.key);
    }
  };
  for (const scope of ['store', 'persistent']) {
    findPinned(scope, pages.scopes[scope] ?? [], null);
  }
  const viewed = section === 'variables' && ['store', 'persistent'].includes(activeScope)
    ? activeScope : null;
  if (viewed && results.length < limit) {
    const open = new Set(expanded?.[viewed] ?? []);
    const visit = (nodes) => {
      for (const node of nodes ?? []) {
        if (results.length >= limit) return;
        if (!open.has(node.key)) continue;
        if (node.loaded) {
          pagesForChildren(viewed, node.key, node.children?.length ?? 0, add);
        }
        // A collapsed ancestor suspends its descendants' subscriptions.
        visit(node.children ?? []);
      }
    };
    pagesForChildren(viewed, null, pages.scopes[viewed]?.length ?? 0, add);
    visit(pages.scopes[viewed] ?? []);
  }
  return results;
}

/** A single tick samples only a bounded subset and rotates fairly. */
export function nextWatchBatch(jobs, cursor, batchSize = WATCHES_PER_TICK) {
  if (!jobs?.length) return { jobs: [], next: 0 };
  const n = Math.min(Math.max(0, batchSize), jobs.length);
  const start = ((cursor % jobs.length) + jobs.length) % jobs.length;
  const current = Array.from({ length: n }, (_, i) => jobs[(start + i) % jobs.length]);
  return { jobs: current, next: (start + n) % jobs.length };
}


/** Independent location subscriptions, including favourites in unloaded trees.
 * The existing shared scheduler executes these alongside active tree pages.
 */
export function collectIndependentFavouriteWatches(favourites) {
  const result = [], seen = new Set();
  for (const fav of (favourites ?? []).slice(0, 100)) {
    const decoded = decodeTreeKey(fav.key);
    if (!decoded || decoded.scope !== fav.scope || !decoded.path.length ||
        seen.has(fav.key)) continue;
    seen.add(fav.key);
    result.push({ kind: 'value', id: 'value:' + fav.key,
      scope: fav.scope, key: fav.key });
  }
  return result;
}

export function combineScopedWatches(pageJobs, favourites) {
  return [
    ...collectIndependentFavouriteWatches(favourites),
    ...(pageJobs ?? []).map((job) => ({ ...job, kind: 'page' })),
  ];
}
