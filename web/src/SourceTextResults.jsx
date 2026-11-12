import React, { useEffect, useState } from 'react';
import { Button, Empty, Spin, Tag, Typography } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { normaliseGameScriptFile, safeScriptLine } from './scripts.js';

const { Text } = Typography;
const PAGE_SIZE = 20;

function safeResults(data) {
  return (Array.isArray(data) ? data : []).filter((entry) =>
    entry && normaliseGameScriptFile(entry.file) === entry.file &&
    safeScriptLine(entry.line) !== null && typeof entry.text === 'string' &&
    entry.text.length <= 250).slice(0, PAGE_SIZE);
}

/** Literal text search across game-owned .rpy files, never runtime evaluation.
 * The bridge scans a small bounded chunk per interaction-thread request and
 * returns an opaque continuation cursor (not a file path).
 */
export default function SourceTextResults({ token, bridge, generation, query, onOpen }) {
  const term = query.trim();
  const [page, setPage] = useState({ term: '', cursor: '0:0' });
  const [matches, setMatches] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [more, setMore] = useState(false);
  const [limited, setLimited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [available, setAvailable] = useState(true);
  const [scanned, setScanned] = useState(0);

  useEffect(() => {
    setPage({ term, cursor: '0:0' });
    setMatches([]);
    setNextCursor(null);
    setMore(false);
    setLimited(false);
    setAvailable(true);
    setScanned(0);
    setError('');
  }, [term, generation]);

  useEffect(() => {
    if (!token || term.length < 2 || page.term !== term) return undefined;
    let active = true;
    const controller = new AbortController();
    setBusy(true);
    setError('');
    const timer = window.setTimeout(async () => {
      try {
        const params = new URLSearchParams({
          q: page.term, cursor: page.cursor, size: String(PAGE_SIZE),
        });
        const response = await fetch(bridge + '/api/v1/source-search?' + params, {
          method: 'GET', mode: 'cors', cache: 'no-store',
          headers: { 'X-Inspector-Token': token }, signal: controller.signal,
        });
        if (!response.ok) throw new Error(response.status === 409
          ? 'Game state changed. Search again.'
          : response.status === 503 ? 'Game paused: resume to continue source search.'
            : response.status === 429 ? 'Inspector queue busy: retry.'
              : 'Source search HTTP ' + response.status);
        const data = await response.json();
        if (!active || data.generation !== generation || data.query !== page.term) return;
        const found = safeResults(data.matches);
        setMatches((old) => {
          const before = page.cursor === '0:0' ? [] : old;
          const seen = new Set(before.map((entry) => entry.file + ':' + entry.line));
          return [...before, ...found.filter((entry) => {
            const id = entry.file + ':' + entry.line;
            if (seen.has(id)) return false;
            seen.add(id);
            return true;
          })].slice(0, 200);
        });
        const validNext = typeof data.cursor === 'string' &&
          /^\d{1,8}:\d{1,8}$/.test(data.cursor) && data.cursor !== page.cursor;
        setNextCursor(data.more && validNext ? data.cursor : null);
        setMore(Boolean(data.more && validNext));
        setLimited((old) => old || Boolean(data.limited));
        setAvailable(Boolean(data.available));
        setScanned((old) => page.cursor === '0:0'
          ? Number(data.scanned_bytes || 0) : old + Number(data.scanned_bytes || 0));
      } catch (reason) {
        if (active && reason.name !== 'AbortError') {
          setError(reason.message || 'Source search failed');
        }
      } finally {
        if (active) setBusy(false);
      }
    }, page.cursor === '0:0' ? 300 : 0);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [token, bridge, generation, page.term, page.cursor, term]);

  if (term.length < 2) return <Empty description="Enter two or more characters to search .rpy source text." />;
  return <>
    <Text type="secondary" className="script-search-disclaimer">
      Literal, case-insensitive text matches in game-owned .rpy files only.
      Matches may be comments, strings or variable references, not semantic usage.
    </Text>
    {matches.map((entry) =>
      <button type="button" className="script-label-item script-text-hit"
        aria-label={'Open source match ' + entry.file + ':' + entry.line}
        key={entry.file + ':' + entry.line}
        onClick={() => onOpen({ name: 'Source match', file: entry.file, line: entry.line })}>
        <span className="script-label-name">{entry.file}:{entry.line}</span>
        <span className="script-text-snippet">{entry.text}</span>
      </button>)}
    {!busy && !error && !matches.length && available &&
      <Empty description={more ? 'No matches in this chunk. Continue searching.' :
        'No matching source text within the scanned files.'} />}
    {!available && <div className="script-source-unavailable">
      <Tag color="gold">Source unavailable</Tag>
      <Text type="secondary">No readable game-owned .rpy source files. The game may distribute only .rpyc.</Text>
    </div>}
    {busy && <div className="script-progress"><Spin size="small" /> Searching source…</div>}
    {error && <Text type="danger" role="alert">{error}</Text>}
    {limited && <Text type="secondary" className="script-budget-warning">
      Partial coverage: file count, file size, depth or read limits excluded some source.
    </Text>}
    {more && <Button block size="small" icon={<SearchOutlined />}
      disabled={busy || !nextCursor} onClick={() =>
        setPage((old) => ({ ...old, cursor: nextCursor }))}>
      Continue source search
    </Button>}
    {!!matches.length && <Text type="secondary" className="script-result-count">
      {matches.length} matching lines shown
    </Text>}
    {scanned > 0 && <Text type="secondary" className="script-result-count">
      {scanned.toLocaleString()} source bytes examined in this search
    </Text>}
  </>;
}
