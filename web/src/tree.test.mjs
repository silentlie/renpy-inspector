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
