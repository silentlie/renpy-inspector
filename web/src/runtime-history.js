/** Observed engine signals only. Never derive dialogue turns from samples. */
export const RUNTIME_LIMIT = 64;
export const RUNTIME_KINDS = ['location', 'restoration', 'invalidation', 'rollback_flag'];

export function runtimeEventDescription(event) {
  if (!event || !RUNTIME_KINDS.includes(event.kind)) return null;
  if (event.kind === 'location') {
    return {
      title: 'Script location sampled',
      detail: typeof event.filename === 'string' && Number.isSafeInteger(event.line)
        ? `${event.filename}:${event.line}` : 'Location unavailable',
      note: 'Observed during a periodic snapshot; intermediate statements may be missed.',
    };
  }
  if (event.kind === 'invalidation' && ['edit', 'undo', 'redo'].includes(event.signal)) {
    return {
      title: event.signal === 'undo' ? 'Inspector edit undone' :
        event.signal === 'redo' ? 'Inspector edit redone' : 'Confirmed inspector edit',
      detail: event.signal === 'undo' ? 'Game-thread Store primitive restored' :
        event.signal === 'redo' ? 'Game-thread Store primitive reapplied' :
          'Game-thread Store primitive changed',
      note: 'An explicit inspector write advanced generation. This is not a Ren’Py rollback or a reconstructed game turn.',
    };
  }
  if (event.kind === 'invalidation') {
    return {
      title: 'Inspector state invalidated',
      detail: 'Inspector bridge cache reset',
      note: 'An internal reset, not evidence of a Ren\'Py load, rollback or restoration callback.',
    };
  }
  if (event.kind === 'rollback_flag') {
    return {
      title: 'Rollback indicator sampled true',
      detail: 'renpy.in_rollback() returned true',
      note: 'A sampled indicator, not a rollback count, step or destination.',
    };
  }
  const signals = {
    after_load: {
      title: 'After-load callback observed',
      detail: 'Ren\'Py after_load callback',
      note: 'A restoration notification; no earlier variable values are reconstructed.',
    },
    after_default: {
      title: 'Default-state callback observed',
      detail: 'Ren\'Py after_default callback',
      note: 'Can occur after rollback, startup or loading. The cause is not determined.',
    },
    legacy_rollback: {
      title: 'Legacy rollback probe triggered',
      detail: 'renpy.in_rollback() returned true on an interaction',
      note: 'A conservative fallback; repeated notifications may describe one rollback.',
    },
    unspecified: {
      title: 'Inspector state invalidated',
      detail: 'No callback cause supplied',
      note: 'The previous state was invalidated; no rollback cause is asserted.',
    },
  };
  return signals[event.signal] || signals.unspecified;
}

export function filteredRuntimeEvents(runtime, filter = 'all') {
  const entries = Array.isArray(runtime?.events) ? runtime.events : [];
  return entries.filter((entry) => runtimeEventDescription(entry) &&
    (filter === 'all' || entry.kind === filter)).slice(-RUNTIME_LIMIT).reverse();
}
