import test from 'node:test';
import assert from 'node:assert/strict';
import { runtimeEventDescription, filteredRuntimeEvents } from './runtime-history.js';

test('default callback does not assert rollback or turns', () => {
  const item = runtimeEventDescription({ kind: 'restoration', signal: 'after_default' });
  assert.match(item.note, /rollback, startup or loading/);
  assert.doesNotMatch(item.title, /Rollback occurred/);
  assert.equal(runtimeEventDescription({ kind: 'restoration', signal: 'after_load' }).title,
    'After-load callback observed');
});

test('bounded timeline renders newest first without manufacturing interactions', () => {
  const events = Array.from({ length: 80 }, (_, index) => ({
    id: index + 1, kind: index % 2 ? 'location' : 'restoration',
    signal: 'unspecified', filename: 'game/a.rpy', line: index + 1,
  }));
  assert.equal(filteredRuntimeEvents({ events }).length, 64);
  assert.equal(filteredRuntimeEvents({ events })[0].id, 80);
  assert.equal(filteredRuntimeEvents({ events }, 'location').length, 40);
  assert.deepEqual(filteredRuntimeEvents({ events: [{ kind: 'something_else' }] }), []);
});
