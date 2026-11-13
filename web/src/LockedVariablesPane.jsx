import React, { useMemo, useState } from 'react';
import { Alert, Button, Empty, Input, Popconfirm, Space, Tag, Typography } from 'antd';
import { EyeOutlined, LockOutlined, ReloadOutlined, UnlockOutlined } from '@ant-design/icons';
import { formatTypedPath } from './tree.js';

const { Text } = Typography;

function formatLockedAt(epoch) {
  if (!Number.isFinite(epoch)) return 'time unavailable';
  return new Date(epoch * 1000).toLocaleString();
}

function staleDescription(reason) {
  if (reason === 'type_changed') return 'The game changed this variable type after it was locked.';
  if (reason === 'target_unavailable') return 'This path no longer resolves to a supported primitive.';
  return 'The game changed this variable value after it was locked.';
}

/**
 * Session-only lock management. Every mutation uses the existing authenticated,
 * generation-checked game-thread endpoint; this component never writes Store.
 */
export default function LockedVariablesPane({
  locks, generation, bridge, token, onLocksChanged, onInspect,
}) {
  const entries = Array.isArray(locks?.entries) ? locks.entries : [];
  const [query, setQuery] = useState('');
  const [busyKey, setBusyKey] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const staleCount = entries.filter((entry) => entry.stale === true).length;
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return entries;
    return entries.filter((entry) => {
      const path = formatTypedPath(entry.key);
      return path.toLocaleLowerCase().includes(needle) ||
        String(entry.baseline_type || '').toLocaleLowerCase().includes(needle) ||
        String(entry.stale_reason || '').toLocaleLowerCase().includes(needle);
    });
  }, [entries, query]);

  const applyAction = async (entry, action) => {
    if (!token || !Number.isSafeInteger(generation) ||
        entry?.scope !== 'store' || !Array.isArray(entry.path)) {
      throw new Error('The lock entry is invalid or the game session is not ready.');
    }
    const response = await fetch(bridge + '/api/v1/locks', {
      method: 'PUT', mode: 'cors', cache: 'no-store',
      headers: { 'X-Inspector-Token': token, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action, scope: 'store', path: entry.path, generation,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 409) {
        throw new Error(data.code === 'lock_missing'
          ? 'This lock no longer exists. The workspace will update from the next snapshot.'
          : 'The game state changed. Wait for the next snapshot before changing locks.');
      }
      if (response.status === 422) {
        throw new Error('This path is no longer an eligible Store primitive. Unlock it instead of refreshing.');
      }
      if (response.status === 429) {
        throw new Error(data.error || 'The Inspector queue or lock capacity is busy. Retry shortly.');
      }
      if (response.status === 403) {
        throw new Error('Primitive editing has been disabled by the game.');
      }
      throw new Error(data.error || 'Lock request failed (HTTP ' + response.status + ').');
    }
    if (data.generation !== generation || data.locked !== (action !== 'unlock') ||
        !Array.isArray(data.locks?.entries) ||
        !Number.isSafeInteger(data.locks?.revision)) {
      throw new Error('Lock confirmation was invalid. Wait for the next snapshot and retry.');
    }
    onLocksChanged?.(data.locks);
    return data;
  };

  const runAction = async (entry, action) => {
    setBusyKey(entry.key);
    setError('');
    setNotice('');
    try {
      await applyAction(entry, action);
      const path = formatTypedPath(entry.key);
      setNotice(action === 'refresh'
        ? 'Lock refreshed against the current game value: ' + path
        : 'Unlocked ' + path);
    } catch (reason) {
      setError(reason.message || 'Lock request failed.');
    } finally {
      setBusyKey('');
    }
  };

  const unlockAll = async () => {
    const pending = entries.slice();
    if (!pending.length || bulkBusy) return;
    setBulkBusy(true);
    setBusyKey('');
    setError('');
    setNotice('');
    let released = 0;
    try {
      for (const entry of pending) {
        setProgress('Unlocking ' + (released + 1) + ' of ' + pending.length + '…');
        await applyAction(entry, 'unlock');
        released += 1;
      }
      setNotice('Unlocked all ' + released + ' variables.');
    } catch (reason) {
      setError('Unlocked ' + released + ' of ' + pending.length +
        ' variables before stopping: ' + (reason.message || 'Lock request failed.'));
    } finally {
      setProgress('');
      setBulkBusy(false);
    }
  };

  return <section className="locked-workspace" aria-label="Locked variables workspace">
    <div className="locked-toolbar">
      <div className="locked-summary">
        <Tag color="success">{entries.length} active</Tag>
        <Tag color={staleCount ? 'warning' : 'default'}>{staleCount} stale</Tag>
        <Text type="secondary">
          {entries.length} of {locks?.limit ?? 128} locks · {locks?.bytes_used ?? 0} / {locks?.byte_limit ?? 32768} bytes
        </Text>
      </div>
      <Popconfirm
        title={'Unlock all ' + entries.length + ' active locks?'}
        description="This removes Inspector protection from every listed path."
        okText="Unlock all"
        cancelText="Cancel"
        okButtonProps={{ danger: true }}
        onConfirm={unlockAll}
        disabled={!entries.length || bulkBusy || Boolean(busyKey)}>
        <Button danger size="small" disabled={!entries.length || bulkBusy || Boolean(busyKey)}
          loading={bulkBusy} aria-label="Unlock all variables">
          Unlock all
        </Button>
      </Popconfirm>
    </div>
    <Alert type="info" showIcon message="Locks protect Inspector operations only"
      description="Locks block this Inspector’s Edit, Undo and Redo actions. They do not stop Ren’Py or game scripts from changing variables. Stale locks remain active until refreshed or unlocked. The baseline stores a fingerprint and type, not the original value." />
    {error && <Alert type="error" showIcon message={error} />}
    {notice && <Alert type="success" showIcon message={notice} />}
    {progress && <Text type="secondary" role="status">{progress}</Text>}
    <Input allowClear size="small" className="locked-filter" value={query}
      aria-label="Filter locked variables" placeholder="Filter locked paths"
      onChange={(event) => setQuery(event.target.value)} />
    <div className="locked-list" role="list" aria-label="Active variable locks">
      {visible.map((entry) => {
        const path = formatTypedPath(entry.key) || 'store (invalid path)';
        const stale = entry.stale === true;
        const busy = bulkBusy || Boolean(busyKey);
        return <article className="locked-entry" role="listitem" key={entry.key}>
          <div className="locked-entry-main">
            <div className="locked-entry-title">
              <LockOutlined className="locked-entry-icon" />
              <Text className="locked-entry-path" title={path}>{path}</Text>
              <Tag color={stale ? 'warning' : 'success'}>{stale ? 'Stale' : 'Active'}</Tag>
            </div>
            <Text type="secondary" className="locked-entry-meta">
              Baseline type: {entry.baseline_type || 'unknown'} · Locked {formatLockedAt(entry.locked_at)}
            </Text>
            {stale && <Text type="warning" className="locked-entry-stale">
              {staleDescription(entry.stale_reason)}
              {Number.isFinite(entry.stale_at) ? ' Detected ' + formatLockedAt(entry.stale_at) + '.' : ''}
            </Text>}
          </div>
          <Space className="locked-entry-actions" size="small" wrap>
            <Button size="small" icon={<EyeOutlined />} disabled={busy}
              aria-label={'Inspect ' + path}
              onClick={() => onInspect?.(entry.scope, entry.key)}>Inspect</Button>
            {stale && <Button size="small" icon={<ReloadOutlined />} disabled={busy}
              aria-label={'Refresh lock ' + path}
              onClick={() => runAction(entry, 'refresh')}>Refresh</Button>}
            <Button size="small" danger icon={<UnlockOutlined />} disabled={busy}
              aria-label={'Unlock ' + path}
              onClick={() => runAction(entry, 'unlock')}>Unlock</Button>
          </Space>
        </article>;
      })}
    </div>
    {!visible.length && <Empty className="locked-empty"
      description={entries.length
        ? 'No locks match this filter.'
        : 'No locked variables. Lock an eligible Store primitive from its details drawer.'} />}
  </section>;
}
