/**
 * Parse an exact Ren'Py typed path without eval, Function, or server-side
 * Python expressions. null means normal fuzzy search should handle the query.
 *
 * Dot access identifies an object/module attribute. Quoted bracket access
 * identifies a dictionary key; numeric brackets identify a list index.
 * Numeric dictionary keys use [key:42] to avoid ambiguity with list indices.
 * Value-identified set/frozenset members use {"text"}, {42}, {True}, {None}.
 * Only store and persistent are supported (no SugarCube $/_ aliases).
 */
import { decodeTreeKey } from './tree.js';

const SCOPE = /^(store|persistent)(?=\.|\[|\{|$)/;
const IDENTIFIER = /^[A-Za-z][A-Za-z0-9_]*/;
const MAX_LENGTH = 2048;
const MAX_SEGMENTS = 8;
const MAX_KEY_LENGTH = 256;
const INT_LITERAL = /^-?(0|[1-9]\d*)$/;
const INDEX_LITERAL = /^(0|[1-9]\d*)$/;

function quoteValue(source, start) {
  const quote = source[start];
  let index = start + 1;
  let decoded = '';
  while (index < source.length) {
    const ch = source[index++];
    if (ch === quote) return { value: decoded, end: index };
    if (ch === '\n' || ch === '\r' || ch.charCodeAt(0) < 32) {
      return { error: 'Unescaped control character in dictionary key.' };
    }
    if (ch !== '\\') {
      decoded += ch;
      continue;
    }
    if (index >= source.length) return { error: 'Unfinished string escape.' };
    const esc = source[index++];
    if ('"\\/'.includes(esc) || esc === "'") {
      decoded += esc;
    } else if (esc === 'n') {
      decoded += '\n';
    } else if (esc === 'r') {
      decoded += '\r';
    } else if (esc === 't') {
      decoded += '\t';
    } else if (esc === 'b') {
      decoded += '\b';
    } else if (esc === 'f') {
      decoded += '\f';
    } else if (esc === 'u') {
      const digits = source.slice(index, index + 4);
      if (!/^[0-9a-fA-F]{4}$/.test(digits)) {
        return { error: 'Expected four hexadecimal digits after \\u.' };
      }
      decoded += String.fromCharCode(parseInt(digits, 16));
      index += 4;
    } else {
      return { error: 'Unsupported string escape: \\' + esc + '.' };
    }
    if (decoded.length > MAX_KEY_LENGTH) return { error: 'Dictionary key is too long (256 characters max).' };
  }
  return { error: 'Unterminated quoted dictionary key.' };
}

function invalid(error) {
  return { error, scope: null, path: null, key: null };
}

/** @returns {null | {scope: string|null, path: Array|null, key: string|null, error: string}} */
export function parseExactPath(query) {
  const input = String(query ?? '').trim();
  const scopeMatch = SCOPE.exec(input);
  if (!scopeMatch) return null; // Let normal global search handle plain names.
  if (input.length > MAX_LENGTH) return invalid('Path is too long (2,048 characters max).');

  const scope = scopeMatch[1];
  let pos = scope.length;
  const segments = [];
  if (pos === input.length) return invalid('Enter a variable after ' + scope + '.');

  while (pos < input.length) {
    if (segments.length >= MAX_SEGMENTS) return invalid('Path is too deep (8 segments max).');
    const char = input[pos];
    if (char === '.') {
      pos++;
      const match = IDENTIFIER.exec(input.slice(pos));
      if (!match) return invalid('Expected a public attribute after ".".');
      const name = match[0];
      if (name.length > MAX_KEY_LENGTH) return invalid('Attribute name is too long (256 characters max).');
      segments.push(['attribute', name]);
      pos += name.length;
    } else if (char === '[' || char === '{') {
      // Square brackets address array indexes/dictionary keys; curly braces
      // address a value-identified set member. Never use iteration positions.
      const member = char === '{';
      const closing = member ? '}' : ']';
      pos++;
      let kind, value;
      if (input[pos] === '"' || input[pos] === "'") {
        const quoted = quoteValue(input, pos);
        if (quoted.error) return invalid(quoted.error);
        value = quoted.value;
        kind = member ? 'member' :
          segments.length === 0 && scope === 'store' ? 'attribute' : 'key';
        pos = quoted.end;
      } else {
        const end = input.indexOf(closing, pos);
        if (end === -1) return invalid('Missing closing "' + closing + '".');
        const literal = input.slice(pos, end).trim();
        const explicitKey = !member && literal.startsWith('key:');
        const token = explicitKey ? literal.slice(4) : literal;
        if (token === 'True' || token === 'False' || token === 'None') {
          value = token === 'None' ? null : token === 'True';
          kind = member ? 'member' : 'key';
        } else if (INT_LITERAL.test(token) &&
          (member || explicitKey || INDEX_LITERAL.test(token))) {
          value = Number(token);
          if (!Number.isSafeInteger(value) || (!member && !explicitKey && value > 1000000)) {
            return invalid('Index must be between 0 and 1,000,000; keys and members must be safe integers.');
          }
          kind = member ? 'member' : explicitKey ? 'key' : 'index';
        } else {
          return invalid(member
            ? 'Use {"member"}, {42}, {True} or {None}. Expressions are not supported.'
            : 'Use ["key"], [0], [True], [None] or [key:42]. Expressions are not supported.');
        }
        pos = end;
      }
      if (input[pos] !== closing) return invalid('Expected "' + closing + '" after the value.');
      pos++;
      if (kind === 'attribute' && (!value || value.startsWith('_'))) {
        return invalid('The Store root must use a public attribute name.');
      }
      if (typeof value === 'string' && value.length > MAX_KEY_LENGTH) {
        return invalid('Dictionary key or set member is too long (256 characters max).');
      }
      segments.push([kind, value]);
    } else {
      return invalid('Unexpected path syntax. Use .name, ["key"], [0] or {"member"}.');
    }
  }

  const key = JSON.stringify([scope, segments]);
  if (!decodeTreeKey(key)) return invalid('Path contains unsupported or private segments.');
  return { scope, path: segments, key, error: '' };
}
