import test from 'node:test';
import assert from 'node:assert/strict';
import { applyFavouriteAction, applyFavouriteActions, commitFavouriteAction,
  readFavouriteSnapshot, sameFavourites } from './favourites-sync.js';

const pin = (scope, name) => ({
  scope, key: JSON.stringify([scope, [['attribute', name]]]),
});
const score = pin('store', 'score');
const memo = pin('store', 'memo');
const flag = pin('persistent', 'flag');
const snapshot = (revision, favourites, initialized = true) =>
  ({ version: 1, revision, initialized, favourites });

test('pinned/unpinned actions are idempotent and bounded, without mutating input', () => {
  const initial = [score];
  assert.deepEqual(applyFavouriteAction(initial, { kind: 'pin', entry: score }), [score]);
  assert.deepEqual(applyFavouriteAction(initial, { kind: 'pin', entry: memo }), [score, memo]);
  assert.deepEqual(applyFavouriteAction(initial, { kind: 'unpin', entry: memo }), [score]);
  assert.deepEqual(initial, [score]);
  assert.equal(applyFavouriteAction(Array(100).fill(score), { kind: 'pin', entry: memo }).length, 2);
  assert.deepEqual(applyFavouriteActions([score], [
    { kind: 'unpin', entry: score }, { kind: 'pin', entry: memo },
  ]), [memo]);
});

test('Clear All removes the confirmed paths without deleting concurrently added pins', () => {
  const change = { kind: 'clear', entries: [score, memo] };
  assert.deepEqual(applyFavouriteAction([score, memo, flag], change), [flag]);
  assert.deepEqual(applyFavouriteAction([flag], change), [flag]);
});

test('reject malformed server versions, revisions and untrusted paths', () => {
  assert.deepEqual(readFavouriteSnapshot(snapshot(0, [], false)).favourites, []);
  for (const invalid of [
    snapshot(-1, []), snapshot(Number.MAX_SAFE_INTEGER + 1, []),
    { ...snapshot(0, []), revision: true }, snapshot(0, [{ scope: 'store', key: 'bad' }]),
    { ...snapshot(0, []), version: 2 },
  ]) {
    assert.throws(() => readFavouriteSnapshot(invalid));
  }
});

test('409 conflict rebases an unrelated pin instead of overwriting the other tab', async () => {
  let server = snapshot(3, [score]);
  const requests = [];
  const save = async (revision, favourites) => {
    requests.push({ revision, favourites });
    if (server.revision !== revision) return { status: 409, data: server };
    server = snapshot(revision + 1, favourites);
    return { status: 200, data: server };
  };
  const result = await commitFavouriteAction(snapshot(2, []),
    { kind: 'pin', entry: memo }, save);
  assert.equal(requests.length, 2);
  assert.deepEqual(result.favourites, [score, memo]);
  assert.deepEqual(server.favourites, [score, memo]);
  assert.equal(result.revision, 4);
});

test('a stale Clear All preserves a pin added concurrently', async () => {
  let server = snapshot(5, [score, memo, flag]);
  const save = async (revision, favourites) => {
    if (server.revision !== revision) return { status: 409, data: server };
    server = snapshot(revision + 1, favourites);
    return { status: 200, data: server };
  };
  const result = await commitFavouriteAction(snapshot(4, [score, memo]),
    { kind: 'clear', entries: [score, memo] }, save);
  assert.deepEqual(result.favourites, [flag]);
});

test('no-op actions do not write or advance the revision', async () => {
  const current = snapshot(7, [score]);
  let called = false;
  const result = await commitFavouriteAction(current, { kind: 'pin', entry: score },
    async () => { called = true; });
  assert.equal(called, false);
  assert.equal(result, current);
  assert.ok(sameFavourites(result.favourites, [score]));
});

test('conflicts have bounded retries and reject a stale conflict response', async () => {
  const base = snapshot(1, []);
  await assert.rejects(() => commitFavouriteAction(base, { kind: 'pin', entry: score },
    async () => ({ status: 409, data: base })), /Stale preferences/);
  let revision = 1;
  let tries = 0;
  await assert.rejects(() => commitFavouriteAction(base, { kind: 'pin', entry: score },
    async () => {
      tries += 1;
      return { status: 409, data: snapshot(++revision, []) };
    }, 3), /concurrently/);
  assert.equal(tries, 3);
});


test('non-ASCII typed pins use Python JSON identity for confirmation and unpin', async () => {
  const unescaped = pin('store', 'café');
  const bridgeKey = unescaped.key.replace('é', '\\u00e9');
  const canonical = { scope: 'store', key: bridgeKey };
  const emoji = pin('store', 'smile😀');
  const emojiBridge = emoji.key.replace('😀', '\\ud83d\\ude00');
  assert.deepEqual(applyFavouriteAction([], { kind: 'pin', entry: unescaped }), [canonical]);
  assert.deepEqual(applyFavouriteAction([], { kind: 'pin', entry: emoji }),
    [{ scope: 'store', key: emojiBridge }]);
  assert.deepEqual(applyFavouriteAction([canonical], { kind: 'unpin', entry: canonical }), []);

  let server = snapshot(0, []);
  let count = 0;
  const saved = await commitFavouriteAction(server, { kind: 'pin', entry: unescaped },
    async (revision, favourites) => {
      count += 1;
      assert.equal(revision, server.revision);
      assert.deepEqual(favourites, [canonical]);
      server = snapshot(revision + 1, [canonical]);
      return { status: 200, data: server };
    });
  assert.equal(count, 1);
  assert.deepEqual(saved.favourites, [canonical]);
  assert.deepEqual(readFavouriteSnapshot(saved).favourites, [canonical]);
});

test('favourite canonicalization rejects over-budget ASCII-expanded keys', async () => {
  const { safeFavourites } = await import('./tree.js');
  const valid = pin('store', 'é');
  const oversized = pin('store', 'é'.repeat(400));
  assert.deepEqual(safeFavourites([valid, oversized]), [
    { scope: 'store', key: valid.key.replace('é', '\\u00e9') },
  ]);
});
