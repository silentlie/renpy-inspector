/**
 * A deliberately small, presentation-only lexer for *captured* Python value
 * previews. It never interprets Python, invokes runtime values or changes
 * observation cadence. Exact string samples are NOT Python expressions.
 *
 * Full values remain plain literal text in FullValuePanel. Short previews and
 * history samples are already bounded by the bridge; the extra browser cap
 * protects rendering if a malformed/hostile preview reaches the UI.
 */
export const MAX_VALUE_SYNTAX_CHARS = 1024;
export const MAX_VALUE_SYNTAX_TOKENS = 96;

const STRINGS = new Set(['str', 'unicode', 'bytes']);
const NUMBERS = new Set(['int', 'long', 'float', 'complex']);
const CONTAINERS = new Set(['list', 'tuple', 'dict', 'set', 'frozenset',
  'defaultdict', 'OrderedDict', 'range']);
const BUILTINS = new Set(['list', 'tuple', 'dict', 'set', 'frozenset',
  'defaultdict', 'OrderedDict', 'range', 'bytes', 'bytearray']);
const NUMBER = /^(?:[+-]?(?:0[xX][\da-fA-F]+|0[oO][0-7]+|0[bB][01]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)[jJlL]?)/;
const COMPLETE_NUMBER = /^[+-]?(?:0[xX][\da-fA-F]+|0[oO][0-7]+|0[bB][01]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)[jJlL]?$/;
const NAME = /^[A-Za-z_][A-Za-z_\d]*/;
const WORD = /[\w]/;
const PUNCTUATION = new Set(['[', ']', '(', ')', '{', '}', ':', ',']);

function plain(text) { return [{ kind: 'plain', text }]; }

function one(kind, text) { return [{ kind, text }]; }

function prefixLength(text, at) {
  // Python repr uses at most a two-letter prefix (u, b, r, br, rb).
  const match = /^[bBuUrR]{1,2}(?=['"])/.exec(text.slice(at, at + 3));
  if (!match) return 0;
  if (at > 0 && WORD.test(text[at - 1])) return 0;
  return match[0].length;
}

function scanString(text, at) {
  const prefix = prefixLength(text, at);
  const quote = text[at + prefix];
  if (quote !== "'" && quote !== '"') return 0;
  let pos = at + prefix + 1;
  while (pos < text.length) {
    if (text[pos] === '\\') {
      pos += Math.min(2, text.length - pos);
    } else if (text[pos] === quote) {
      return pos + 1 - at;
    } else {
      pos++;
    }
  }
  // The source bridge may truncate a quoted repr mid-string.
  return text.length - at;
}

function lexicalPreview(text) {
  const result = [];
  function emit(kind, slice) {
    if (!slice) return;
    const last = result[result.length - 1];
    if (last?.kind === kind) last.text += slice;
    else result.push({ kind, text: slice });
  }
  for (let at = 0; at < text.length;) {
    if (result.length >= MAX_VALUE_SYNTAX_TOKENS) return plain(text);
    const length = scanString(text, at);
    if (length) {
      emit('string', text.slice(at, at + length));
      at += length;
      continue;
    }
    const boundary = at === 0 || !WORD.test(text[at - 1]);
    const number = boundary && NUMBER.exec(text.slice(at));
    if (number && !WORD.test(text[at + number[0].length] || '')) {
      emit('number', number[0]);
      at += number[0].length;
      continue;
    }
    const name = boundary && NAME.exec(text.slice(at));
    if (name) {
      const word = name[0];
      emit(word === 'True' || word === 'False' ? 'boolean' :
        word === 'None' ? 'null' :
          BUILTINS.has(word) ? 'builtin' : 'plain', word);
      at += word.length;
      continue;
    }
    emit(PUNCTUATION.has(text[at]) ? 'punctuation' : 'plain', text[at]);
    at++;
  }
  return result;
}

/**
 * source='preview': bounded captured Python-ish repr.
 * source='exact': captured scalar's raw text, NOT a Python literal.
 * A mismatch/unknown type is shown unchanged, never guessed.
 */
export function tokenizePythonValue(text, { type, source = 'preview', state = 'value' } = {}) {
  if (typeof text !== 'string') return plain('');
  if (!text || text.length > MAX_VALUE_SYNTAX_CHARS ||
      (state !== 'value' && state !== undefined)) return plain(text);

  if (STRINGS.has(type)) {
    // Even if an exact string contains "None", quotes or code, it is one string.
    if (source === 'exact') return one('string', text);
    const start = prefixLength(text, 0);
    return text[start] === "'" || text[start] === '"' ?
      one('string', text) : plain(text);
  }
  if (NUMBERS.has(type)) return COMPLETE_NUMBER.test(text) ?
    one('number', text) : plain(text);
  if (type === 'bool') return text === 'True' || text === 'False' ?
    one('boolean', text) : plain(text);
  if (type === 'NoneType') return text === 'None' ? one('null', text) : plain(text);

  // Other exact samples are not expressions. Unknown game types get no
  // parsing, regardless of how convincingly their preview resembles Python.
  if (source !== 'preview' || !CONTAINERS.has(type)) return plain(text);
  return lexicalPreview(text);
}
