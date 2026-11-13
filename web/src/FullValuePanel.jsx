import React, { useEffect, useRef, useState } from 'react';
import { Button, Space, Tag, Typography } from 'antd';
import { CopyOutlined, ReloadOutlined } from '@ant-design/icons';
import { decodeTreeKey, formatTypedPath } from './tree.js';
import { fullValueTone } from './value-format.js';

const { Text } = Typography;
const DISPLAY_KINDS = new Set(['string', 'number', 'boolean', 'null']);
const MAX_DISPLAY_CHARS = 16384;

/**
 * Full values are requested only when the user clicks. They are never part
 * of automatic root, page, favourite or history polling.
 *
 * The parent keys this component by typed path + game generation so a
 * reopened drawer cannot retain a previous game's sensitive value.
 */
export default function FullValuePanel({ selection, generation, bridge, token }) {
  const [value, setValue] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(null);
  const exactPath = formatTypedPath(selection?.key);

  useEffect(() => () => pending.current?.abort(), []);

  const loadValue = async () => {
    const decoded = decodeTreeKey(selection?.key);
    if (!decoded || decoded.scope !== selection.scope || !decoded.path.length ||
        !Number.isSafeInteger(generation) || !token || loading) return;

    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true);
    setValue(null);
    setError('');
    try {
      const params = new URLSearchParams({
        scope: selection.scope,
        path: JSON.stringify(decoded.path),
      });
      const response = await fetch(bridge + '/api/v1/full-value?' + params, {
        method: 'GET', mode: 'cors', cache: 'no-store',
        headers: { 'X-Inspector-Token': token }, signal: controller.signal,
      });
      if (!response.ok) throw new Error(response.status === 409
        ? 'Game state changed. Reopen the variable.'
        : response.status === 503 ? 'Game interaction is paused. Resume and retry.'
          : response.status === 429 ? 'Inspector queue busy. Retry shortly.'
            : 'Full value request failed (HTTP ' + response.status + ')');
      const data = await response.json();
      if (data.protocol !== 1 || data.generation !== generation ||
          data.scope !== selection.scope || data.key !== selection.key ||
          !['string', 'number', 'boolean', 'null', 'unsupported', 'missing'].includes(data.kind) ||
          (DISPLAY_KINDS.has(data.kind) &&
            (typeof data.text !== 'string' || data.text.length > MAX_DISPLAY_CHARS * 2))) {
        throw new Error('Full value response is invalid or from an older game state.');
      }
      if (!controller.signal.aborted) setValue(data);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason.message || 'Full value unavailable');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
      if (pending.current === controller) pending.current = null;
    }
  };

  const copy = async (text) => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard is unavailable');
      await navigator.clipboard.writeText(text);
    } catch {
      setError('Could not copy to clipboard.');
    }
  };

  const displayable = value && DISPLAY_KINDS.has(value.kind);
  const complete = displayable && !value.truncated;

  return <section className="detail-full-value" aria-label="Full value inspection"
    style={{ marginTop: 16 }}>
    <Space wrap>
      <Button size="small" type="primary" loading={loading}
        onClick={loadValue} aria-label={value ? 'Refresh full value' : 'Show full value'}>
        {value ? <><ReloadOutlined /> Refresh full value</> : 'Show full value'}
      </Button>
      <Button size="small" icon={<CopyOutlined />}
        disabled={!complete} onClick={() => copy(value.text)}>
        Copy Value
      </Button>
      <Button size="small" icon={<CopyOutlined />}
        disabled={!exactPath} onClick={() => copy(exactPath)}>
        Copy Path
      </Button>
    </Space>
    <div style={{ marginTop: 8 }}>
      <Text type="secondary">
        On-demand game-thread capture · maximum {MAX_DISPLAY_CHARS.toLocaleString()} characters.
        Values may change after capture.
      </Text>
    </div>
    {error && <Text type="danger" role="alert">{error}</Text>}
    {value && <>
      <div style={{ marginTop: 10 }}>
        {displayable ? <>
          <Space wrap>
            <Tag>{value.kind}</Tag>
            {value.truncated && <Tag color="gold">Truncated: {value.limit.toLocaleString()}-character budget</Tag>}
            {Number.isSafeInteger(value.length) &&
              <Text type="secondary">{value.length.toLocaleString()} {value.length_unit || 'characters'} in source</Text>}
          </Space>
          <pre aria-label="Full variable value" className={`detail-full-value-text value-tone-${fullValueTone(value.kind)}`}
            style={{
              marginTop: 10, maxHeight: '38vh', overflow: 'auto',
              whiteSpace: 'pre-wrap', overflowWrap: 'anywhere',
              fontSize: 13, lineHeight: 1.55,
              background: '#0b1220', padding: 12, borderRadius: 7,
              userSelect: 'text',
            }}>{value.text}</pre>
          {value.truncated && <Text type="secondary">
            Only the leading portion is shown. Copy Value is disabled to avoid copying
            an incomplete value as though it were the original.
          </Text>}
        </> : <Text type="secondary" role="status">
          {value.reason || 'This variable cannot be displayed as a primitive.'}
        </Text>}
      </div>
    </>}
  </section>;
}
