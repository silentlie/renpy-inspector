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


import { collectIndependentFavouriteWatches, combineScopedWatches } from './watch.js';

test('independent watches include deep favourite keys outside loaded tree', () => {
  const path = JSON.stringify(['store', [['attribute', 'nested'], ['key', 'score']]]);
  const values = collectIndependentFavouriteWatches([
    { scope:'store', key:path }, { scope:'store', key:path },
    { scope:'persistent', key:path }, { scope:'store', key:'bad' },
  ]);
  assert.equal(values.length, 1);
  assert.equal(values[0].key, path);
  assert.equal(values[0].kind, 'value');
});

test('one shared poll plan contains values and expanded pages', () => {
  const path = JSON.stringify(['persistent', [['attribute', 'flag']]]);
  const jobs = combineScopedWatches([{ scope:'store', parentKey:'p',
    offset:0, id:'page-p' }], [{ scope:'persistent', key:path }]);
  assert.equal(jobs.length, 2);
  assert.deepEqual(jobs.map(j=>j.kind), ['value','page']);
});

test('background scheduler skips busy watches and fills the budget fairly', async () => {
  const { nextEligibleWatchBatch, MAX_BACKGROUND_IN_FLIGHT } = await import('./watch.js');
  const jobs = [{id:'a'}, {id:'b'}, {id:'c'}, {id:'d'}, {id:'e'}];
  const busy = new Set(['a','c']);
  const one = nextEligibleWatchBatch(jobs, 0, (job) => busy.has(job.id), MAX_BACKGROUND_IN_FLIGHT);
  assert.deepEqual(one.jobs.map((job) => job.id), ['b','d']);
  assert.equal(one.next, 4);
  const two = nextEligibleWatchBatch(jobs, one.next, (job) => busy.has(job.id), 1);
  assert.deepEqual(two.jobs.map((job) => job.id), ['e']);
  assert.equal(two.next, 0);
});

test('background capacity exhausted sends nothing and preserves the cursor', async () => {
  const { nextEligibleWatchBatch } = await import('./watch.js');
  const jobs = [{id:'a'}, {id:'b'}, {id:'c'}];
  assert.deepEqual(nextEligibleWatchBatch(jobs, 2, () => false, 0),
    { jobs: [], next: 2 });
  assert.deepEqual(nextEligibleWatchBatch(jobs, 1, () => true, 2),
    { jobs: [], next: 1 });
  assert.deepEqual(nextEligibleWatchBatch([], 2, () => false, 2),
    { jobs: [], next: 0 });
});

test('fair polling selects all ready favourites and pages across multiple ticks', async () => {
  const { nextEligibleWatchBatch } = await import('./watch.js');
  const jobs = [{id:'favourite-a'}, {id:'page-a'}, {id:'favourite-b'}, {id:'page-b'}];
  const scheduled = [];
  let cursor = 0;
  for (let i = 0; i < 2; i += 1) {
    const batch = nextEligibleWatchBatch(jobs, cursor, () => false, 2);
    scheduled.push(...batch.jobs.map((job) => job.id));
    cursor = batch.next;
  }
  assert.deepEqual(scheduled, jobs.map((job) => job.id));
});
