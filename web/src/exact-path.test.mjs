import test from 'node:test';
import assert from 'node:assert/strict';
import { parseExactPath } from './exact-path.js';
import { formatTypedPath } from './tree.js';

const exact = (input) => {
  const result = parseExactPath(input);
  assert.ok(result && !result.error, input + ': ' + result?.error);
  assert.deepEqual(JSON.parse(result.key), [result.scope, result.path]);
  return result;
};

test('dotted object attributes and quoted dictionary keys are different typed paths', () => {
  assert.deepEqual(exact('store.player.stats["hp"]').path, [
    ['attribute', 'player'], ['attribute', 'stats'], ['key', 'hp'],
  ]);
  assert.deepEqual(exact('store.player["stats"][0]["health points"]').path, [
    ['attribute', 'player'], ['key', 'stats'], ['index', 0], ['key', 'health points'],
  ]);
  assert.deepEqual(exact('persistent.flags["seen"]').path, [
    ['attribute', 'flags'], ['key', 'seen'],
  ]);
  assert.deepEqual(exact('persistent["flag"]').path, [['key', 'flag']]);
  assert.deepEqual(exact('store["player"]').path, [['attribute', 'player']]);
});

test('dict keys support booleans, None, integer-key disambiguation and safe quotes', () => {
  assert.deepEqual(exact('store.player[True][None][key:42][key:-3]').path, [
    ['attribute', 'player'], ['key', true], ['key', null], ['key', 42], ['key', -3],
  ]);
  assert.deepEqual(exact("store.player['single\\'quoted']").path, [
    ['attribute', 'player'], ['key', "single'quoted"],
  ]);
  assert.deepEqual(exact('store.player["escaped \\"quote\\" and \\u2603"]').path, [
    ['attribute', 'player'], ['key', 'escaped "quote" and ☃'],
  ]);
  assert.deepEqual(exact('store.player[42]').path.at(-1), ['index', 42]);
});

test('Copy Path can be pasted back exactly, including Unicode and numeric dict keys', () => {
  const samples = [
    ['store', [['attribute', 'player'], ['key', 'unicode ☃'], ['index', 3]]],
    ['persistent', [['attribute', 'flags'], ['key', false], ['key', 0], ['key', null]]],
    ['store', [['attribute', 'player'], ['key', 'has \\ and "quotes"']]],
    ['store', [['attribute', 'weird'], ['key', '\n']]],
  ];
  for (const sample of samples) {
    const path = formatTypedPath(JSON.stringify(sample));
    assert.ok(path);
    assert.deepEqual([exact(path).scope, exact(path).path], sample, path);
  }
});

test('normal words use global fuzzy search rather than exact-path navigation', () => {
  for (const value of ['', 'player', 'hp', '$player', '_temp', 'script', 'stored.player']) {
    assert.equal(parseExactPath(value), null, value);
  }
});

test('invalid private, executable, huge or malformed input is rejected without evaluating it', () => {
  const invalid = [
    'store', 'persistent', 'store.__dict__', 'store._private',
    'store.player()', 'store.player[__import__("os")]',
    'store.player["unterminated]', 'store.player["bad" extra]',
    'store.player[1+1]', 'store.player[-1]', 'store.player[1000001]',
    'store.player[key:9007199254740992]',
    'store.player["a"]extra', 'store.player..score',
    'store.player["\\uNOTHEX"]', 'store.player["a\nb"]',
    'store.' + Array(10).fill('level').join('.'),
    'store.player["' + 'x'.repeat(257) + '"]',
    'store.' + 'x'.repeat(2050),
  ];
  for (const input of invalid) {
    const result = parseExactPath(input);
    assert.ok(result && result.error, input);
    assert.equal(result.key, null, input);
  }
});
