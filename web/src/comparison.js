/**
 * Bounded, session-only change history derived from read-only Ren'Py samples.
 *
 * Adapted conceptually from SugarCube Inspector's PolledChanges, but uses the
 * bridge's bounded *preview metadata* and small exact primitive samples,
 * never arbitrary full Python objects. The game thread never receives history
 * state and the browser never mutates gameplay.
 */
import { classifyGeneration } from './lifecycle.js';

export const MAX_CHANGES = 100;
export const MAX_SAMPLES = 6000;
export const MAX_PAGE_BASELINES = 96;

const SCOPES = new Set(['store', 'persistent']);
const PRIMITIVES = new Set(['bool', 'int', 'long', 'float', 'str', 'unicode', 'NoneType']);
const ABSENT = Object.freeze({ kind: 'missing', preview: 'Missing', type: 'missing' });

function sampleValue(node) {
  if (node?.state === 'missing') return ABSENT;
  if (node?.state !== 'value') return null; // failed, unavailable or cyclic reads are not changes
  const type = String(node.type ?? '');
  const preview = String(node.preview ?? '');
  const captured = node.compare_sample?.text;
  if (PRIMITIVES.has(type) && typeof captured === 'string' &&
      captured.length <= 256) {
    return { kind: 'value', preview, type, text: captured, precision: 'exact' };
  }
  if (!PRIMITIVES.has(type) || preview.length > 160 ||
      ((type === 'str' || type === 'unicode') && preview.endsWith('\u2026'))) {
    return { kind: 'other', preview: 'Not a fully captured primitive', type };
  }
  // Old bridges provide previews only, not exact primitive samples.
  return { kind: 'value', preview, type, precision: 'preview' };
}

function sameValue(a, b) {
  if (a.kind !== b.kind) return false;
  if (a.kind !== 'value') return true;
  if (a.type !== b.type) return false;
  // Two exact samples detect changes that fall beyond a 100-character preview.
  // Never infer equality from an exact sample vs an older preview-only bridge.
  if (a.precision === 'exact' && b.precision === 'exact') return a.text === b.text;
  return a.preview === b.preview;
}

function eventKind(before, after) {
  if (before.kind === 'missing') return 'added';
  if (after.kind === 'missing') return 'removed';
  return 'changed';
}

function safeContext(info) {
  const file = typeof info?.filename === 'string' ? info.filename.slice(0, 180) : '';
  const line = Number.isSafeInteger(info?.line) && info.line >= 0 ? info.line :
    (typeof info?.line === 'string' && /^\d{1,8}$/.test(info.line) ?
      Number(info.line) : null);
  return { filename: file, line };
}

function validObservation(scope, node) {
  return SCOPES.has(scope) && node && typeof node.key === 'string' &&
    typeof node.path === 'string' && node.key.length <= 2048;
}

/** All state is private to the browser tab, and never saved to gameplay. */
export function createChangeTracker({
  limit = MAX_CHANGES, sampleLimit = MAX_SAMPLES,
} = {}) {
  let generation = null;
  let nextId = 0;
  let events = [];
  const last = new Map();
  const pages = new Map();

  function adoptGeneration(incoming) {
    const transition = classifyGeneration(generation, incoming);
    if (transition === 'invalid' || transition === 'stale') return false;
    if (transition === 'new') {
      generation = incoming;
      events = []; // a game load/rollback generation is a new comparison epoch
      last.clear();
      pages.clear();
    }
    return true;
  }

  function observeOne(scope, node, timestamp, game, assumedMissing = false) {
    if (!validObservation(scope, node)) return false;
    const sampled = sampleValue(node);
    if (!sampled) return false;
    const key = node.key;
    const previous = last.get(key);
    if (previous && timestamp < previous.timestamp) return false;
    const before = previous?.sample ?? (assumedMissing ? ABSENT : null);
    last.delete(key);
    last.set(key, { sample: sampled, timestamp });
    if (last.size > sampleLimit) last.delete(last.keys().next().value);
    if (!before || sameValue(before, sampled) ||
        (before.kind !== 'value' && sampled.kind !== 'value')) return false;
    // Precision is recorded independently on each side of a transition. A
    // later re-read cannot reconstruct the full earlier value.
    events = [{
      id: String(nextId++), key, scope,
      path: node.path, kind: eventKind(before, sampled),
      before, after: sampled,
      capturedAt: timestamp, context: safeContext(game),
    }, ...events].slice(0, limit);
    return true;
  }

  function observeValue({ scope, node, generation: epoch, capturedAt, game }) {
    if (!adoptGeneration(epoch)) return false;
    const time = Number.isFinite(capturedAt) && capturedAt >= 0 ?
      capturedAt : 0;
    return observeOne(scope, node, time, game);
  }

  function observePage({
    scope, parentKey = null, offset = 0, items, more = true,
    generation: epoch, capturedAt, game,
  }) {
    if (!adoptGeneration(epoch) || !SCOPES.has(scope) ||
        !Number.isSafeInteger(offset) || offset < 0 ||
        !Array.isArray(items) || items.length > 80) return false;
    const time = Number.isFinite(capturedAt) && capturedAt >= 0 ? capturedAt : 0;
    const pageKey = JSON.stringify([scope, parentKey, offset]);
    const previousPage = pages.get(pageKey);
    if (previousPage && time < previousPage.timestamp) return false;
    const current = new Map(items.filter((node) => validObservation(scope, node))
      .map((node) => [node.key, node]));
    let changed = false;
    // Added/removed are safe conclusions only when BOTH page samples cover
    // the complete parent. A paginated boundary can shift when keys are
    // inserted, and pretending that shift is a removal would be misleading.
    const complete = offset === 0 && previousPage && !previousPage.more && !more;
    if (complete) {
      for (const [key, oldNode] of previousPage.nodes) {
        if (current.has(key)) continue;
        changed = observeOne(scope, { ...oldNode, state: 'missing' }, time, game) || changed;
      }
    }
    for (const [key, node] of current) {
      const definitelyAdded = complete && !previousPage.nodes.has(key);
      changed = observeOne(scope, node, time, game, definitelyAdded) || changed;
    }
    pages.delete(pageKey);
    pages.set(pageKey, { nodes: current, timestamp: time, more: Boolean(more) });
    if (pages.size > MAX_PAGE_BASELINES) pages.delete(pages.keys().next().value);
    return changed;
  }

  return {
    beginGeneration: adoptGeneration,
    observeValue, observePage,
    getChanges: () => events,
    getGeneration: () => generation,
    historyFor: (key, max = 20) => events.filter((e) => e.key === key).slice(0, max),
    clear: () => { events = []; }, // retain baselines, prevent false next-poll adds
    reset: () => { generation = null; events = []; last.clear(); pages.clear(); },
  };
}

export function comparisonText(value) {
  return value?.kind === 'missing' ? 'Missing' :
    value?.kind === 'other' ? 'Not a fully captured primitive' :
      value?.precision === 'exact' ? String(value.text) :
        String(value?.preview ?? 'Unavailable');
}

/** Client-side filtering of the existing 100-event history; never rescans
 * game data. Pinned state is the current list, not historical pin metadata.
 */
export function filterChanges(changes, {
  query = '', scope = 'all', kind = 'all', favouritesOnly = false,
  favourites = [], focusKey = null,
} = {}) {
  const needle = String(query).trim().toLocaleLowerCase();
  const pins = new Set((favourites ?? []).map((f) =>
    JSON.stringify([f.scope, f.key])));
  return (changes ?? []).filter((entry) => {
    if (!entry || (scope !== 'all' && entry.scope !== scope) ||
        (kind !== 'all' && entry.kind !== kind) ||
        (focusKey && entry.key !== focusKey)) return false;
    if (favouritesOnly && !pins.has(JSON.stringify([entry.scope, entry.key])))
      return false;
    return !needle ||
      String(entry.path ?? '').toLocaleLowerCase().includes(needle) ||
      String(entry.key ?? '').toLocaleLowerCase().includes(needle);
  });
}
