import React, { useEffect, useState } from 'react';
import { Button, Checkbox, Tag, Typography } from 'antd';
import { formatTypedPath } from './tree.js';

const { Text } = Typography;

function newerHistory(incoming, current) {
  if (!incoming) return false;
  if (!current) return true;
  const generation = incoming.generation ?? -1;
  const previousGeneration = current.generation ?? -1;
  if (generation !== previousGeneration) return generation > previousGeneration;
  return (incoming.revision ?? 0) >= (current.revision ?? 0);
}

const STATUS = {
  applied: { label: 'Applied', color: 'blue' },
  undone: { label: 'Undone', color: 'default' },
  conflicted: { label: 'Conflict', color: 'volcano' },
  superseded: { label: 'Redo discarded', color: 'default' },
};

/**
 * This is deliberately separate from Compare: these are explicit inspector
 * writes, not sampled game mutations. Undo/Redo each require a fresh click
 * after the user acknowledges that they write to the running game.
 */
export default function EditHistoryPane({
  value, generation, enabled, bridge, token,
}) {
  const [history, setHistory] = useState(value);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setHistory((current) => newerHistory(value, current) ? value : current);
  }, [value]);

  const run = async (action) => {
    const entryId = action === 'undo' ? history?.undo_entry_id : history?.redo_entry_id;
    if (!enabled || !token || !entryId || !confirmed || busy) return;
    setBusy(true); setError(''); setConfirmed(false);
    try {
      const response = await fetch(bridge + '/api/v1/edit-history', {
        method: 'PUT', mode: 'cors', cache: 'no-store',
        headers: { 'X-Inspector-Token': token, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action, generation: history?.generation ?? generation, entry_id: entryId,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (data.edit_history) {
        setHistory((current) => newerHistory(data.edit_history, current)
          ? data.edit_history : current);
      }
      if (!response.ok) {
        throw new Error(response.status === 409
          ? (data.error || 'Conflict: the recorded value or game generation changed.')
          : response.status === 423 ? 'This variable is locked against Inspector writes. Unlock it from the variable details before undoing or redoing.'
            : response.status === 403 ? 'Editing has been disabled by the game.'
              : response.status === 503
              ? 'The game may have completed this action. Refresh and inspect the current value before retrying.'
              : 'Undo/Redo failed (HTTP ' + response.status + ')');
      }
      if (!data.applied || !data.edit_history ||
          data.edit_history.generation <= (history?.generation ?? generation)) {
        throw new Error('The reversal was not confirmed. Refresh and inspect the current value.');
      }
    } catch (reason) {
      setError(reason.message || 'Undo/Redo failed.');
    } finally {
      setBusy(false);
    }
  };

  const entries = Array.isArray(history?.entries) ? [...history.entries].reverse() : [];
  const canUndo = enabled && Boolean(history?.can_undo && history?.undo_entry_id);
  const canRedo = enabled && Boolean(history?.can_redo && history?.redo_entry_id);

  return <section className="edit-history-workspace" aria-label="Inspector edit history">
    <div className="edit-history-toolbar">
      <div className="edit-history-description">
        <Text strong>Explicit inspector edits</Text>
        <Text type="secondary">
          Session-only history · up to {history?.limit ?? 50} records · {history?.bytes_used ?? 0}
          / {history?.byte_limit ?? 65536} bytes. Game loads, rollback and other state resets
          discard reversal history. This is not Ren’Py rollback.
        </Text>
      </div>
      <div className="edit-history-actions">
        <Button size="small" disabled={!canUndo || busy || !confirmed}
          onClick={() => run('undo')}
          aria-label="Undo last inspector edit">Undo</Button>
        <Button size="small" disabled={!canRedo || busy || !confirmed}
          onClick={() => run('redo')} aria-label="Redo last inspector edit">Redo</Button>
        <Checkbox checked={confirmed} disabled={busy}
          onChange={(event) => setConfirmed(event.target.checked)}>
          I understand Undo/Redo writes to the running game
        </Checkbox>
      </div>
    </div>
    {error && <Text type="danger" role="alert">{error}</Text>}
    <div className="edit-history-list" role="region" aria-label="Explicit edit records">
      {entries.length ? entries.map((entry) => {
        const status = STATUS[entry.status] || STATUS.conflicted;
        return <article className="edit-history-entry" key={entry.id}>
          <div className="edit-history-entry-heading">
            <Text className="edit-history-path" title={formatTypedPath(entry.key)}>
              {formatTypedPath(entry.key) || 'Store variable'}
            </Text>
            <Tag>{entry.type}</Tag>
            <Tag color={status.color}>{status.label}</Tag>
          </div>
          <Text type="secondary" className="edit-history-time">
            Edit #{entry.id} · {new Date(entry.created_at * 1000).toLocaleTimeString()}
          </Text>
          <div className="edit-history-values">
            <div><Text type="secondary">Before</Text>
              <pre>{entry.before}</pre></div>
            <div><Text type="secondary">After</Text>
              <pre>{entry.after}</pre></div>
          </div>
        </article>;
      }) : <div className="edit-history-empty">
        <Text type="secondary">No explicit edits in this bridge session.</Text>
      </div>}
    </div>
  </section>;
}
