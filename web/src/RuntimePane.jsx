import React, { useMemo, useState } from 'react';
import { Button, Empty, Select, Tag, Typography } from 'antd';
import { sourceTargetForContext } from './scripts.js';
import { filteredRuntimeEvents, runtimeEventDescription } from './runtime-history.js';

const { Text, Title } = Typography;

function sampledTime(timestamp) {
  return Number.isFinite(timestamp) ? new Date(timestamp * 1000).toLocaleTimeString() : 'Time unavailable';
}

export default function RuntimePane({ snapshot, onOpenSource }) {
  const [filter, setFilter] = useState('all');
  const game = snapshot?.game ?? {};
  const timeline = snapshot?.runtime ?? {};
  const events = useMemo(() => filteredRuntimeEvents(timeline, filter), [timeline, filter]);
  // Existing bridge snapshots encode numeric context metadata as short text.
  const line = Number(game.line);
  const returnDepth = Number(game.return_depth);
  const location = typeof game.filename === 'string' && Number.isSafeInteger(line) && line > 0
    ? `${game.filename}:${line}` : 'Not available';
  const rollback = typeof game.rollback_active === 'boolean'
    ? game.rollback_active ? 'True at latest sample' : 'False at latest sample'
    : 'Not exposed by this engine';

  return <section className="runtime-workspace" aria-label="Runtime and restoration history">
    <div className="runtime-summary">
      <Title level={4}>Runtime &amp; rollback context</Title>
      <Text type="secondary">Read-only Ren'Py engine observations, not SugarCube turns or a complete interaction log.</Text>
      <div className="runtime-summary-grid">
        <div><Text type="secondary">Current sampled statement</Text><Text className="runtime-mono">{location}</Text></div>
        <div><Text type="secondary">Return destinations</Text><Text>{game.return_depth != null && Number.isSafeInteger(returnDepth) && returnDepth >= 0 ? `${returnDepth} on stack` : 'Unavailable'}</Text></div>
        <div><Text type="secondary">Rollback indicator</Text><Text>{rollback}</Text></div>
        <div><Text type="secondary">Last snapshot</Text><Text>{sampledTime(snapshot?.captured_at)}</Text></div>
      </div>
      {sourceTargetForContext(game) && <Button size="small" className="runtime-source-link"
        onClick={() => onOpenSource(game)}>View current in Scripts</Button>}
      <Text type="secondary" className="runtime-disclaimer">
        Return destinations are not the Python call stack. A false or unavailable rollback indicator
        does not prove no rollback happened between samples. Restorations reset variable Compare
        history, but this bounded session timeline retains callback evidence.
      </Text>
    </div>
    <div className="runtime-history-header">
      <div><Text strong>Observed timeline</Text><Text type="secondary">
        {Array.isArray(timeline.events) ? ` Last ${timeline.limit || 64} entries, ${timeline.total_observed || 0} recorded this bridge session` :
          ' Waiting for the first capture'}
      </Text></div>
      <Select aria-label="Filter runtime observations" size="small" value={filter} onChange={setFilter}
        options={[
          { value: 'all', label: 'All observations' },
          { value: 'location', label: 'Script locations' },
          { value: 'restoration', label: 'Restoration signals' },
          { value: 'invalidation', label: 'Inspector invalidations' },
          { value: 'rollback_flag', label: 'Rollback indicators' },
        ]} />
    </div>
    <div className="runtime-history-list" role="region" aria-label="Observed runtime timeline">
      {events.length ? events.map((entry) => {
        const description = runtimeEventDescription(entry);
        return <article className="runtime-event" key={entry.id}>
          <div className="runtime-event-header">
            <Text strong>{description.title}</Text>
            <Tag>{entry.kind === 'location' ? 'sample' : entry.kind === 'restoration' ? 'callback' :
              entry.kind === 'invalidation' ? 'reset' : 'indicator'}</Tag>
            <Text type="secondary">{sampledTime(entry.captured_at)} · epoch {entry.generation}</Text>
          </div>
          <Text className="runtime-mono">{description.detail}</Text>
          {entry.kind === "location" && sourceTargetForContext(entry) &&
            <Button size="small" type="link" className="runtime-source-link"
              aria-label={`View source for ${entry.filename}:${entry.line}`}
              onClick={() => onOpenSource(entry)}>View in Scripts</Button>}
          <Text type="secondary">{description.note}</Text>
        </article>;
      }) : <Empty description={filter === 'all'
        ? 'No engine observations captured yet.'
        : 'No observations of this type in the retained timeline.'} />}
    </div>
  </section>;
}
