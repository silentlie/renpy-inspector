import test from 'node:test';
import assert from 'node:assert/strict';
import { normaliseGameScriptFile, safeScriptLine, appendScriptLabels, sourceTargetForContext } from './scripts.js';

test('current location only permits game-relative RenPy source files', () => {
  assert.equal(normaliseGameScriptFile('game/script.rpy'), 'script.rpy');
  assert.equal(normaliseGameScriptFile('/project/game/chapters/intro.rpy'), 'chapters/intro.rpy');
  assert.equal(normaliseGameScriptFile('script.rpy'), 'script.rpy');
  assert.equal(normaliseGameScriptFile('../private.rpy'), '');
  assert.equal(normaliseGameScriptFile('game/../../private.rpy'), '');
  assert.equal(normaliseGameScriptFile('/etc/passwd'), '');
  assert.equal(normaliseGameScriptFile('script.rpyc'), '');
  assert.equal(safeScriptLine('12'), 12);
  assert.equal(safeScriptLine(100001), null);
  assert.equal(safeScriptLine(0), null);
});

test('paginated script labels retain stable order without duplicate rows', () => {
  const first = [{ name: 'start', file: 'script.rpy', line: 1 }];
  const second = [{ ...first[0] }, { name: 'chapters.intro', file: 'chapters/intro.rpy', line: 12 }];
  const merged = appendScriptLabels(first, second);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].name, 'start');
  assert.equal(merged[1].line, 12);
});

test('sampled source navigation validates relative paths and line bounds', () => {
  assert.deepEqual(sourceTargetForContext({ filename: 'game/script.rpy', line: '12' }),
    { file: 'script.rpy', line: 12 });
  assert.deepEqual(sourceTargetForContext({ file: 'chapter/scene.rpy', line: 5 }),
    { file: 'chapter/scene.rpy', line: 5 });
  assert.equal(sourceTargetForContext({ filename: '../private.rpy', line: 5 }), null);
  assert.equal(sourceTargetForContext({ filename: 'script.rpyc', line: 1 }), null);
  assert.equal(sourceTargetForContext({ filename: 'script.rpy', line: 999999 }), null);
});
