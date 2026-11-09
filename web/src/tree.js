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
