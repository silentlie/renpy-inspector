import test from 'node:test';
import assert from 'node:assert/strict';
import { flatten, filteredTree, keysOf, readBridgeFragment, safeFavourites } from './tree.js';

const sample = [
  { key: 'a', name: 'player', path: 'store.player', type: 'dict', preview: '2 items', children: [
    { key: 'b', name: 'health', path: "store.player['health']", type: 'int', preview: '9', children: [] },
    { key: 'c', name: 'score', path: "store.player['score']", type: 'int', preview: '10', children: [] },
  ] },
];

test('flatten yields all nested keys', () => assert.deepEqual([...flatten(sample).keys()], ['a', 'b', 'c']));
test('search preserves ancestors and matching children', () => {
  const selected = filteredTree(sample, 'HEALTH');
  assert.equal(selected[0].name, 'player');
  assert.deepEqual(selected[0].children.map((x) => x.name), ['health']);
  assert.equal(filteredTree(sample, 'missing').length, 0);
});
test('expansion keys include parents only', () => assert.deepEqual(keysOf(sample), ['a']));
test('reject invalid fragment token and foreign bridge origins', () => {
  assert.equal(readBridgeFragment('#token=foo').token, '');
  assert.equal(readBridgeFragment('#bridge=http://evil.example:1234').bridge, '');
  assert.equal(readBridgeFragment('#token=' + 'a'.repeat(64)).token.length, 64);
});
test('invalid favorites are discarded and capped', () => {
  const values = [{ scope: 'store', key: 'b' }, { scope: 'system', key: 'c' }, null];
  assert.deepEqual(safeFavourites(values), [{ scope: 'store', key: 'b' }]);
});

// A favourites view is a scoped tree, not a second permanent side panel.
test('favourite scope resolves captured nodes and keeps missing pins', async () => {
  const { favouriteNodes } = await import('./tree.js');
  const favs = favouriteNodes({ store: sample, persistent: [] }, [
    { scope: 'store', key: 'b' }, { scope: 'persistent', key: 'absent' },
  ]);
  assert.equal(favs.length, 2);
  assert.equal(favs[0].name, 'health');
  assert.equal(favs[0].favouriteScope, 'store');
  assert.equal(favs[1].state, 'missing');
  assert.equal(favs[1].favouriteScope, 'persistent');
});


test('favourite render keys stay unique when a pinned child is also inside a pinned parent', async () => {
  const { favouriteNodes } = await import('./tree.js');
  const items = favouriteNodes({ store: sample, persistent: [] }, [
    { scope: 'store', key: 'a' }, { scope: 'store', key: 'b' },
  ]);
  assert.notEqual(items[0].children[0].key, items[1].key);
  assert.equal(items[0].children[0].sourceKey, 'b');
  assert.equal(items[1].sourceKey, 'b');
});
