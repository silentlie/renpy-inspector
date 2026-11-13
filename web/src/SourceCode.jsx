import React, { useMemo } from 'react';
import { highlightSourceExcerpt } from './source-highlight.js';

/** Escape through React text nodes; deliberately never use innerHTML. */
export default function SourceCode({ lines }) {
  const highlighted = useMemo(() => highlightSourceExcerpt(lines), [lines]);
  return <div className="script-source-lines" role="list">
    {highlighted.map((entry) =>
      <div key={entry.line} className={'script-source-line' +
        (entry.line === lines?.find((item) => item.line === lines?.sourceLine) ? ' script-source-active' : '')}
        role="listitem">
        <span className="script-source-number">{entry.line}</span>
        <code>{entry.tokens.map((segment, index) =>
          <span key={index} className={`source-token-${segment.kind}`}>{segment.text}</span>)}</code>
      </div>)}
  </div>;
}
