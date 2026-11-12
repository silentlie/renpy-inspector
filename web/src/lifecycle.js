/** Monotonic game-state epoch validation shared by browser consumers.
 * Requests captured before a load/rollback may arrive after the next epoch.
 * Never let those stale responses rewind caches or Compare baselines.
 */
export function classifyGeneration(previous, incoming) {
  if (!Number.isSafeInteger(incoming) || incoming < 0) return 'invalid';
  if (!Number.isSafeInteger(previous) || previous < 0) return 'new';
  if (incoming < previous) return 'stale';
  return incoming > previous ? 'new' : 'same';
}
