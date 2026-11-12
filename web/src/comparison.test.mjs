import test from 'node:test';
import assert from 'node:assert/strict';
import { createChangeTracker, comparisonText, filterChanges, MAX_CHANGES } from './comparison.js';

const key = (path) => JSON.stringify(['store', [['attribute', path]]]);
const node = (name, preview, type = 'int') => ({
  key: key(name), name, path: 'store.' + name,
  state: 'value', preview: String(preview), type,
});
const page = (items, time, options = {}) => ({
  scope: 'store', parentKey: null, offset: 0, items, more: false,
  generation: 1, capturedAt: time,
  game: { filename: 'script.rpy', line: 42 }, ...options,
});
const direct = (n, time, options = {}) => ({
  scope: 'store', node: n, generation: 1, capturedAt: time,
  game: { filename: 'script.rpy', line: 42 }, ...options,
});

test('first snapshot is baseline and later primitive change is captured', () => {
  const tracker = createChangeTracker();
  assert.equal(tracker.observePage(page([node('hp', 10)], 1)), false);
  assert.equal(tracker.getChanges().length, 0);
  assert.equal(tracker.observePage(page([node('hp', 8)], 2)), true);
  const [change] = tracker.getChanges();
  assert.equal(change.kind, 'changed');
  assert.equal(change.before.preview, '10');
  assert.equal(change.after.preview, '8');
  assert.deepEqual(change.context, { filename: 'script.rpy', line: 42 });
  assert.equal(change.key, key('hp'));
});

test('overlapping direct and page samples deduplicate and ignore stale data', () => {
  const tracker = createChangeTracker();
  tracker.observePage(page([node('hp', 10)], 100));
  tracker.observeValue(direct(node('hp', 9), 102));
  tracker.observePage(page([node('hp', 10)], 101)); // delayed root response
  tracker.observeValue(direct(node('hp', 9), 103));
  assert.equal(tracker.getChanges().length, 1);
  assert.equal(tracker.getChanges()[0].after.preview, '9');
});

test('complete branch detects added and removed primitives', () => {
  const tracker = createChangeTracker();
  tracker.observePage(page([node('a', 1)], 1));
  tracker.observePage(page([node('a', 1), node('b', 2)], 2));
  tracker.observePage(page([node('b', 2)], 3));
  assert.deepEqual(tracker.getChanges().map(x => x.kind), ['removed', 'added']);
  assert.deepEqual(tracker.getChanges().map(x => x.key), [key('a'), key('b')]);
});

test('partial page movement cannot masquerade as added/removed values', () => {
  const tracker = createChangeTracker();
  tracker.observePage(page([node('a', 1)], 1, { more: true }));
  tracker.observePage(page([node('b', 2)], 2, { more: true }));
  assert.deepEqual(tracker.getChanges(), []);
});

test('direct missing and recovery are captured without opening a branch', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('hp', 10), 1));
  tracker.observeValue(direct({ ...node('hp', 10), state: 'missing' }, 2));
  tracker.observeValue(direct(node('hp', 27), 3));
  assert.deepEqual(tracker.getChanges().map(x => x.kind), ['added', 'removed']);
  assert.equal(tracker.historyFor(key('hp')).length, 2);
});

test('load generation clears baselines/history without fake transitions', () => {
  const tracker = createChangeTracker();
  tracker.observePage(page([node('hp', 10)], 1));
  tracker.observePage(page([node('hp', 4)], 2));
  assert.equal(tracker.getChanges().length, 1);
  tracker.observePage(page([node('hp', 70)], 3, { generation: 2 }));
  assert.equal(tracker.getChanges().length, 0);
  tracker.observePage(page([node('hp', 69)], 4, { generation: 2 }));
  assert.equal(tracker.getChanges().length, 1);
});

test('clear history retains current baselines', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('hp', 1), 1));
  tracker.observeValue(direct(node('hp', 2), 2));
  tracker.clear();
  assert.equal(tracker.getChanges().length, 0);
  tracker.observeValue(direct(node('hp', 2), 3));
  assert.equal(tracker.getChanges().length, 0);
  tracker.observeValue(direct(node('hp', 3), 4));
  assert.equal(tracker.getChanges().length, 1);
  assert.equal(tracker.getChanges()[0].before.preview, '2');
});

test('bounded session history keeps newest hundred records', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('hp', 0), 0));
  for (let i = 1; i <= MAX_CHANGES + 15; i++) {
    tracker.observeValue(direct(node('hp', i), i));
  }
  assert.equal(tracker.getChanges().length, MAX_CHANGES);
  assert.equal(tracker.getChanges()[0].after.preview, '115');
  assert.equal(tracker.getChanges().at(-1).after.preview, '16');
});

test('truncated strings and object previews do not appear as exact values', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('dialogue', "'hello...'\u2026", 'str'), 1));
  tracker.observeValue(direct(node('dialogue', "'different...'\u2026", 'str'), 2));
  tracker.observeValue(direct(node('inventory', '4 items', 'dict'), 2));
  tracker.observeValue(direct(node('inventory', '5 items', 'dict'), 3));
  assert.equal(tracker.getChanges().length, 0);
  assert.equal(comparisonText({ kind: 'other' }), 'Not a fully captured primitive');
});

test('invalid samples do not erase reliable baseline or create spurious changes', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('hp', 10), 1));
  tracker.observeValue(direct({ ...node('hp', 10), state: 'error' }, 2));
  tracker.observeValue(direct(node('hp', 12), 3));
  assert.equal(tracker.getChanges().length, 1);
  assert.equal(tracker.getChanges()[0].before.preview, '10');
});

test('a comparison event includes the actual sampled context, not invented turns', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('xp', 1), 1));
  tracker.observeValue(direct(node('xp', 2), 2, { game: { line: '99', filename: 'scene.rpy' } }));
  const change = tracker.getChanges()[0];
  assert.deepEqual(change.context, { filename: 'scene.rpy', line: 99 });
  assert.equal('passage' in change, false);
  assert.equal('turn' in change, false);
});


test('exact small strings detect changes hidden beyond truncated previews', () => {
  const tracker = createChangeTracker();
  const prefix = 'A'.repeat(110);
  const preview = "'"+ prefix.slice(0, 100) + "'…";
  const first = {
    ...node('memo', preview, 'str'), compare_sample: { text: prefix + 'before' },
  };
  const second = {
    ...node('memo', preview, 'str'), compare_sample: { text: prefix + 'after' },
  };
  tracker.observeValue(direct(first, 10));
  tracker.observeValue(direct(second, 11));
  assert.equal(tracker.getChanges().length, 1);
  const [change] = tracker.getChanges();
  assert.equal(change.before.precision, 'exact');
  assert.equal(change.after.precision, 'exact');
  assert.equal(comparisonText(change.before), prefix + 'before');
  assert.equal(comparisonText(change.after), prefix + 'after');
  tracker.observeValue(direct(second, 12));
  assert.equal(tracker.getChanges().length, 1);
});

test('mixed old preview-only and exact comparisons clearly label their precision', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('score', 2), 1));
  tracker.observeValue(direct({
    ...node('score', 3), compare_sample: { text: '3' },
  }, 2));
  const [change] = tracker.getChanges();
  assert.equal(change.before.precision, 'preview');
  assert.equal(change.after.precision, 'exact');
  assert.equal(comparisonText(change.before), '2');
  assert.equal(comparisonText(change.after), '3');
});

test('preview-same samples from different precision do not create spurious events', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct(node('score', 10), 1));
  tracker.observeValue(direct({
    ...node('score', 10), compare_sample: { text: '10' },
  }, 2));
  assert.equal(tracker.getChanges().length, 0);
});

test('filter history by path, kind, scope, favourite and exact focused typed key', () => {
  const storeKey = key('hp');
  const persistentKey = JSON.stringify(['persistent', [['attribute', 'flags']]]);
  const changes = [
    { id: '1', key: storeKey, scope: 'store', path: 'store.hp', kind: 'changed' },
    { id: '2', key: persistentKey, scope: 'persistent', path: 'persistent.flags', kind: 'added' },
    { id: '3', key: key('xp'), scope: 'store', path: 'store.xp', kind: 'removed' },
  ];
  const favourites = [{ scope: 'store', key: storeKey }];
  assert.deepEqual(filterChanges(changes, { query: 'HP' }).map(e => e.id), ['1']);
  assert.deepEqual(filterChanges(changes, { scope: 'persistent' }).map(e => e.id), ['2']);
  assert.deepEqual(filterChanges(changes, { kind: 'removed' }).map(e => e.id), ['3']);
  assert.deepEqual(filterChanges(changes, { favouritesOnly: true, favourites }).map(e => e.id), ['1']);
  assert.deepEqual(filterChanges(changes, { focusKey: persistentKey }).map(e => e.id), ['2']);
  assert.deepEqual(filterChanges(changes, {
    focusKey: storeKey, scope: 'persistent', favouritesOnly: true, favourites,
  }), []);
});

test('exact sample guards against untrusted oversized metadata', () => {
  const tracker = createChangeTracker();
  tracker.observeValue(direct({
    ...node('text', 'preview', 'str'), compare_sample: { text: 'x'.repeat(300) },
  }, 1));
  tracker.observeValue(direct({
    ...node('text', 'different', 'str'), compare_sample: { text: 'x'.repeat(300) },
  }, 2));
  const change = tracker.getChanges()[0];
  assert.equal(change.before.precision, 'preview');
  assert.equal(change.after.precision, 'preview');
});
