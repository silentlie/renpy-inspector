/** Best-effort, bounded lexical colouring for game-owned .rpy excerpts.
 * Not an interpreter, AST parser, HTML generator, or executable expression.
 * Excerpts are at most 21 lines and 240 characters per line on the bridge.
 */
const KEYWORDS = new Set([
  'label', 'menu', 'if', 'elif', 'else', 'while', 'for', 'in', 'return',
  'jump', 'call', 'scene', 'show', 'hide', 'with', 'python', 'init', 'default',
  'define', 'screen', 'image', 'transform', 'style', 'play', 'stop', 'queue',
  'voice', 'pause', 'pass', 'break', 'continue', 'and', 'or', 'not', 'is',
  'as', 'from', 'import', 'class', 'def', 'try', 'except', 'finally',
  'raise', 'lambda', 'yield', 'assert', 'del', 'global',
]);
const LITERALS = new Set(['True', 'False', 'None']);
const MAX_SOURCE_LENGTH = 240;
const MAX_TOKENS = 256;

function token(tokens, kind, text) {
  if (!text) return;
  const last = tokens[tokens.length - 1];
  if (last && last.kind === kind) last.text += text;
  else tokens.push({ kind, text });
}

function isWord(char) { return /[A-Za-z0-9_]/.test(char || ''); }
function isStart(char) { return /[A-Za-z_]/.test(char || ''); }
function isDigit(char) { return /[0-9]/.test(char || ''); }

/** Carries triple-quoted string state between adjacent excerpt lines. */
export function highlightSourceLine(input, previous = null) {
  const text = typeof input === 'string' ? input.slice(0, MAX_SOURCE_LENGTH) : '';
  const tokens = [];
  let i = 0;
  let quote = previous === "'''" || previous === '"""' ? previous : null;
  while (i < text.length && tokens.length < MAX_TOKENS) {
    if (quote || text[i] === '"' || text[i] === "'") {
      const start = i;
      if (!quote) {
        quote = text.slice(i, i + 3) === text[i].repeat(3) ?
          text[i].repeat(3) : text[i];
        i += quote.length;
      }
      let ended = false;
      while (i < text.length) {
        if (text[i] === '\\') { i = Math.min(text.length, i + 2); continue; }
        if (text.startsWith(quote, i)) {
          i += quote.length;
          ended = true;
          break;
        }
        i += 1;
      }
      token(tokens, 'string', text.slice(start, i));
      if (ended || quote.length === 1) quote = null;
      continue;
    }
    if (text[i] === '#') {
      token(tokens, 'comment', text.slice(i));
      i = text.length;
      continue;
    }
    if (isStart(text[i])) {
      const start = i++;
      while (i < text.length && isWord(text[i])) i++;
      const value = text.slice(start, i);
      token(tokens, LITERALS.has(value) ? 'literal' :
        KEYWORDS.has(value) ? 'keyword' : 'plain', value);
      continue;
    }
    if (isDigit(text[i]) && !isWord(text[i - 1])) {
      const match = /^(?:0[xX][\da-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(text.slice(i));
      if (match) {
        token(tokens, 'number', match[0]);
        i += match[0].length;
        continue;
      }
    }
    token(tokens, 'plain', text[i]);
    i++;
  }
  if (i < text.length) token(tokens, 'plain', text.slice(i));
  return { tokens, next: quote && quote.length === 3 ? quote : null };
}

export function highlightSourceExcerpt(lines) {
  let state = null;
  return (Array.isArray(lines) ? lines : []).slice(0, 21).map((item) => {
    const result = highlightSourceLine(item?.text, state);
    state = result.next;
    return { line: item?.line, tokens: result.tokens };
  });
}
