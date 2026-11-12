/** Pure tree helpers. No game data is evaluated or modified in the browser. */
export function flatten(nodes, map = new Map()) {
  for (const node of nodes ?? []) {
    map.set(node.key, node);
    flatten(node.children ?? [], map);
  }
  return map;
}

export function filteredTree(nodes, query) {
  const needle = String(query ?? '').trim().toLocaleLowerCase();
  if (!needle) return nodes ?? [];
  const walk = (source) => (source ?? []).flatMap((node) => {
    const children = walk(node.children);
    const hit = [node.name, node.path, node.type, node.preview]
      .some((v) => String(v ?? '').toLocaleLowerCase().includes(needle));
    return hit || children.length ? [{ ...node, children }] : [];
  });
  return walk(nodes);
}

export function keysOf(nodes) {
  const result = [];
  for (const node of nodes ?? []) {
    if (node.children?.length) result.push(node.key, ...keysOf(node.children));
  }
  return result;
}

export function readBridgeFragment(fragment) {
  const p = new URLSearchParams(String(fragment ?? '').replace(/^#/, ''));
  const token = p.get('token') ?? '';
  const bridge = p.get('bridge') ?? '';
  return {
    token: /^[a-f0-9]{64}$/.test(token) ? token : '',
    bridge: /^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(bridge) ? bridge : '',
  };
}

export function safeFavourites(data) {
  if (!Array.isArray(data)) return [];
  const unique = new Set();
  return data.filter((x) => {
    if (!x || !['store', 'persistent'].includes(x.scope) ||
        typeof x.key !== 'string' || x.key.length > 2048) return false;
    const decoded = decodeTreeKey(x.key);
    if (!decoded || decoded.scope !== x.scope || !decoded.path.length) return false;
    if (unique.has(x.key)) return false;
    unique.add(x.key);
    return true;
  }).slice(0, 100);
}

/** Resolve browser-local favourite paths against the current bounded snapshot.
 * Ant requires globally unique render keys: a favourite may also appear as a
 * descendant of another favourite, so render keys are namespaced per root.
 * sourceKey always identifies the original scope/key for pin and detail actions.
 */
export function favouriteNodes(scopes, favourites, directValues = {}) {
  const maps = {
    store: flatten(scopes?.store ?? []),
    persistent: flatten(scopes?.persistent ?? []),
  };
  const clone = (node, scope, rootKey) => ({
    ...node,
    key: JSON.stringify([scope, rootKey, node.key]),
    sourceKey: node.key,
    favouriteScope: scope,
    children: (node.children ?? []).map((child) => clone(child, scope, rootKey)),
  });
  return (favourites ?? []).map(({ scope, key }) => {
    const original = maps[scope]?.get(key);
    const live = directValues[key];
    if (live) {
      const merged = live.state === 'missing' ? { ...live, children: [], expandable: false } :
        { ...original, ...live, children: original?.children ?? [] };
      return clone(merged, scope, key);
    }
    if (original) return clone(original, scope, key);
    return {
      key: JSON.stringify([scope, key, key]), sourceKey: key,
      name: 'Waiting for favourite watch', path: key, type: 'pending',
      preview: 'Waiting for live value', state: 'pending',
      favouriteScope: scope, children: [], isLeaf: true,
    };
  });
}


/** Keys are typed JSON locations. No expression evaluation is performed. */
export function decodeTreeKey(key) {
  try {
    const pair = JSON.parse(key);
    if (!Array.isArray(pair) || pair.length !== 2 ||
        !['store', 'persistent'].includes(pair[0]) ||
        !Array.isArray(pair[1]) || pair[1].length > 8) return null;
    if (!pair[1].every((s) =>
      Array.isArray(s) && s.length === 2 &&
      ((s[0] === 'attribute' && typeof s[1] === 'string' && !s[1].startsWith('_')) ||
       (s[0] === 'index' && Number.isSafeInteger(s[1]) && s[1] >= 0) ||
       (s[0] === 'key' && (typeof s[1] === 'string' || typeof s[1] === 'boolean' ||
         Number.isSafeInteger(s[1]) || s[1] === null))))) return null;
    return { scope: pair[0], path: pair[1] };
  } catch { return null; }
}

/** Guard against reordering of independently completed HTTP samples.
 * Timestamps are captured on Ren'Py's game thread, not on arrival in React.
 * Missing stamps keep compatibility with older bridges/test fixtures.
 */
export function staleSample(last, incoming) {
  return Number.isFinite(last) && Number.isFinite(incoming) && incoming < last;
}

function sampleAt(last, incoming) {
  return Number.isFinite(incoming) ? incoming : last;
}

function preserveLoadedNode(newer, previous) {
  if (!previous) return newer;
  // A container can turn into a scalar or disappear between observations.
  // Keeping its old children would display fictitious state.
  if (newer.expandable === false ||
      (newer.state && newer.state !== 'value') ||
      (previous.type && newer.type && newer.type !== previous.type)) {
    return { ...newer, children: [], loaded: false, more: false,
      nextOffset: 0, capped: false };
  }
  return {
    ...newer,
    // A shallower root refresh cannot erase the latest child-page timestamp.
    sampledAt: previous.sampledAt,
    children: previous.loaded ? previous.children ?? [] :
      reconcilePageNodes(previous.children ?? [], newer.children ?? []),
    loaded: Boolean(previous.loaded),
    more: previous.more ?? newer.more,
    nextOffset: previous.nextOffset ?? newer.nextOffset,
    capped: previous.capped ?? newer.capped,
  };
}

/** Refresh live root previews without discarding child pages. */
export function reconcilePageNodes(previous, incoming, preserveExtra = false) {
  const old = new Map((previous ?? []).map((node) => [node.key, node]));
  const result = (incoming ?? []).map((node) => preserveLoadedNode(node, old.get(node.key)));
  if (preserveExtra) {
    const seen = new Set(result.map((node) => node.key));
    for (const node of previous ?? []) if (!seen.has(node.key)) result.push(node);
  }
  return result;
}

export function appendPageNodes(previous, incoming) {
  const result = (previous ?? []).slice();
  const index = new Map(result.map((node, i) => [node.key, i]));
  for (const node of incoming ?? []) {
    const i = index.get(node.key);
    if (i === undefined) {
      index.set(node.key, result.length);
      result.push(node);
    } else {
      result[i] = preserveLoadedNode(node, result[i]);
    }
  }
  return result;
}

function updateNode(nodes, parentKey, transform) {
  let changed = false;
  const next = (nodes ?? []).map((node) => {
    if (node.key === parentKey) {
      changed = true;
      return transform(node);
    }
    const children = updateNode(node.children, parentKey, transform);
    if (children !== node.children) {
      changed = true;
      return { ...node, children };
    }
    return node;
  });
  return changed ? next : nodes;
}

export function integrateChildPage(state, page, parentKey = null) {
  if (!state || page.generation !== state.generation ||
      !['store', 'persistent'].includes(page.scope) ||
      !Array.isArray(page.items)) return state;
  const scope = page.scope;
  const children = state.scopes[scope] ?? [];
  const meta = { nextOffset: page.next_offset, more: page.more, capped: page.capped };
  if (parentKey === null) {
    const previous = state.roots?.[scope];
    if (staleSample(previous?.sampledAt, page.captured_at)) return state;
    return {
      ...state,
      scopes: { ...state.scopes, [scope]: appendPageNodes(children, page.items) },
      roots: { ...state.roots, [scope]: {
        ...meta, sampledAt: sampleAt(previous?.sampledAt, page.captured_at),
      } },
    };
  }
  let accepted = false;
  const updated = updateNode(children, parentKey, (node) => {
    if (staleSample(node.sampledAt, page.captured_at)) return node;
    accepted = true;
    return {
      ...node, loaded: true, children: appendPageNodes(node.children, page.items),
      ...meta, sampledAt: sampleAt(node.sampledAt, page.captured_at),
    };
  });
  if (!accepted) return state;
  return { ...state, scopes: { ...state.scopes, [scope]: updated } };
}


/** Reconcile a watched page of direct children, preserving deeper loaded trees.
 * If membership/order changes, drop subsequent offset pages: their positional
 * cursors may be invalid after insertions/deletions. The scroll sentinel will
 * fetch the new tail on demand.
 */
export function refreshWatchedPage(state, page, parentKey = null, pageSize = 80) {
  if (!state || page.generation !== state.generation ||
      !['store', 'persistent'].includes(page.scope) ||
      !Number.isSafeInteger(page.offset) || page.offset < 0 ||
      !Array.isArray(page.items) || page.items.length > pageSize) return state;
  const scope = page.scope;
  const offset = page.offset;
  const nextEnd = offset + page.items.length;
  const replace = (before, metadata) => {
    // Search-revealed off-page breadcrumbs are outside the sequential
    // pagination range. Never misidentify them as offset-page members.
    const revealed = before.filter((node) => node.isRevealed);
    const sequential = before.filter((node) => !node.isRevealed);
    if (offset > sequential.length) return null;
    const oldSlice = sequential.slice(offset, offset + pageSize);
    const keepRevealed = (loaded) => {
      const seen = new Set(loaded.map((node) => node.key));
      return [...loaded, ...revealed.filter((node) => !seen.has(node.key))];
    };
    const keysStable = oldSlice.length >= page.items.length &&
      page.items.every((item, i) => oldSlice[i].key === item.key) &&
      (page.items.length === pageSize || !page.more);
    const nextSlice = page.items.map((item, i) =>
      preserveLoadedNode(item, oldSlice[i]?.key === item.key ? oldSlice[i] : undefined));
    if (keysStable) {
      // Keep already-loaded pages, unless the refreshed final page shrank.
      const tail = !page.more || page.items.length < pageSize ? [] :
        sequential.slice(offset + page.items.length);
      const next = keepRevealed([...sequential.slice(0, offset), ...nextSlice, ...tail]);
      const end = tail.length ? Math.max(nextEnd, metadata?.nextOffset ?? 0) : nextEnd;
      return { nodes: next, meta: { nextOffset: end,
        more: tail.length ? metadata?.more ?? page.more : page.more,
        capped: page.capped } };
    }
    return { nodes: keepRevealed([...sequential.slice(0, offset), ...nextSlice]),
      meta: { nextOffset: nextEnd, more: page.more, capped: page.capped } };
  };
  if (parentKey === null) {
    const previous = state.roots?.[scope];
    if (staleSample(previous?.sampledAt, page.captured_at)) return state;
    const output = replace(state.scopes?.[scope] ?? [], previous);
    if (!output) return state;
    return { ...state,
      scopes: { ...state.scopes, [scope]: output.nodes },
      roots: { ...state.roots, [scope]: {
        ...output.meta, sampledAt: sampleAt(previous?.sampledAt, page.captured_at),
      } } };
  }
  let changed = false;
  const updated = updateNode(state.scopes?.[scope] ?? [], parentKey, (node) => {
    if (staleSample(node.sampledAt, page.captured_at)) return node;
    const output = replace(node.children ?? [], node);
    if (!output) return node;
    changed = true;
    return { ...node, children: output.nodes, loaded: true, ...output.meta,
      sampledAt: sampleAt(node.sampledAt, page.captured_at) };
  });
  if (!changed) return state;
  return { ...state, scopes: { ...state.scopes, [scope]: updated } };
}

/** Synthetic Load More leaves are never game values or favourites. */
export function asVirtualTreeNodes(nodes, scope, roots, showMore = true) {
  const visit = (items) => (items ?? []).map((node) => {
    const descendants = visit(node.children ?? []);
    if (showMore && node.more) descendants.push({
      key: '__page__:' + node.key, isLoadMore: true, parentKey: node.key,
      scope, name: 'Load next 80 entries', isLeaf: true,
      nextOffset: node.nextOffset ?? 0,
    });
    return {
      ...node, title: node.name,
      isLeaf: !node.expandable || Boolean(node.loaded && !descendants.length),
      children: descendants,
    };
  });
  const result = visit(nodes);
  if (showMore && roots?.[scope]?.more) result.push({
    key: '__page__:root:' + scope, isLoadMore: true, parentKey: null,
    scope, name: 'Load next 80 entries', isLeaf: true,
    nextOffset: roots[scope].nextOffset ?? 0,
  });
  return result;
}


/** Root snapshots refresh previews but do not erase previously loaded pages. */
export function mergeRootSnapshot(previous, incoming) {
  const generation = incoming?.generation ?? 0;
  if (previous && Number.isSafeInteger(previous.generation) &&
      Number.isSafeInteger(generation) && generation < previous.generation) return previous;
  const scopes = {};
  const roots = {};
  for (const scope of ['store', 'persistent']) {
    const next = incoming?.scopes?.[scope] ?? [];
    const initial = incoming?.root_pages?.[scope] ??
      { next_offset: next.length, more: false, capped: false };
    const rootMeta = {
      nextOffset: initial.next_offset ?? next.length,
      more: Boolean(initial.more), capped: Boolean(initial.capped),
    };
    if (previous && previous.generation === generation) {
      const oldNodes = previous.scopes?.[scope] ?? [];
      const oldMeta = previous.roots?.[scope];
      if (staleSample(oldMeta?.sampledAt, incoming?.captured_at)) {
        scopes[scope] = oldNodes;
        roots[scope] = oldMeta;
        continue;
      }
      const oldSequential = oldNodes.filter((node) => !node.isRevealed);
      const stablePrefix = next.every((node, i) => oldSequential[i]?.key === node.key);
      // A newly complete root must trim previously paginated rows even if
      // the earlier snapshot still advertised more pages.
      const structuralChange = !stablePrefix ||
        (!rootMeta.more && oldNodes.length !== next.length);
      scopes[scope] = reconcilePageNodes(oldNodes, next, !structuralChange);
      const keepCursor = !structuralChange && rootMeta.more &&
        (oldMeta?.nextOffset ?? 0) > rootMeta.nextOffset;
      roots[scope] = {
        ...(keepCursor ? oldMeta : rootMeta),
        sampledAt: sampleAt(oldMeta?.sampledAt, incoming?.captured_at),
      };
    } else {
      scopes[scope] = next;
      roots[scope] = { ...rootMeta, sampledAt: incoming?.captured_at };
    }
  }
  return { generation, scopes, roots };
}


/** Materialise only the typed path returned by the trusted game-thread bridge.
 * Off-page results are inserted as breadcrumb nodes. Normal paging remains
 * sequential from the current cursor; no 1,000-node eager fetch is required.
 */
export function integrateRevealChain(state, response) {
  if (!state || response?.generation !== state.generation ||
      !['store', 'persistent'].includes(response?.scope) ||
      !Array.isArray(response.chain) || !response.chain.length ||
      response.chain.length > 8) return state;
  const scope = response.scope;
  const keys = [];
  for (let i = 0; i < response.chain.length; i += 1) {
    const node = response.chain[i];
    const decoded = typeof node?.key === 'string' ? decodeTreeKey(node.key) : null;
    if (!decoded || decoded.scope !== scope || decoded.path.length !== i + 1 ||
        !decoded.path.every((segment, n) =>
          n < i ? JSON.stringify(segment) === JSON.stringify(keys[n]) : true)) return state;
    keys.push(decoded.path[i]);
  }
  if (response.key !== response.chain[response.chain.length - 1].key) return state;
  const weave = (siblings, depth) => {
    const item = response.chain[depth];
    const current = siblings ?? [];
    const index = current.findIndex((entry) => entry.key === item.key);
    const previous = index >= 0 ? current[index] : null;
    const merged = previous ? preserveLoadedNode(item, previous) :
      { ...item, children: [], loaded: false, isRevealed: true };
    const next = depth < response.chain.length - 1
      ? { ...merged, children: weave(merged.children, depth + 1) }
      : merged;
    if (index === -1) return [...current, next];
    const updated = current.slice();
    updated[index] = next;
    return updated;
  };
  return {
    ...state,
    scopes: { ...state.scopes,
      [scope]: weave(state.scopes?.[scope] ?? [], 0) },
  };
}

/** The Tree may expand exactly the parent keys of a revealed path. */
export function revealParentKeys(response) {
  if (!Array.isArray(response?.chain)) return [];
  return response.chain.slice(0, -1).map((node) => node.key);
}
