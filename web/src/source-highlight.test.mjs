import test from 'node:test';
import assert from 'node:assert/strict';
import { highlightSourceLine, highlightSourceExcerpt } from './source-highlight.js';

test('source text remains exactly intact and never becomes executable markup', () => {
  const source = 'label start: # <img src=x onerror=alert(1)>';
  const { tokens } = highlightSourceLine(source);
  assert.equal(tokens.map(t => t.text).join(''), source);
  assert.equal(tokens[0].kind, 'keyword');
  assert.equal(tokens.at(-1).kind, 'comment');
});

test('strings containing hash marks and escaped quotes are not comments', () => {
  const s = '    "hello # \\"world\\"" # actual comment';
  const { tokens } = highlightSourceLine(s);
  assert.equal(tokens.map(t => t.text).join(''), s);
  assert.equal(tokens.filter(t => t.kind === 'comment').length, 1);
  assert.equal(tokens.filter(t => t.kind === 'string').length, 1);
});

test('multiline quotes carry lexical state; excerpts remain bounded', () => {
  const lines = [
    { line: 1, text: "'''Hello # intact" },
    { line: 2, text: "foo''' $ True" },
  ];
  const tokens = highlightSourceExcerpt(lines);
  assert.equal(tokens[0].tokens.at(-1).kind, 'string');
  assert.equal(tokens[1].tokens[0].kind, 'string');
  assert.ok(tokens[1].tokens.some(t => t.kind === 'literal'));
  assert.equal(highlightSourceLine('z'.repeat(400)).tokens.map(t => t.text).join('').length, 240);
  assert.equal(highlightSourceExcerpt(Array.from({length: 100}, () => ({line:1,text:'a'}))).length, 21);
});

test('recognises RenPy and Python keywords plus numeric literals', () => {
  const r = highlightSourceLine('default hp = 2.75');
  assert.ok(r.tokens.some(t => t.kind === 'keyword' && t.text === 'default'));
  assert.ok(r.tokens.some(t => t.kind === 'number' && t.text === '2.75'));
});
