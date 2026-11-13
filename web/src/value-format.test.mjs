import test from 'node:test';
import assert from 'node:assert/strict';
import { valuePresentation, fullValueTone } from './value-format.js';

test('classifies known builtins without executing or guessing game-defined types', () => {
  assert.equal(valuePresentation('dict').category, 'Mapping');
  assert.equal(valuePresentation('frozenset').category, 'Set');
  assert.equal(valuePresentation('unicode').tone, 'string');
  assert.equal(valuePresentation('bool').tone, 'boolean');
  assert.equal(valuePresentation('GameCustomObject').category, 'Object / other');
  assert.equal(valuePresentation('Anything', 'missing').category, 'Missing');
  assert.equal(fullValueTone('string'), 'string');
  assert.equal(fullValueTone('unsupported'), 'object');
});
