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
  return data.filter((x) => x && (x.scope === 'store' || x.scope === 'persistent') &&
    typeof x.key === 'string' && x.key.length < 2048).slice(0, 100);
}

/** Resolve browser-local favourite paths against the current bounded snapshot.
 * Ant requires globally unique render keys: a favourite may also appear as a
 * descendant of another favourite, so render keys are namespaced per root.
 * sourceKey always identifies the original scope/key for pin and detail actions.
 */
export function favouriteNodes(scopes, favourites) {
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
    if (original) return clone(original, scope, key);
    return {
      key: JSON.stringify([scope, key, key]), sourceKey: key,
      name: 'Unavailable favourite', path: key, type: 'missing',
      preview: 'Not present in current bounded snapshot', state: 'missing',
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

function preserveLoadedNode(newer, previous) {
  if (!previous) return newer;
  return {
    ...newer,
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
  if (parentKey === null) return {
    ...state,
    scopes: { ...state.scopes, [scope]: appendPageNodes(children, page.items) },
    roots: { ...state.roots, [scope]: meta },
  };
  const updated = updateNode(children, parentKey, (node) => ({
    ...node, loaded: true, children: appendPageNodes(node.children, page.items), ...meta,
  }));
  if (updated === children) return state;
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
