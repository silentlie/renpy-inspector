import React, { useEffect, useMemo, useState } from 'react';
import { Button, Empty, Input, Spin, Tag, Typography } from 'antd';
import { CopyOutlined, SearchOutlined } from '@ant-design/icons';
import { appendScriptLabels, normaliseGameScriptFile, safeScriptLine } from './scripts.js';

const { Text, Title } = Typography;
const PAGE_SIZE = 40;

/** Read-only browser navigation over game-owned Ren'Py script metadata.
 * Selecting a source location never changes the game's execution point.
 */
export default function ScriptPane({ token, bridge, activeGame, generation }) {
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState({ query: '', offset: 0 });
  const [labels, setLabels] = useState([]);
  const [nextOffset, setNextOffset] = useState(0);
  const [more, setMore] = useState(false);
  const [limited, setLimited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [source, setSource] = useState(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [sourceError, setSourceError] = useState('');

  const currentFile = normaliseGameScriptFile(activeGame?.filename);
  const currentLine = safeScriptLine(activeGame?.line);
  const currentLocation = currentFile && currentLine ?
    { name: 'Current statement', file: currentFile, line: currentLine } : null;

  useEffect(() => {
    if (!token) return undefined;
    let active = true;
    const controller = new AbortController();
    setBusy(true);
    setError('');
    const timer = window.setTimeout(async () => {
      try {
        const args = new URLSearchParams({
          q: page.query, offset: String(page.offset), size: String(PAGE_SIZE),
        });
        const response = await fetch(bridge + '/api/v1/scripts?' + args, {
          headers: { 'X-Inspector-Token': token }, method: 'GET',
          mode: 'cors', cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) throw new Error(response.status === 503 ?
          'Game paused: resume to search scripts.' :
          response.status === 429 ? 'Request queue busy: retry.' :
          'Script index HTTP ' + response.status);
        const result = await response.json();
        if (!active || result.generation !== generation) return;
        setLabels((old) => page.offset ? appendScriptLabels(old, result.labels) :
          appendScriptLabels([], result.labels));
        setNextOffset(result.next_offset ?? 0);
        setMore(Boolean(result.more));
        setLimited(Boolean(result.limited));
      } catch (reason) {
        if (active && reason.name !== 'AbortError') setError(reason.message || 'Script index unavailable');
      } finally {
        if (active) setBusy(false);
      }
    }, page.offset ? 0 : 260);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [token, bridge, page.query, page.offset, generation]);

  useEffect(() => {
    if (!selected || !token) { setSource(null); return undefined; }
    let active = true;
    const controller = new AbortController();
    setSource(null);
    setSourceError('');
    setSourceBusy(true);
    const timer = window.setTimeout(async () => {
      try {
        const args = new URLSearchParams({ file: selected.file, line: String(selected.line) });
        const response = await fetch(bridge + '/api/v1/source?' + args, {
          headers: { 'X-Inspector-Token': token }, method: 'GET',
          mode: 'cors', cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) throw new Error(response.status === 503 ?
          'Game paused: resume to inspect source.' : 'Source HTTP ' + response.status);
        const data = await response.json();
        if (active && data.generation === generation && data.file === selected.file &&
            data.line === selected.line) setSource(data);
      } catch (reason) {
        if (active && reason.name !== 'AbortError') setSourceError(reason.message || 'Source unavailable');
      } finally {
        if (active) setSourceBusy(false);
      }
    }, 0);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [selected?.file, selected?.line, bridge, token, generation]);

  const filteredCount = useMemo(() => labels.length, [labels.length]);
  const openLocation = (entry) => {
    if (!entry || !normaliseGameScriptFile(entry.file) || !safeScriptLine(entry.line)) return;
    setSelected({ name: entry.name, file: entry.file, line: entry.line });
  };
  const changeFilter = (value) => {
    setFilter(value);
    setPage({ query: value, offset: 0 });
    setLabels([]);
    setMore(false);
  };

  return <section className="script-workspace" aria-label="Script navigation">
    <div className="script-navigation">
      <div className="script-navigation-header">
        <Text className="eyebrow">SCRIPT INDEX</Text>
        <Title level={4}>Scripts</Title>
        <Text type="secondary">Search labels and filenames. Navigation does not jump the running game.</Text>
        <Input prefix={<SearchOutlined />} allowClear size="middle"
          aria-label="Search script labels or filenames" placeholder="Find label or .rpy file"
          value={filter} maxLength={64}
          onChange={(event) => changeFilter(event.target.value)} />
        <div className="script-current">
          <Text type="secondary">Current: {activeGame?.filename || 'Unknown'}:{activeGame?.line || '?'}</Text>
          <Button size="small" disabled={!currentLocation}
            onClick={() => openLocation(currentLocation)}>View current</Button>
        </div>
        {activeGame?.return_depth !== undefined &&
          <Text type="secondary">Return stack: {activeGame.return_depth}
            {activeGame.return_labels ? ' · ' + activeGame.return_labels : ''}</Text>}
      </div>
      <div className="script-label-list" role="region" aria-label="Script labels">
        {labels.map((item) => <button type="button" className={
          'script-label-item' + (selected?.name === item.name ? ' script-label-active' : '')
        } key={item.name + item.file + item.line}
          onClick={() => openLocation(item)}>
          <span className="script-label-name">{item.name}</span>
          <span className="script-label-location">{item.file}:{item.line}</span>
        </button>)}
        {!busy && !labels.length && !error &&
          <Empty description="No script labels found within the index budget" />}
        {busy && <div className="script-progress"><Spin size="small"/> Loading labels…</div>}
        {error && <Text type="danger" role="alert">{error}</Text>}
        {limited && <Text type="secondary" className="script-budget-warning">
          Partial index: only the first 4,000 eligible labels are examined.
        </Text>}
        {more && <Button block size="small" disabled={busy || nextOffset > 3960}
          onClick={() => setPage((old) => ({ ...old, offset: nextOffset }))}>
          More labels
        </Button>}
        {!!filteredCount && <Text type="secondary" className="script-result-count">
          {filteredCount} listed
        </Text>}
      </div>
    </div>
    <div className="script-source-pane" role="region" aria-label="Script source context">
      {selected ? <>
        <div className="script-source-heading">
          <div className="script-source-heading-text">
            <Text strong>{selected.name}</Text>
            <Text type="secondary">{selected.file}:{selected.line}</Text>
          </div>
          <Button size="small" icon={<CopyOutlined />} onClick={() =>
            navigator.clipboard?.writeText(selected.file + ':' + selected.line).catch(() => {})}>
            Copy location
          </Button>
        </div>
        {sourceBusy && <div className="script-progress"><Spin size="small"/> Reading source…</div>}
        {sourceError && <Text type="danger" role="alert">{sourceError}</Text>}
        {source && !source.available && <div className="script-source-unavailable">
          <Tag color="gold">Source unavailable</Tag>
          <Text type="secondary">{source.reason || 'This game may contain only compiled .rpyc files.'}</Text>
        </div>}
        {source?.available && <div className="script-source-lines" role="list">
          {source.lines.map((entry) =>
            <div key={entry.line} className={'script-source-line' +
              (entry.line === source.line ? ' script-source-active' : '')} role="listitem">
              <span className="script-source-number">{entry.line}</span>
              <code>{entry.text}</code>
            </div>)}
        </div>}
      </> : <Empty className="script-source-empty"
        description="Choose a label or view the current statement to inspect its source location." />}
    </div>
  </section>;
}
