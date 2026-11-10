/**
 * Bounded, session-only change history derived from read-only Ren'Py samples.
 *
 * Adapted conceptually from SugarCube Inspector's PolledChanges, but uses the
 * bridge's bounded *previews*, not full Python values. The game thread never
 * receives history state and the browser never mutates gameplay.
 */
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
  if (!PRIMITIVES.has(type) || preview.length > 160 ||
      ((type === 'str' || type === 'unicode') && preview.endsWith('\u2026'))) {
    return { kind: 'other', preview: 'Not a fully captured primitive', type };
  }
  return { kind: 'value', preview, type };
}

function sameValue(a, b) {
  return a.kind === b.kind &&
    (a.kind !== 'value' || (a.type === b.type && a.preview === b.preview));
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
    if (!Number.isSafeInteger(incoming) || incoming < 0) return false;
    if (generation !== incoming) {
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
    // Do not label a preview-only string as its complete actual value.
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
      String(value?.preview ?? 'Unavailable');
}
