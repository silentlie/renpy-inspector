import test from 'node:test';
import assert from 'node:assert/strict';
import { createChangeTracker, comparisonText, MAX_CHANGES } from './comparison.js';

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
