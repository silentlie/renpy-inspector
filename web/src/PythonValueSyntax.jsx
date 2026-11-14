import React, { useMemo } from 'react';
import { tokenizePythonValue } from './python-value-syntax.js';

/** Inline-only coloured text. No HTML interpolation, eval, or bridge reads. */
export default function PythonValueSyntax({ text, type, source = 'preview', state = 'value' }) {
  const tokens = useMemo(
    () => tokenizePythonValue(text, { type, source, state }),
    [text, type, source, state],
  );
  if (tokens.length === 1 && tokens[0].kind === 'plain') return tokens[0].text;
  return tokens.map(({ kind, text: fragment }, index) =>
    <span key={index} className={'value-token-' + kind}>{fragment}</span>);
}
