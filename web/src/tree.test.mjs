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


import {
  decodeTreeKey, reconcilePageNodes, integrateChildPage,
  asVirtualTreeNodes, appendPageNodes,
} from './tree.js';

test('typed tree keys reject private paths and synthetic rows', () => {
  const key = JSON.stringify(['store', [['attribute', 'player'], ['index', 0]]]);
  assert.deepEqual(decodeTreeKey(key), { scope: 'store', path: [['attribute', 'player'], ['index', 0]] });
  assert.equal(decodeTreeKey('__page__:root:store'), null);
  assert.equal(decodeTreeKey(JSON.stringify(['store', [['attribute', '__dict__']]])), null);
  assert.equal(decodeTreeKey(JSON.stringify(['bad', []])), null);
});

test('virtualised tree has independent root and branch Load More rows', () => {
  const parent = {
    key: 'p', name: 'parent', expandable: true, loaded: true, more: true,
    nextOffset: 80, children: [{ key: 'c', name: 'child', expandable: false, children: [] }],
  };
  const result = asVirtualTreeNodes([parent], 'store',
    { store: { more: true, nextOffset: 80 } });
  assert.equal(result[0].isLeaf, false);
  assert.equal(result[0].children[1].isLoadMore, true);
  assert.equal(result[0].children[1].parentKey, 'p');
  assert.equal(result[1].isLoadMore, true);
  assert.equal(result[1].parentKey, null);
});

test('page reconciliation preserves loaded descendants and stable keys', () => {
  const before = [{ key: 'a', name: 'old', loaded: true,
    children: [{ key: 'b', name: 'nested', children: [] }] },
    { key: 'extra', name: 'paged', children: [] }];
  const next = reconcilePageNodes(before, [{ key: 'a', name: 'new', children: [] }], true);
  assert.equal(next[0].name, 'new');
  assert.equal(next[0].children[0].key, 'b');
  assert.equal(next[1].key, 'extra');
  const merged = appendPageNodes(before, [{ key: 'a', name: 'updated', children: [] }]);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].children[0].key, 'b');
});

test('page responses with stale game generations are ignored', () => {
  const state = { generation: 2, scopes: { store: [{ key: 'a', children: [] }] },
    roots: { store: { more: false } } };
  assert.equal(integrateChildPage(state, {
    generation: 1, scope: 'store', items: [],
  }), state);
});

test('child pages append and set next-cursor metadata', () => {
  const state = { generation: 2,
    scopes: { store: [{ key: 'a', children: [], expandable: true }] },
    roots: { store: { more: false } } };
  const result = integrateChildPage(state, {
    scope: 'store', generation: 2, items: [{ key: 'b', children: [] }],
    next_offset: 80, more: true, capped: false,
  }, 'a');
  assert.equal(result.scopes.store[0].loaded, true);
  assert.equal(result.scopes.store[0].children[0].key, 'b');
  assert.equal(result.scopes.store[0].more, true);
});
