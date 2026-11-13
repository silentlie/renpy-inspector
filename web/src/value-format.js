/** Presentation only. These are bridge-supplied labels, NOT runtime Python types. */
const known = Object.freeze({
  str: ['Text', 'Exact text is available on demand for built-in strings.'],
  unicode: ['Text', 'Unicode text is available on demand when safe.'],
  bytes: ['Text', 'Byte-string previews may not represent decodable Unicode.'],
  int: ['Integer', 'A numeric preview, not an editable Python value.'],
  long: ['Integer', 'Python 2 long integer; conversion remains bounded.'],
  float: ['Number', 'A finite or special floating-point representation.'],
  bool: ['Boolean', 'Python True or False.'],
  NoneType: ['Null', 'Python None.'],
  dict: ['Mapping', 'Expand to inspect visible keys within pagination limits.'],
  list: ['Sequence', 'Expand to inspect indexed entries.'],
  tuple: ['Sequence', 'Expand to inspect indexed entries (immutable container).'],
  set: ['Set', 'Expandable safe scalar members; unsupported members are omitted.'],
  frozenset: ['Set', 'Immutable set; only stable safe scalar members are visible.'],
  module: ['Namespace', 'Only supported visible attributes are inspectable.'],
});
const numeric = new Set(['int', 'long', 'float', 'complex']);
const strings = new Set(['str', 'unicode', 'bytes']);
const sequences = new Set(['list', 'tuple', 'range']);
const mappings = new Set(['dict', 'defaultdict', 'OrderedDict']);
const sets = new Set(['set', 'frozenset']);

export function valuePresentation(type, state = 'value') {
  const label = typeof type === 'string' ? type.slice(0, 80) : '';
  if (state === 'missing') return { category: 'Missing', tone: 'muted', detail: 'Path missing from the current game state.' };
  if (state === 'error') return { category: 'Unavailable', tone: 'muted', detail: 'The inspector could not read this value.' };
  const category = known[label]?.[0] ||
    (strings.has(label) ? 'Text' : numeric.has(label) ? 'Number' :
      sequences.has(label) ? 'Sequence' : mappings.has(label) ? 'Mapping' :
        sets.has(label) ? 'Set' : 'Object / other');
  const tone = strings.has(label) ? 'string' :
    numeric.has(label) ? 'number' : label === 'bool' ? 'boolean' :
      label === 'NoneType' ? 'null' : 'object';
  return {
    category, tone,
    detail: known[label]?.[1] ||
      'Only a bounded preview is available; nested values require safe explicit inspection.',
  };
}

/** A full-value string is literal text, not Python source. Never re-interpret it. */
export function fullValueTone(kind) {
  return ({ string: 'string', number: 'number', boolean: 'boolean', null: 'null' })[kind] || 'object';
}
