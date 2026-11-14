/** Pure, conflict-aware operations on inspector-owned favourites. */
import { safeFavourites } from './tree.js';

export function readFavouriteSnapshot(data) {
  if (!data || data.version !== 1 || typeof data.initialized !== 'boolean' ||
      !Number.isSafeInteger(data.revision) || data.revision < 0 ||
      !Array.isArray(data.favourites) || data.favourites.length > 100) {
    throw new Error('Invalid inspector favourites response');
  }
  const favourites = safeFavourites(data.favourites);
  if (favourites.length !== data.favourites.length) {
    throw new Error('Invalid inspector favourite paths');
  }
  return { revision: data.revision, initialized: data.initialized, favourites };
}

export function applyFavouriteAction(favourites, action) {
  const current = safeFavourites(favourites);
  if (action?.kind === 'pin') {
    const entry = safeFavourites([action.entry])[0];
    if (!entry || current.some((x) => x.scope === entry.scope && x.key === entry.key) ||
        current.length >= 100) return current;
    return [...current, entry];
  }
  if (action?.kind === 'unpin') {
    return current.filter((x) =>
      !(x.scope === action.entry?.scope && x.key === action.entry?.key));
  }
  if (action?.kind === 'clear') {
    // Delete only the paths present when Clear All was confirmed. A new pin
    // added concurrently in another tab must not silently disappear.
    const keys = new Set((action.entries ?? []).map((x) => JSON.stringify([x.scope, x.key])));
    return current.filter((x) => !keys.has(JSON.stringify([x.scope, x.key])));
  }
  throw new Error('Invalid favourites operation');
}

export function applyFavouriteActions(favourites, actions) {
  return actions.reduce(applyFavouriteAction, safeFavourites(favourites));
}

export function sameFavourites(a, b) {
  return JSON.stringify(safeFavourites(a)) === JSON.stringify(safeFavourites(b));
}

/** request(revision, next) returns {status, data}; 409 contains the live server list. */
export async function commitFavouriteAction(base, action, request, attempts = 5) {
  let current = base;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const next = applyFavouriteAction(current.favourites, action);
    if (sameFavourites(next, current.favourites)) return current;
    const response = await request(current.revision, next);
    if (response.status === 409) {
      const latest = readFavouriteSnapshot(response.data);
      if (latest.revision <= current.revision) throw new Error('Stale preferences conflict response');
      current = latest;
      continue;
    }
    if (response.status !== 200) throw new Error('Preferences HTTP ' + response.status);
    const saved = readFavouriteSnapshot(response.data);
    if (saved.revision <= current.revision || !sameFavourites(saved.favourites, next)) {
      throw new Error('Unexpected preferences save confirmation');
    }
    return saved;
  }
  throw new Error('Favourites were updated concurrently. Retry the change.');
}
