import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyGeneration } from './lifecycle.js';
import { createChangeTracker } from './comparison.js';
import { mergeRootSnapshot, safeFavourites } from './tree.js';

const key = JSON.stringify(['store', [['attribute', 'hp']]]);
const node = (preview) => ({ key, path: 'store.hp', state: 'value', type: 'int', preview: String(preview) });
const value = (generation, preview, time) =>
  ({ scope: 'store', node: node(preview), generation, capturedAt: time, game: {} });
const snapshot = (generation, preview) => ({
  generation, scopes: { store: [node(preview)], persistent: [] },
  root_pages: { store: { next_offset: 1, more: false }, persistent: { next_offset: 0, more: false } },
});

test('epochs only advance monotonically', () => {
  assert.equal(classifyGeneration(undefined, 0), 'new');
  assert.equal(classifyGeneration(1, 1), 'same');
  assert.equal(classifyGeneration(1, 2), 'new');
  assert.equal(classifyGeneration(2, 1), 'stale');
  assert.equal(classifyGeneration(1, -1), 'invalid');
  assert.equal(classifyGeneration(1, NaN), 'invalid');
});

test('rollback/load resets compare baseline but delayed old samples cannot rewind it', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(value(4, 10, 1));
  tracker.observeValue(value(4, 8, 2));
  assert.equal(tracker.getChanges().length, 1);
  tracker.beginGeneration(5); // authoritative restore notification
  assert.deepEqual(tracker.getChanges(), []);
  assert.equal(tracker.observeValue(value(4, 6, 3)), false);
  assert.equal(tracker.getGeneration(), 5);
  tracker.observeValue(value(5, 30, 4)); // new baseline, not a change
  assert.deepEqual(tracker.getChanges(), []);
  tracker.observeValue(value(5, 29, 5));
  assert.equal(tracker.getChanges().length, 1);
  assert.equal(tracker.getChanges()[0].before.preview, '30');
});

test('late old-generation root snapshots cannot replace restored tree', () => {
  const fresh = mergeRootSnapshot(null, snapshot(5, 30));
  assert.equal(mergeRootSnapshot(fresh, snapshot(4, 8)), fresh);
  assert.equal(mergeRootSnapshot(fresh, snapshot(5, 29)).scopes.store[0].preview, '29');
});

test('favourites remain typed paths suitable for re-resolving in a new epoch', () => {
  const favourite = { scope: 'store', key };
  assert.deepEqual(safeFavourites([favourite]), [favourite]);
});
