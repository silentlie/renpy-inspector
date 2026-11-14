import test from 'node:test';
import assert from 'node:assert/strict';
import { MAX_VALUE_SYNTAX_CHARS, MAX_VALUE_SYNTAX_TOKENS,
  tokenizePythonValue } from './python-value-syntax.js';

const show = (text, options) => tokenizePythonValue(text, options);
const kinds = (tokens) => tokens.map((x) => x.kind);
const rejoin = (tokens) => tokens.map((x) => x.text).join('');

test('short captured Python scalar previews receive conservative token colours', () => {
  assert.deepEqual(kinds(show("'hello\\n'", { type: 'str' })), ['string']);
  assert.deepEqual(kinds(show('u"hello"', { type: 'unicode' })), ['string']);
  assert.deepEqual(kinds(show("b'bytes'", { type: 'bytes' })), ['string']);
  assert.deepEqual(kinds(show('-1.25e+5', { type: 'float' })), ['number']);
  assert.deepEqual(kinds(show('12L', { type: 'long' })), ['number']);
  assert.deepEqual(kinds(show('0xFF', { type: 'int' })), ['number']);
  assert.deepEqual(kinds(show('True', { type: 'bool' })), ['boolean']);
  assert.deepEqual(kinds(show('False', { type: 'bool' })), ['boolean']);
  assert.deepEqual(kinds(show('None', { type: 'NoneType' })), ['null']);
  assert.deepEqual(kinds(show('nonsense', { type: 'float' })), ['plain']);
});

test('exact string samples are never parsed as Python code or markup', () => {
  for (const text of ['True', 'None', '42', 'dict(3)', '<img src=x onerror=alert(1)>',
    'a: [False]', "print('fake')", "u'not code'"]) {
    const t = show(text, { type: 'unicode', source: 'exact' });
    assert.deepEqual(t, [{ kind: 'string', text }]);
  }
  assert.deepEqual(show('True', { type: 'str', source: 'preview' }),
    [{ kind: 'plain', text: 'True' }]); // repr absent: refuse to guess
});

test('nested built-in previews keep exact original text and quote boundaries', () => {
  const source = String.raw`dict({'name': "a: True", 'hp': -4.2e+3, 'alive': False, 'unset': None})`;
  const t = show(source, { type: 'dict', source: 'preview' });
  assert.equal(rejoin(t), source);
  assert.ok(t.some((x) => x.kind === 'builtin' && x.text === 'dict'));
  assert.ok(t.some((x) => x.kind === 'string' && x.text === '"a: True"'));
  assert.ok(t.some((x) => x.kind === 'number' && x.text === '-4.2e+3'));
  assert.ok(t.some((x) => x.kind === 'boolean' && x.text === 'False'));
  assert.ok(t.some((x) => x.kind === 'null' && x.text === 'None'));
  assert.ok(t.some((x) => x.kind === 'punctuation'));
});

test('escaped quotes and truncated reprs never lose text or retokenize strings', () => {
  const source = String.raw`['abc\' True', "xyz\" False", u'cut-off…`;
  const t = show(source, { type: 'list' });
  assert.equal(rejoin(t), source);
  assert.equal(t.filter((x) => x.kind === 'boolean').length, 0);
  assert.ok(t.filter((x) => x.kind === 'string').length >= 2);
});

test('unknown objects, missing/error statuses and other exact samples remain literal', () => {
  const dangerous = '<script>alert(1)</script> True 123';
  for (const options of [
    { type: 'MyObject' }, { type: 'strangeType', source: 'preview' },
    { type: 'dict', source: 'exact' }, { type: 'dict', state: 'missing' },
    { type: 'dict', state: 'error' },
  ]) {
    assert.deepEqual(show(dangerous, options), [{ kind: 'plain', text: dangerous }]);
  }
  assert.deepEqual(show('Missing', { type: 'missing', state: 'missing' }),
    [{ kind: 'plain', text: 'Missing' }]);
});

test('bounded fallback renders input intact for oversized or overly fragmented samples', () => {
  const oversized = "'".repeat(MAX_VALUE_SYNTAX_CHARS + 1);
  assert.deepEqual(show(oversized, { type: 'list' }), [{ kind: 'plain', text: oversized }]);
  const many = Array.from({ length: MAX_VALUE_SYNTAX_TOKENS + 30 },
    (_, n) => n % 2 ? ',' : 'True').join('');
  assert.deepEqual(show(many, { type: 'list' }), [{ kind: 'plain', text: many }]);
});

test('captured content is not mutated for unsupported or malformed values', () => {
  for (const value of ['{<img src=x>}', '\u0000\t<&"\\', '', 'dict([1])', '1notanumber']) {
    for (const type of ['str', 'int', 'bool', 'list', 'Unknown']) {
      const t = show(value, { type });
      assert.equal(rejoin(t), value);
      assert.ok(t.length <= MAX_VALUE_SYNTAX_TOKENS + 1);
      assert.ok(t.every((x) => ['plain', 'string', 'number', 'boolean',
        'null', 'builtin', 'punctuation'].includes(x.kind)));
    }
  }
});
