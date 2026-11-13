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
  selection, generation, bridge, token, enabled, onApplied,
}) {
  const [opened, setOpened] = useState(false);
  const [target, setTarget] = useState(null);
  const [value, setValue] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const controller = useRef(null);

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
        setTarget(data);
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
    if (!valid || !target?.editable || target.generation !== generation ||
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
        No automatic undo or change history is provided.
      </Text>
      {busy && <Text type="secondary">Processing game-thread request…</Text>}
      {target && !target.editable && <Text type="secondary" role="status">
        {target.reason || 'This value is not eligible for editing.'}
      </Text>}
      {target?.editable && <>
        <Text type="secondary">Current type: {target.type}. The type cannot be changed.
          {target.type === 'bool' ? ' Enter True or False.' : ''}
        </Text>
        <label className="detail-edit-label" htmlFor="primitive-edit-text">New literal value</label>
        <Input.TextArea id="primitive-edit-text" aria-label="New literal value"
          value={value} onChange={(event) => {
            setValue(event.target.value); setConfirmed(false);
          }} maxLength={MAX_EDIT_TEXT} autoSize={{ minRows: 2, maxRows: 7 }} />
        <Checkbox checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}>
          I understand this writes to the running game state
        </Checkbox>
        <Button size="small" type="primary" danger loading={busy} onClick={apply}
          disabled={!confirmed || busy || value === target.text || value.length > MAX_EDIT_TEXT}
          aria-label="Apply primitive edit">Apply edit</Button>
      </>}
    </>}
    {error && <Text type="danger" role="alert">{error}</Text>}
    {saved && <Text type="success" role="status">{saved}</Text>}
  </section>;
}
