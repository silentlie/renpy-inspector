import React, { useMemo, useState } from 'react';
import { Button, Empty, Input, Select, Tag, Typography } from 'antd';
import { comparisonText, filterChanges, MAX_FAVOURITE_CHANGES,
  MAX_FAVOURITE_CHANGES_PER_PATH } from './comparison.js';
import { formatTypedPath } from './tree.js';
import { sourceTargetForContext } from './scripts.js';
import { valuePresentation } from './value-format.js';

const { Text } = Typography;

/**
 * History is browser-session only, based on the existing Compare/watch samples.
 * Unlike Compare's pinned-only filter, this has independent bounded retention
 * and records a new baseline after pinning. It never requests more game data.
 */
export default function FavouriteHistoryPane({
  favourites, changes, baselineKeys, focusKey, onFocusChange, onClear,
  onInspect, onReveal, onOpenSource,
}) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const [navigationError, setNavigationError] = useState('');
  const pins = favourites ?? [];
  const events = changes ?? [];
  const known = new Set(pins.map((pin) => pin.key));
  const selectedKey = focusKey && known.has(focusKey) ? focusKey : 'all';
  const counts = useMemo(() => {
    const result = new Map();
    for (const event of events) result.set(event.key, (result.get(event.key) ?? 0) + 1);
    return result;
  }, [events]);
  const filtered = useMemo(() => filterChanges(events, {
    query, kind, focusKey: selectedKey === 'all' ? null : selectedKey,
  }), [events, query, kind, selectedKey]);
  const observedCount = pins.filter((pin) => (baselineKeys ?? []).includes(pin.key)).length;
  const options = [{ value: 'all', label: 'All pinned paths (' + pins.length + ')' },
    ...pins.map((pin) => ({ value: pin.key,
      label: (formatTypedPath(pin.key) || pin.key) + ' (' + (counts.get(pin.key) ?? 0) + ')' }))];
  const reveal = async (event) => {
    setNavigationError('');
    const success = await onReveal(event);
    if (!success) setNavigationError(
      'The path is not visible in this game state. Its captured history remains available.');
  };

  return <section className="pin-history-workspace" aria-label="Favourite change history">
    <div className="pin-history-toolbar">
      <Text type="secondary" className="pin-history-description">
        Observed changes only after each path is pinned and its first sample is captured.
        Up to {MAX_FAVOURITE_CHANGES} session events, {MAX_FAVOURITE_CHANGES_PER_PATH} per pinned path.
        This is not a complete mutation or rollback log; source locations show where
        sampling happened, not what caused a change.
      </Text>
      <div className="pin-history-controls">
        <Select size="small" value={selectedKey} onChange={(next) => {
          onFocusChange(next === 'all' ? null : next);
          setNavigationError('');
        }} options={options} aria-label="Choose pinned variable history"
          className="pin-history-select" showSearch optionFilterProp="label" />
        <Input size="small" allowClear maxLength={160} placeholder="Filter history paths"
          value={query} onChange={(event) => setQuery(event.target.value)}
          aria-label="Filter pinned history paths" className="pin-history-filter" />
        <Select size="small" value={kind} onChange={setKind}
          aria-label="Filter pinned history event kind" options={[
            { value: 'all', label: 'All changes' },
            { value: 'changed', label: 'Changed' },
            { value: 'added', label: 'Added' },
            { value: 'removed', label: 'Removed' },
          ]} />
        <Button size="small" onClick={onClear} disabled={!events.length}
          aria-label="Clear pinned history">Clear history</Button>
      </div>
      <Text type="secondary" className="pin-history-count" aria-live="polite">
        {filtered.length} of {events.length} observations ·
        {' '}{observedCount} / {pins.length} pins have a captured baseline
      </Text>
      {navigationError && <Text type="danger" role="alert">{navigationError}</Text>}
    </div>
    <div className="pin-history-list" role="region" aria-label="Pinned change observations">
      {filtered.length ? filtered.map((event) =>
        <article className="pin-history-entry" key={event.id}>
          <div className="pin-history-entry-title">
            <Text className="pin-history-path">{event.path}</Text>
            <Tag>{event.scope}</Tag>
            <Tag color={event.kind === 'added' ? 'green' :
              event.kind === 'removed' ? 'volcano' : 'blue'}>{event.kind}</Tag>
          </div>
          <Text type="secondary" className="pin-history-context">
            Sampled {new Date(event.capturedAt * 1000).toLocaleTimeString()}
            {event.context.filename ? ' · ' + event.context.filename : ''}
            {event.context.line !== null ? ':' + event.context.line : ''}
          </Text>
          <div className="pin-history-values">
            {[['Before', event.before], ['After', event.after]].map(([label, value]) =>
              <div key={label}>
                <Text type="secondary">{label} · {value.precision === 'exact'
                  ? 'exact sampled primitive' : 'preview/status'}</Text>
                <pre className={'pin-history-sample value-tone-' +
                  valuePresentation(value.type, value.kind).tone}>{comparisonText(value)}</pre>
              </div>)}
          </div>
          <div className="pin-history-actions">
            <Button size="small" type="link" onClick={() => onInspect(event)}>
              Inspect variable</Button>
            <Button size="small" type="link" onClick={() => reveal(event)}>
              Reveal in tree</Button>
            {sourceTargetForContext(event.context) && <Button size="small" type="link"
              aria-label="View pinned sample source"
              title="Sampled location, not proof of a mutation cause"
              onClick={() => onOpenSource(event.context)}>View sampled source</Button>}
          </div>
        </article>) : <Empty className="pin-history-empty"
          description={!pins.length
            ? 'Pin a Store or Persistent value to start monitoring its changes.'
            : events.length
              ? 'No pinned observations match these filters.'
              : observedCount < pins.length
                ? 'Waiting for the first sample of each pinned variable. No earlier history is reconstructed.'
                : 'No changes observed since pinning. Game scripts may change values between samples.'} />}
    </div>
  </section>;
}
