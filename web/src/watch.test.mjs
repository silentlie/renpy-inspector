import test from 'node:test';
import assert from 'node:assert/strict';
import { collectWatchedPages, nextWatchBatch } from './watch.js';

const key = (scope, path) => JSON.stringify([scope, path]);
const store = 'store';
const owner = key(store, [['attribute','player']]);
const child = key(store, [['attribute','player'],['key','inventory']]);
const pin = key('persistent', [['attribute','choice']]);

const model = {
  generation: 1,
  scopes: {
    store: [{ key:owner, expandable:true, loaded:true, children:[
      { key:child, expandable:true, loaded:true, children:
        Array.from({length: 160}, (_,i) => ({key:key(store,[['attribute','player'],['key','inventory'],['index',i]]),children:[]})) },
    ] }],
    persistent:[{key:pin,expandable:false,children:[]}],
  },
};

test('watch expanded branches but not collapsed descendants', () => {
  const expanded={store:[owner,child],persistent:[]};
  const result=collectWatchedPages(model,expanded,'store','variables',[]);
  assert.deepEqual(result.map(x=>x.parentKey), [owner,child,child]);
  assert.deepEqual(result.map(x=>x.offset), [0,0,80]);
  const collapsed=collectWatchedPages(model,{store:[child]},'store','variables',[]);
  assert.deepEqual(collapsed,[]);
});

test('favourites have independent subscriptions when their tab is hidden', () => {
  const result=collectWatchedPages(model,{store:[],persistent:[]},'persistent','overview',
    [{scope:'store',key:child}]);
  assert.equal(result.length,1);
  assert.equal(result[0].scope,'store');
  assert.equal(result[0].parentKey,owner);
  assert.equal(result[0].offset,0);
});

test('root page zero needs no duplicate watcher and hidden scope is paused', () => {
  assert.deepEqual(collectWatchedPages(model,{},'persistent','variables',[]),[]);
  assert.deepEqual(collectWatchedPages(model,{},'store','overview',[]),[]);
});

test('watch plan deduplicates overlap and is capped', () => {
  const jobs=collectWatchedPages(model,{store:[owner,child]},'store','variables',
    [{scope:'store',key:child}],2);
  assert.equal(jobs.length,2);
  assert.equal(new Set(jobs.map(j=>j.id)).size,2);
});

test('shared scheduler rotates bounded batches rather than all watches', () => {
  const jobs=[{id:'a'},{id:'b'},{id:'c'},{id:'d'},{id:'e'}];
  let cursor=0;
  const ids=[];
  for(let i=0;i<3;i++){const next=nextWatchBatch(jobs,cursor,2);
    ids.push(...next.jobs.map(x=>x.id));cursor=next.next;}
  assert.deepEqual(ids,['a','b','c','d','e','a']);
});
