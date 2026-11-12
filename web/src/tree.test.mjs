import test from 'node:test';
import assert from 'node:assert/strict';
import { flatten, filteredTree, keysOf, readBridgeFragment, safeFavourites, formatTypedPath } from './tree.js';

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
  const key = JSON.stringify(['store', [['attribute', 'player']]]);
  const values = [{ scope: 'store', key }, { scope: 'system', key: 'c' },
    { scope: 'store', key: 'b' }, { scope: 'store', key }, null];
  assert.deepEqual(safeFavourites(values), [{ scope: 'store', key }]);
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
  assert.equal(favs[1].state, 'pending');
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


import { mergeRootSnapshot } from './tree.js';

test('new snapshot refreshes previews without erasing loaded child pages', () => {
  const previous = {
    generation: 3,
    scopes: { store: [{ key: 'p', loaded: true,
      children: [{ key: 'child', name: 'loaded' }] },
      { key: 'after80', name: 'paged' }], persistent: [] },
    roots: { store: { nextOffset: 160, more: true } },
  };
  const incoming = {
    generation: 3,
    scopes: { store: [{ key: 'p', name: 'fresh', children: [] }], persistent: [] },
    root_pages: { store: { next_offset: 80, more: true } },
  };
  const merged = mergeRootSnapshot(previous, incoming);
  assert.equal(merged.scopes.store[0].name, 'fresh');
  assert.equal(merged.scopes.store[0].children[0].name, 'loaded');
  assert.equal(merged.scopes.store[1].name, 'paged');
  assert.equal(merged.roots.store.nextOffset, 160);
  const reset = mergeRootSnapshot(merged, { ...incoming, generation: 4 });
  assert.equal(reset.scopes.store.length, 1);
  assert.equal(reset.scopes.store[0].children.length, 0);
  assert.equal(reset.roots.store.nextOffset, 80);
});


import { refreshWatchedPage } from './tree.js';

test('watched pages update previews without losing expanded grandchildren', () => {
  const parent = { key:'parent', type:'dict', expandable:true,loaded:true,
    nextOffset:2,more:false,children:[
      {key:'a',name:'a',type:'int',state:'value',preview:'1',children:[]},
      {key:'nested',name:'nested',type:'dict',state:'value',expandable:true,loaded:true,
        children:[{key:'deep',name:'deep',preview:'20',children:[]}],preview:'1 item'},
    ]};
  const state={generation:1,scopes:{store:[parent]},roots:{}};
  const next=refreshWatchedPage(state,{scope:'store',generation:1,
    offset:0,next_offset:2,more:false,items:[
      {key:'a',name:'a',type:'int',state:'value',preview:'9',children:[]},
      {key:'nested',name:'nested',type:'dict',state:'value',expandable:true,
        preview:'1 item',children:[]},
    ]},'parent');
  assert.equal(next.scopes.store[0].children[0].preview,'9');
  assert.equal(next.scopes.store[0].children[1].children[0].key,'deep');
  assert.equal(next.scopes.store[0].children[1].loaded,true);
});

test('structural replacement removes stale child pages and resets cursor', () => {
  const prior={generation:5,scopes:{store:[{key:'p',loaded:true,
    children:[{key:'old',type:'int',preview:'7'}, {key:'tail',type:'int'}],
    nextOffset:2,more:false}]},roots:{}};
  const result=refreshWatchedPage(prior,{scope:'store',generation:5,
    offset:0,items:[{key:'new',type:'int',state:'value',preview:'8'}],
    next_offset:1,more:true,capped:false},'p');
  assert.deepEqual(result.scopes.store[0].children.map(n=>n.key),['new']);
  assert.equal(result.scopes.store[0].nextOffset,1);
  assert.equal(result.scopes.store[0].more,true);
});

test('scalars and changed types lose stale expanded children', () => {
  const old=[{key:'x',type:'dict',state:'value',expandable:true,loaded:true,
    children:[{key:'y',type:'str'}]}];
  const next=reconcilePageNodes(old,[{key:'x',type:'int',state:'value',expandable:false,children:[]}]);
  assert.equal(next[0].loaded,false);
  assert.deepEqual(next[0].children,[]);
});

test('stale watched pages from a previous load are ignored', () => {
  const state={generation:7,scopes:{store:[]},roots:{}};
  const page={scope:'store',generation:6,offset:0,items:[]};
  assert.equal(refreshWatchedPage(state,page),state);
});


test('watched final page trims old loaded tails after a container shrinks', () => {
  const old=Array.from({length:160},(_,i)=>({
    key:String(i),type:'int',state:'value',expandable:false,preview:String(i),
  }));
  const state={generation:7,scopes:{store:[{key:'list',loaded:true,
    nextOffset:160,more:true,children:old}]},roots:{}};
  const page={scope:'store',generation:7,offset:0,next_offset:80,
    more:false,capped:false,items:old.slice(0,80).map(n=>({...n,preview:'updated'}))};
  const updated=refreshWatchedPage(state,page,'list');
  assert.equal(updated.scopes.store[0].children.length,80);
  assert.equal(updated.scopes.store[0].nextOffset,80);
  assert.equal(updated.scopes.store[0].more,false);
  assert.equal(updated.scopes.store[0].children[0].preview,'updated');
});


test('direct watch can render a favourite never present in the lazy tree', async () => {
  const { favouriteNodes } = await import('./tree.js');
  const key = JSON.stringify(['store', [['attribute', 'profile'], ['key', 'level']]]);
  const nodes = favouriteNodes({ store: [], persistent: [] },
    [{ scope: 'store', key }], { [key]: {
      key, name: 'level', path: 'store.profile["level"]',
      type: 'int', preview: '14', state: 'value', expandable: false,
      children: [],
    }});
  assert.equal(nodes[0].preview, '14');
  assert.equal(nodes[0].sourceKey, key);
  assert.equal(nodes[0].favouriteScope, 'store');
});

test('missing direct-watch value overrides a stale loaded tree preview', async () => {
  const { favouriteNodes } = await import('./tree.js');
  const key = JSON.stringify(['persistent', [['attribute', 'flag']]]);
  const original = { key, name: 'flag', type: 'dict',
    preview: '3 items', state: 'value', expandable: true, children: [
      { key:'oldchild', name:'old', children:[] },
    ] };
  const nodes = favouriteNodes({ store: [], persistent: [original] },
    [{ scope: 'persistent', key }], { [key]: {
      key, name:'flag', type:'missing', preview:'<missing>',
      state:'missing', expandable:false, children:[],
    }});
  assert.equal(nodes[0].state, 'missing');
  assert.equal(nodes[0].children.length, 0);
});


import { integrateRevealChain, revealParentKeys } from './tree.js';

test('search reveal materialises a deeply nested match beyond the first root page', () => {
  const key = (steps) => JSON.stringify(['store', steps]);
  const p = [['attribute', 'late_root']];
  const q = [...p, ['key', 'stats']];
  const r = [...q, ['key', 'hp']];
  const chain = [
    {key:key(p),name:'late_root',type:'dict',state:'value',expandable:true,children:[]},
    {key:key(q),name:"['stats']",type:'dict',state:'value',expandable:true,children:[]},
    {key:key(r),name:"['hp']",type:'int',state:'value',preview:'81',expandable:false,children:[]},
  ];
  const state={generation:4,scopes:{
    store:[{key:key([['attribute','existing']]),name:'existing',children:[]}],
    persistent:[],
  },roots:{store:{nextOffset:80,more:true}}};
  const result=integrateRevealChain(state,{
    generation:4,scope:'store',key:key(r),chain,
  });
  assert.equal(result.scopes.store.length,2);
  assert.equal(result.scopes.store[1].children[0].children[0].preview,'81');
  assert.equal(result.roots.store.nextOffset,80);
  assert.deepEqual(revealParentKeys({chain}),[key(p),key(q)]);
  assert.deepEqual(result.scopes.persistent,[]);
  const repeated=integrateRevealChain(result,{generation:4,scope:'store',key:key(r),chain});
  assert.equal(repeated.scopes.store.length,2);
});

test('search reveal rejects stale epochs, malformed keys and fake path prefixes', () => {
  const state={generation:8,scopes:{store:[],persistent:[]},roots:{}};
  const key=(steps)=>JSON.stringify(['store',steps]);
  const first={key:key([['attribute','a']]),expandable:true,children:[]};
  const other={key:key([['attribute','b'],['key','child']]),children:[]};
  const bad={scope:'store',generation:8,key:other.key,chain:[first,other]};
  assert.equal(integrateRevealChain(state,bad),state);
  assert.equal(integrateRevealChain(state,{...bad,generation:7}),state);
  assert.equal(integrateRevealChain(state,{...bad,chain:[{key:'not JSON'}]}),state);
});

test('reveal does not overwrite an already expanded branch on a second lookup', () => {
  const key=(steps)=>JSON.stringify(['store',steps]);
  const path=[['attribute','owner']];
  const parent={key:key(path),name:'owner',type:'dict',state:'value',expandable:true,
    loaded:true,nextOffset:80,more:true,children:[
      {key:key([...path,['key','existing']]),name:'existing',children:[]},
    ]};
  const next={key:key([...path,['key','new']]),name:'new',type:'int',state:'value',
    preview:'17',expandable:false,children:[]};
  const state={generation:1,scopes:{store:[parent],persistent:[]},roots:{}};
  const result=integrateRevealChain(state,{generation:1,scope:'store',key:next.key,
    chain:[{...parent,children:[]},next]});
  assert.equal(result.scopes.store[0].children.length,2);
  assert.equal(result.scopes.store[0].nextOffset,80);
  assert.equal(result.scopes.store[0].loaded,true);
});




test('off-page search reveal survives root snapshots and watched pagination', () => {
  const key=(steps)=>JSON.stringify(['store',steps]);
  const first=Array.from({length:80},(_,i)=>({
    key:key([['attribute','field_'+String(i).padStart(3,'0')]]),
    type:'int',state:'value',name:'field',expandable:false,children:[],
  }));
  const root={generation:1,scopes:{store:first,persistent:[]},
    roots:{store:{nextOffset:80,more:true,capped:false}}};
  const target={key:key([['attribute','field_900']]),name:'field_900',type:'int',
    state:'value',preview:'900',expandable:false,children:[]};
  const revealed=integrateRevealChain(root,{
    generation:1,scope:'store',key:target.key,chain:[target],
  });
  assert.equal(revealed.scopes.store.length,81);
  assert.equal(revealed.scopes.store[80].isRevealed,true);
  const fresh=mergeRootSnapshot(revealed,{
    generation:1,scopes:{store:first,persistent:[]},
    root_pages:{store:{next_offset:80,more:true},persistent:{next_offset:0,more:false}},
  });
  assert.equal(fresh.scopes.store.length,81);
  const page80=Array.from({length:80},(_,i)=>({
    key:key([['attribute','field_'+String(i+80).padStart(3,'0')]]),
    type:'int',state:'value',expandable:false,children:[],
  }));
  const updated=refreshWatchedPage(fresh,{
    generation:1,scope:'store',offset:80,items:page80,
    next_offset:160,more:true,capped:false,
  });
  assert.equal(updated.scopes.store.length,161);
  assert.equal(updated.scopes.store[160].key,target.key);
  assert.equal(updated.roots.store.nextOffset,160);
});

import { staleSample } from './tree.js';

test('completed root snapshots retire paged tails and off-page breadcrumbs', () => {
  const source = Array.from({length: 160}, (_, i) => ({
    key: 'k' + i, name: 'item ' + i, type: 'int', state: 'value',
    preview: '' + i, expandable: false, children: [],
  }));
  const previous = {generation: 9, scopes: {store: [...source, {
    key: 'reveal', isRevealed: true, type: 'int', state: 'value', children: [],
  }], persistent: []}, roots: {store: {
    nextOffset: 160, more: true, sampledAt: 100,
  }}};
  const incoming = {generation: 9, captured_at: 150,
    scopes: {store: source.slice(0, 30), persistent: []},
    root_pages: {store: {next_offset: 30, more: false, capped: false}}};
  const after = mergeRootSnapshot(previous, incoming);
  assert.equal(after.scopes.store.length, 30);
  assert.equal(after.scopes.store[29].key, 'k29');
  assert.equal(after.roots.store.nextOffset, 30);
  assert.equal(after.roots.store.more, false);
  assert.equal(after.roots.store.sampledAt, 150);
});

test('older HTTP page samples cannot rewind a later tree sample', () => {
  const key = JSON.stringify(['store', [['attribute', 'bag']]]);
  const item = (preview) => ({
    key: JSON.stringify(['store', [['attribute', 'bag'], ['key', 'item']]]),
    type: 'int', state: 'value', expandable: false, preview, children: [],
  });
  const root = mergeRootSnapshot(null, {generation: 7, captured_at: 100,
    scopes: {store: [{key, type: 'dict', state: 'value', expandable: true, children: []}],
      persistent: []},
    root_pages: {store: {next_offset: 1, more: false}}});
  const recent = integrateChildPage(root, {scope: 'store', generation: 7,
    captured_at: 130, items: [item('new')], offset: 0,
    next_offset: 1, more: false, capped: false}, key);
  assert.equal(recent.scopes.store[0].children[0].preview, 'new');
  assert.equal(recent.scopes.store[0].sampledAt, 130);
  const old = refreshWatchedPage(recent, {scope: 'store', generation: 7,
    captured_at: 120, items: [item('old')], offset: 0,
    next_offset: 1, more: false, capped: false}, key);
  assert.equal(old, recent);
  const oldAppend = integrateChildPage(recent, {scope: 'store', generation: 7,
    captured_at: 125, items: [item('old')], offset: 0,
    next_offset: 1, more: false, capped: false}, key);
  assert.equal(oldAppend, recent);
  const next = refreshWatchedPage(recent, {scope: 'store', generation: 7,
    captured_at: 145, items: [item('latest')], offset: 0,
    next_offset: 1, more: false, capped: false}, key);
  assert.equal(next.scopes.store[0].children[0].preview, 'latest');
});

test('root snapshots cannot regress a newer watched root page', () => {
  const root = mergeRootSnapshot(null, {generation: 4, captured_at: 100,
    scopes: {store: [{key: 'a', type: 'int', state: 'value',
      preview: 'old', expandable: false, children: []}], persistent: []},
    root_pages: {store: {next_offset: 1, more: false}}});
  const fresh = refreshWatchedPage(root, {scope: 'store', generation: 4,
    offset: 0, captured_at: 170, items: [{
      key: 'a', type: 'int', state: 'value', preview: 'fresh',
      expandable: false, children: [],
    }], next_offset: 1, more: false, capped: false});
  const delayed = mergeRootSnapshot(fresh, {generation: 4, captured_at: 150,
    scopes: {store: [{key: 'a', type: 'int', state: 'value',
      preview: 'old', expandable: false, children: []}], persistent: []},
    root_pages: {store: {next_offset: 1, more: false}}});
  assert.equal(delayed.scopes.store[0].preview, 'fresh');
  assert.equal(delayed.roots.store.sampledAt, 170);
  assert.equal(staleSample(170, 150), true);
  assert.equal(staleSample(170, 171), false);
});

test('root preview is not rolled back after a newer expanded-child sample', () => {
  const owner = JSON.stringify(['store', [['attribute', 'owner']]]);
  const child = JSON.stringify(['store', [['attribute', 'owner'], ['key', 'hp']]]);
  const initial = mergeRootSnapshot(null, {generation: 2, captured_at: 100,
    scopes: {store: [{key: owner, type: 'dict', state: 'value', preview: 'old',
      expandable: true, children: []}], persistent: []}});
  const sampled = integrateChildPage(initial, {scope: 'store', generation: 2,
    captured_at: 130, offset: 0, next_offset: 1, more: false,
    items: [{key: child, type: 'int', state: 'value',
      preview: '7', expandable: false, children: []}]}, owner);
  const oldRoot = mergeRootSnapshot(sampled, {generation: 2, captured_at: 120,
    scopes: {store: [{key: owner, type: 'dict', state: 'value',
      preview: 'stale', expandable: true, children: []}], persistent: []}});
  assert.equal(oldRoot.scopes.store[0].sampledAt, 130);
  assert.equal(oldRoot.scopes.store[0].preview, 'old');
  assert.equal(oldRoot.scopes.store[0].children[0].preview, '7');
});

test('late nested page cannot resurrect scalar or missing root children', () => {
  const root = mergeRootSnapshot(null, {generation: 2, captured_at: 180,
    scopes: {store: [{key: 'p', type: 'int', state: 'value',
      expandable: false, children: []}], persistent: []}});
  const stale = integrateChildPage(root, {scope: 'store', generation: 2,
    captured_at: 160, offset: 0, items: [{key: 'old', children: []}],
    next_offset: 1, more: false}, 'p');
  assert.equal(stale, root);
  const impossible = integrateChildPage(root, {scope: 'store', generation: 2,
    captured_at: 190, offset: 0, items: [{key: 'old', children: []}],
    next_offset: 1, more: false}, 'p');
  assert.equal(impossible, root);
});

test('older root pagination reply does not undo a structural shrink', () => {
  const state = mergeRootSnapshot(null, {generation: 5, captured_at: 190,
    scopes: {store: [{key:'a', type:'int', state:'value', expandable: false,
      children: []}], persistent: []},
    root_pages: {store: {next_offset: 1, more: false}}});
  const stale = integrateChildPage(state, {scope: 'store', generation: 5,
    captured_at: 100, offset: 80, items: [{key: 'vanished'}],
    next_offset: 81, more: true}, null);
  assert.equal(stale, state);
});

test('copyable typed paths retain uncapped names and safely quote keys', () => {
  assert.equal(formatTypedPath(JSON.stringify(['store', [
    ['attribute', 'player'], ['key', 'has space'], ['index', 2],
  ]])), 'store.player["has space"][2]');
  assert.equal(formatTypedPath(JSON.stringify(['persistent', [
    ['attribute', 'flags'], ['key', true], ['key', null],
  ]])), 'persistent.flags[True][None]');
  const veryLong = 'a'.repeat(400);
  assert.equal(formatTypedPath(JSON.stringify(['store', [
    ['attribute', 'info'], ['key', veryLong],
  ]])), 'store.info["' + veryLong + '"]');
  assert.equal(formatTypedPath('not a typed path'), '');
});


test('typed member paths decode and format distinctly from dictionary keys or list indexes', () => {
  const path = JSON.stringify(['store', [['attribute', 'flags'], ['member', 42]]]);
  assert.deepEqual(decodeTreeKey(path).path[1], ['member', 42]);
  assert.equal(formatTypedPath(path), 'store.flags{42}');
  assert.equal(formatTypedPath(JSON.stringify(['store', [
    ['attribute', 'flags'], ['key', 42],
  ]])), 'store.flags[key:42]');
  assert.equal(formatTypedPath(JSON.stringify(['store', [
    ['attribute', 'flags'], ['index', 42],
  ]])), 'store.flags[42]');
  assert.equal(decodeTreeKey(JSON.stringify(['store', [
    ['attribute', 'flags'], ['member', {}],
  ]])), null);
  assert.equal(decodeTreeKey(JSON.stringify(['store', [
    ['attribute', 'flags'], ['member', 'X'.repeat(257)],
  ]])), null);
  assert.equal(decodeTreeKey(JSON.stringify(['store', [
    ['attribute', 'flags'], ['member', 9007199254740992],
  ]])), null);
});
