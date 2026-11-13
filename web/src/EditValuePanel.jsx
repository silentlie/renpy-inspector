import React, { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Input, Space, Tag, Typography } from 'antd';
import { decodeTreeKey } from './tree.js';

const { Text } = Typography;
const MAX_EDIT_TEXT = 1024;

/**
 * Editing is absent unless enabled in trusted game init code. Opening the
 * editor is an explicit GET; applying requires an additional confirmation.
 * No automatic writes, rerender writes, or background editing requests.
 */
export default function EditValuePanel({
  selection, generation, bridge, token, enabled, locks, onApplied, onLocksChanged,
}) {
  const [opened, setOpened] = useState(false);
  const [target, setTarget] = useState(null);
  const [value, setValue] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const controller = useRef(null);
  const selectedLockKey = selection?.key;
  const lockedFromSnapshot = Array.isArray(locks?.entries)
    ? locks.entries.some((entry) => entry.key === selectedLockKey)
    : undefined;
  const isLocked = lockedFromSnapshot ?? (target?.locked === true);

  useEffect(() => () => controller.current?.abort(), []);
  if (!enabled || selection?.scope !== 'store') return null;

  const decoded = decodeTreeKey(selection?.key);
  const valid = decoded?.scope === 'store' && decoded.path?.length > 0 &&
    Number.isSafeInteger(generation) && token;
  const read = async () => {
    if (!valid || busy) return;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setBusy(true); setError(''); setSaved('');
    setTarget(null); setConfirmed(false);
    try {
      const params = new URLSearchParams({
        scope: 'store', path: JSON.stringify(decoded.path),
      });
      const result = await fetch(bridge + '/api/v1/edit-target?' + params, {
        method: 'GET', mode: 'cors', cache: 'no-store',
        headers: { 'X-Inspector-Token': token }, signal: request.signal,
      });
      if (!result.ok) throw new Error(result.status === 403
        ? 'Game configuration has disabled editing.'
        : result.status === 409 ? 'Game state changed. Reopen the variable.'
          : 'Edit target unavailable (HTTP ' + result.status + ')');
      const data = await result.json();
      if (data.protocol !== 1 || data.generation !== generation ||
          data.key !== selection.key || data.scope !== 'store' ||
          typeof data.editable !== 'boolean' ||
          (data.editable && (typeof data.text !== 'string' ||
            data.text.length > MAX_EDIT_TEXT ||
            typeof data.expected !== 'string' || !/^[0-9a-f]{64}$/.test(data.expected) ||
            !['str', 'unicode', 'int', 'long', 'float', 'bool'].includes(data.type)))) {
        throw new Error('Edit target does not match the selected game generation.');
      }
      if (!request.signal.aborted) {
        setTarget({ ...data, locked: data.locked === true });
        setValue(data.editable ? data.text : '');
      }
    } catch (reason) {
      if (!request.signal.aborted) setError(reason.message || 'Could not inspect edit target.');
    } finally {
      if (!request.signal.aborted) setBusy(false);
      if (controller.current === request) controller.current = null;
    }
  };

  const apply = async () => {
    if (!valid || !target?.editable || isLocked || target.generation !== generation ||
        !confirmed || busy || value === target.text || value.length > MAX_EDIT_TEXT) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true); setError(''); setSaved('');
    try {
      const result = await fetch(bridge + '/api/v1/edit', {
        method: 'PUT', mode: 'cors', cache: 'no-store', signal: request.signal,
        headers: { 'X-Inspector-Token': token, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope: 'store', path: decoded.path, generation: target.generation,
          expected: target.expected, type: target.type, text: value,
        }),
      });
      if (!result.ok) throw new Error(result.status === 409 ?
        'Conflict: variable value or game state changed. Reopen the editor.' :
        result.status === 423 ? 'This variable is locked against Inspector writes. Unlock it before editing.' :
          result.status === 422 ? 'The variable is no longer editable.' :
            result.status === 403 ? 'Editing has been disabled by the game.' :
              result.status === 503 ? 'Game interaction paused. Check the value before retrying.' :
                result.status === 400 ? 'Invalid value for the existing primitive type.' :
                  'Edit failed (HTTP ' + result.status + ')');
      const data = await result.json();
      if (!data.applied || !Number.isSafeInteger(data.generation) ||
          data.generation <= generation) {
        throw new Error('Edit confirmation was invalid; inspect current game state.');
      }
      setTarget(null); setConfirmed(false); setOpened(false);
      setSaved('Edit applied. Game state has been refreshed.');
      onApplied?.();
    } catch (reason) {
      if (!request.signal.aborted) setError(reason.message || 'Edit request failed.');
    } finally {
      if (!request.signal.aborted) setBusy(false);
      if (controller.current === request) controller.current = null;
    }
  };

  const toggleLock = async () => {
    if (!valid || !target?.editable || !Number.isSafeInteger(target.generation) || busy) return;
    const action = isLocked ? 'unlock' : 'lock';
    setBusy(true); setError(''); setSaved('');
    const request = new AbortController();
    controller.current?.abort();
    controller.current = request;
    try {
      const response = await fetch(bridge + '/api/v1/locks', {
        method: 'PUT', mode: 'cors', cache: 'no-store', signal: request.signal,
        headers: { 'X-Inspector-Token': token, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action, scope: 'store', path: decoded.path, generation: target.generation,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(response.status === 409
          ? 'Game state changed. Reopen the variable before changing its lock.'
          : response.status === 422
            ? 'Only an existing supported Store primitive can be locked.'
            : response.status === 429
              ? 'The session lock limit has been reached.'
              : response.status === 403
                ? 'Variable editing has been disabled by the game.'
                : 'Lock request failed (HTTP ' + response.status + ')');
      }
      if (data.generation !== target.generation || data.locked !== (action === 'lock') ||
          !Array.isArray(data.locks?.entries)) {
        throw new Error('Lock confirmation was invalid. Refresh the variable before retrying.');
      }
      setTarget((current) => current ? {
        ...current, locked: data.locked, lock_revision: data.locks.revision,
      } : current);
      onLocksChanged?.(data.locks);
      setConfirmed(false);
      setSaved(data.locked
        ? 'Variable protected from Inspector edits and Undo/Redo.'
        : 'Variable unlocked for Inspector edits and Undo/Redo.');
    } catch (reason) {
      if (!request.signal.aborted) setError(reason.message || 'Lock request failed.');
    } finally {
      if (!request.signal.aborted) setBusy(false);
      if (controller.current === request) controller.current = null;
    }
  };

  return <section className="detail-edit-panel" aria-label="Primitive variable editing">
    <Space wrap>
      <Text strong>Primitive editor</Text>
      <Tag color="orange">Explicitly enabled · game state write</Tag>
      <Button size="small" disabled={!valid || busy}
        aria-label={opened ? 'Close primitive editor' : 'Open primitive editor'}
        onClick={() => {
          if (opened) {
            controller.current?.abort();
            setOpened(false); setTarget(null); setConfirmed(false); setError('');
          } else { setOpened(true); read(); }
        }}>
        {opened ? 'Close editor' : 'Edit primitive'}
      </Button>
    </Space>
    {opened && <>
      <Text type="secondary" className="detail-edit-warning">
        This changes the running game. Saves and rollback may be affected.
        Existing Store primitives only, with exact-value and generation checks.
        Successful edits can be reversed from the session-only Edits tab, provided the recorded value still matches.
      </Text>
      {busy && <Text type="secondary">Processing game-thread request…</Text>}
      {target && !target.editable && <Text type="secondary" role="status">
        {target.reason || 'This value is not eligible for editing.'}
      </Text>}
      {target?.editable && <>
        <Space wrap className="detail-lock-controls">
          <Tag color={isLocked ? 'warning' : 'default'}>{isLocked ? 'Locked' : 'Unlocked'}</Tag>
          <Button size="small" disabled={busy} onClick={toggleLock}
            aria-label={isLocked ? 'Unlock variable' : 'Lock variable'}>
            {isLocked ? 'Unlock variable' : 'Lock variable'}
          </Button>
        </Space>
        <Text type="secondary" className="detail-lock-note">
          A lock blocks this Inspector's edits and Undo/Redo for this exact path. It does not
          prevent game scripts or Ren'Py from changing the variable during normal gameplay.
        </Text>
        <Text type="secondary">Current type: {target.type}. The type cannot be changed.
          {target.type === 'bool' ? ' Enter True or False.' : ''}
        </Text>
        {isLocked && <Text type="warning" role="status">This variable is locked. Unlock it before editing or reversing an edit.</Text>}
        <label className="detail-edit-label" htmlFor="primitive-edit-text">New literal value</label>
        <Input.TextArea id="primitive-edit-text" aria-label="New literal value" disabled={isLocked || busy}
          value={value} onChange={(event) => {
            setValue(event.target.value); setConfirmed(false);
          }} maxLength={MAX_EDIT_TEXT} autoSize={{ minRows: 2, maxRows: 7 }} />
        <Checkbox checked={confirmed} disabled={isLocked || busy} onChange={(event) => setConfirmed(event.target.checked)}>
          I understand this writes to the running game state
        </Checkbox>
        <Button size="small" type="primary" danger loading={busy} onClick={apply}
          disabled={!confirmed || busy || isLocked || value === target.text || value.length > MAX_EDIT_TEXT}
          aria-label="Apply primitive edit">Apply edit</Button>
      </>}
    </>}
    {error && <Text type="danger" role="alert">{error}</Text>}
    {saved && <Text type="success" role="status">{saved}</Text>}
  </section>;
}
