import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button, Card, ConfigProvider, Descriptions, Drawer, Empty, Input,
  Spin, Statistic, Tabs, Tag, Tooltip, Tree, Typography, theme,
} from 'antd';
import {
  ApartmentOutlined, CheckCircleFilled, CopyOutlined, DisconnectOutlined,
  EyeOutlined, ReloadOutlined, RightOutlined, DownOutlined, SearchOutlined,
  StarFilled, StarOutlined,
} from '@ant-design/icons';
import {
  flatten, filteredTree, favouriteNodes, keysOf, readBridgeFragment, safeFavourites,
} from './tree.js';

const { Text, Title, Paragraph } = Typography;
const initialConnection = readBridgeFragment(window.location.hash);
const FAVORITES_KEY = 'renpy-inspector-ant-favourites-v1';
const SNAPSHOT_REFRESH_MS = 1250;
const SCOPES = [{ key: 'store', label: 'Store' }, { key: 'persistent', label: 'Persistent' }];

function loadLocalFavourites() {
  try { return safeFavourites(JSON.parse(localStorage.getItem(FAVORITES_KEY) ?? '[]')); }
  catch { return []; }
}

function captureTime(epoch) {
  if (!epoch) return 'Waiting for game snapshot';
  return new Date(epoch * 1000).toLocaleTimeString();
}

function previewKind(type) {
  const kind = String(type ?? '').toLowerCase();
  if (['str', 'unicode', 'bytes'].includes(kind)) return 'string';
  if (['bool', 'boolean'].includes(kind)) return 'boolean';
  if (['int', 'float', 'long', 'complex'].includes(kind)) return 'number';
  if (['nonetype', 'none'].includes(kind)) return 'null';
  return 'object';
}

function TreeRow({ node, isFavourite, isActive, onToggle, onDetails, onFavourite }) {
  const canExpand = Boolean(node.children?.length);
  return <span className={`variable-row${isActive ? ' variable-row-active' : ''}`}>
    <span className={`variable-label${canExpand ? ' variable-label-expandable' : ''}`}
      role={canExpand ? 'button' : undefined} tabIndex={canExpand ? 0 : undefined}
      aria-expanded={canExpand ? Boolean(node.expanded) : undefined}
      onClick={canExpand ? (event) => { event.stopPropagation(); onToggle(); } : undefined}
      onKeyDown={canExpand ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault(); event.stopPropagation(); onToggle();
        }
      } : undefined}>
      <span className="variable-key" title={node.path}>{node.name}</span>
      <span className="variable-colon">:</span>
      <span className="variable-type">{node.type}</span>
    </span>
    <span className={`variable-preview preview-${previewKind(node.type)}`}
      title={`${node.type} · ${node.preview}`}>{node.preview}</span>
    <span className="variable-actions">
      <Tooltip title="Inspect path and value">
        <button type="button" className="row-icon-button" aria-label={`Inspect ${node.name}`}
          onClick={(event) => { event.stopPropagation(); onDetails(); }}>
          <EyeOutlined />
        </button>
      </Tooltip>
      <Tooltip title={isFavourite ? 'Remove favourite' : 'Add favourite'}>
        <button type="button" className="row-icon-button" aria-label={`${isFavourite ? 'Remove' : 'Add'} ${node.name} ${isFavourite ? 'from' : 'to'} favourites`}
          aria-pressed={isFavourite}
          onClick={(event) => { event.stopPropagation(); onFavourite(); }}>
          {isFavourite ? <StarFilled className="pinned-star" /> : <StarOutlined />}
        </button>
      </Tooltip>
    </span>
  </span>;
}

function VariablePane({ scope, snapshot, query, favourites, selected, onSelect, onFavourite, expanded, onExpand }) {
  const viewportRef = useRef(null);
  const [height, setHeight] = useState(450);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const measure = () => {
      const next = Math.floor(element.getBoundingClientRect().height);
      if (next > 0) setHeight((before) => before === next ? before : next);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const nodes = useMemo(() => scope === 'favourites'
    ? favouriteNodes(snapshot?.scopes, favourites)
    : snapshot?.scopes?.[scope] ?? [], [scope, snapshot, favourites]);
  const visible = useMemo(() => filteredTree(nodes, query), [nodes, query]);
  const favKeys = useMemo(() => new Set(favourites.map((x) => `${x.scope}:${x.key}`)), [favourites]);
  const hasQuery = Boolean(query.trim());
  const expandedKeys = hasQuery ? keysOf(visible) : expanded[scope] ?? [];
  const expandedSet = new Set(expandedKeys);
  const treeData = useMemo(() => {
    const convert = (items) => items.map((node) => ({
      ...node,
      title: node.name,
      isLeaf: !node.children?.length,
      children: convert(node.children ?? []),
    }));
    return convert(visible);
  }, [visible]);

  return <section className="variable-pane" aria-label="Variable tree workspace">
    <div className="variable-pane-summary">
      <Text type="secondary">{scope === 'favourites' ? `${favourites.length} saved browser pins` : `${snapshot?.counts?.[scope] ?? 0} captured nodes`}</Text>
      {scope !== 'favourites' && snapshot?.truncated?.[scope] &&
        <Tag color="gold" title="The bridge limits captures to protect the game">Partial snapshot</Tag>}
      {hasQuery && <Text type="secondary">Filtered, captured nodes only</Text>}
    </div>
    <div ref={viewportRef} className="variable-tree-viewport">
      {treeData.length ? <Tree
        className="full-width-variable-tree" blockNode showLine={{ showLeafIcon: false }}
        switcherIcon={({ expanded: isExpanded }) => isExpanded ? <DownOutlined /> : <RightOutlined />}
        selectable={false} virtual height={height}
        treeData={treeData} expandedKeys={expandedKeys} autoExpandParent={hasQuery}
        onExpand={(next) => { if (!hasQuery) onExpand(scope, next); }}
        titleRender={(raw) => {
          const node = raw;
          const originScope = scope === 'favourites' ? node.favouriteScope : scope;
          const sourceKey = node.sourceKey ?? node.key;
          const pinned = favKeys.has(`${originScope}:${sourceKey}`);
          return <TreeRow node={{ ...node, expanded: expandedSet.has(node.key) }}
            isFavourite={pinned}
            isActive={selected?.scope === originScope && selected?.key === sourceKey}
            onToggle={hasQuery ? undefined : () => {
              onExpand(scope, expandedSet.has(node.key)
                ? expandedKeys.filter((key) => key !== node.key)
                : [...expandedKeys, node.key]);
            }}
            onDetails={() => onSelect(originScope, sourceKey)}
            onFavourite={() => onFavourite(originScope, sourceKey)} />;
        }} /> :
        <Empty className="empty-variables" description={hasQuery ? 'No captured variables match this search' :
          scope === 'favourites' ? 'Pin variables using the star on a tree row' : 'No variables captured'} />}
    </div>
    <div className="variable-pane-footer">
      <Text type="secondary">Read-only · Captured values · Live updates</Text>
      <Text type="secondary">{scope !== 'favourites' && snapshot?.truncated?.[scope]
        ? 'Some branches are not included in the bounded snapshot'
        : 'Expand a captured branch to browse its children'}</Text>
    </div>
  </section>;
}

export default function App() {
  const [token] = useState(initialConnection.token);
  const [bridge] = useState(initialConnection.bridge || window.location.origin);
  const [snapshot, setSnapshot] = useState(null);
  const [connection, setConnection] = useState(token ? 'connecting' : 'unpaired');
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [section, setSection] = useState('variables');
  const [scope, setScope] = useState('store');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [expanded, setExpanded] = useState({ store: [], persistent: [], favourites: [] });
  const [favourites, setFavourites] = useState(loadLocalFavourites);
  const requestCounter = useRef(0);

  useEffect(() => {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(favourites)); } catch { /* private browsing */ }
  }, [favourites]);

  useEffect(() => {
    if (!token) { setConnection('unpaired'); return; }
    let disposed = false;
    let busy = false;
    const id = ++requestCounter.current;
    const poll = async () => {
      if (busy) return;
      busy = true;
      try {
        const response = await fetch(`${bridge}/api/v1/snapshot`, {
          headers: { 'X-Inspector-Token': token }, method: 'GET', cache: 'no-store', mode: 'cors',
        });
        if (!response.ok) throw new Error(response.status === 401 ? 'Pairing token expired' : `HTTP ${response.status}`);
        const data = await response.json();
        if (!data || data.protocol !== 1 || !data.scopes) throw new Error('Unsupported bridge protocol');
        if (!disposed && id === requestCounter.current) {
          setSnapshot(data); setConnection('online'); setError('');
        }
      } catch (failure) {
        if (!disposed && id === requestCounter.current) {
          setConnection('offline'); setError(failure.message || 'Connection unavailable');
        }
      } finally { busy = false; }
    };
    poll();
    const timer = window.setInterval(poll, SNAPSHOT_REFRESH_MS);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [token, bridge, refresh]);

  const selectNode = useCallback((chosenScope, key) => setSelected({ scope: chosenScope, key }), []);
  const pinVariable = useCallback((chosenScope, key) => {
    if (!SCOPES.some((item) => item.key === chosenScope)) return;
    setFavourites((before) => {
      const rest = before.filter((x) => !(x.scope === chosenScope && x.key === key));
      return rest.length < before.length ? rest : [...before, { scope: chosenScope, key }].slice(0, 100);
    });
  }, []);
  const onExpanded = useCallback((chosenScope, keys) => {
    setExpanded((before) => ({ ...before, [chosenScope]: keys }));
  }, []);
  const activeNode = useMemo(() => {
    if (!selected) return null;
    return flatten(snapshot?.scopes?.[selected.scope] ?? []).get(selected.key) || null;
  }, [snapshot, selected]);
  const selectedPinned = Boolean(selected && favourites.some((x) => x.scope === selected.scope && x.key === selected.key));
  const activeGame = snapshot?.game ?? {};
  const online = connection === 'online';

  return <ConfigProvider theme={{ algorithm: [theme.darkAlgorithm, theme.compactAlgorithm], token: {
    colorPrimary: '#5b9ff3', colorBgBase: '#0e1726', colorText: '#e8eef9',
    fontSize: 13, borderRadius: 7,
  } }}>
    <div className="inspector-shell">
      <header className="inspector-header">
        <div className="product-brand">
          <ApartmentOutlined className="product-icon" />
          <span><strong>Ren'Py Inspector</strong><small>External workspace · v0.6.1 preview</small></span>
        </div>
        <div className="connection-status" role="status">
          <Tag color="blue">READ ONLY</Tag>
          {online ? <CheckCircleFilled style={{ color: '#57d5a5' }} /> :
            connection === 'connecting' ? <Spin size="small" /> : <DisconnectOutlined style={{ color: '#ff9b81' }} />}
          <span>{online ? 'Connected' : connection === 'connecting' ? 'Connecting' : 'Disconnected'}</span>
        </div>
      </header>
      <Tabs className="main-navigation" activeKey={section} onChange={setSection}
        items={[{ key: 'overview', label: 'Overview' }, { key: 'variables', label: 'Variables' }, { key: 'scripts', label: 'Scripts' }]} />
      <main className="inspector-main">
        {section === 'variables' && <div className="variables-workspace">
          <div className="variables-toolbar">
            <Input allowClear size="middle" className="variable-search"
              prefix={<SearchOutlined />} placeholder="Search captured variable name, path, type or value"
              aria-label="Search captured variables" value={query} onChange={(e) => setQuery(e.target.value)} />
            <Tooltip title="Fetch latest snapshot"><Button type="text" aria-label="Refresh snapshot"
              icon={<ReloadOutlined />} onClick={() => setRefresh((n) => n + 1)} /></Tooltip>
          </div>
          <Tabs className="variable-scope-tabs" activeKey={scope} onChange={setScope}
            items={[{ key: 'store', label: 'Store' }, { key: 'persistent', label: 'Persistent' },
              { key: 'favourites', label: `Favourites (${favourites.length})` }]} />
          <VariablePane scope={scope} snapshot={snapshot} query={query} favourites={favourites}
            selected={selected} onSelect={selectNode} onFavourite={pinVariable}
            expanded={expanded} onExpand={onExpanded} />
        </div>}
        {section === 'overview' && <section className="info-page" aria-label="Runtime overview">
          <Text className="eyebrow">RUNTIME STATUS</Text>
          <Title level={3}>Overview</Title>
          <div className="overview-statistics">
            <Card><Statistic title="Captured Store nodes" value={snapshot?.counts?.store ?? 0} /></Card>
            <Card><Statistic title="Captured Persistent nodes" value={snapshot?.counts?.persistent ?? 0} /></Card>
            <Card><Statistic title="Browser favourites" value={favourites.length} /></Card>
          </div>
          <Card title="Active session" className="overview-card">
            <Descriptions column={1} size="small" items={[
              { key: 'game', label: 'Game', children: activeGame.game || 'Unavailable' },
              { key: 'engine', label: "Ren'Py", children: activeGame.version || 'Unavailable' },
              { key: 'capture', label: 'Last capture', children: captureTime(snapshot?.captured_at) },
              { key: 'connection', label: 'Connection', children: online ? 'Local authenticated read-only API' : 'Disconnected' },
            ]} />
          </Card>
        </section>}
        {section === 'scripts' && <section className="info-page" aria-label="Script context">
          <Text className="eyebrow">SCRIPT CONTEXT</Text>
          <Title level={3}>Scripts</Title>
          <Paragraph type="secondary">Available script location metadata is shown below. Full source browsing is not supported by the external bridge.</Paragraph>
          <Card className="overview-card"><Descriptions column={1} size="small" items={[
            { key: 'file', label: 'Script file', children: activeGame.filename || 'Not exposed by game runtime' },
            { key: 'line', label: 'Line', children: activeGame.line || 'Unavailable' },
          ]} /></Card>
        </section>}
      </main>
      <footer className="inspector-statusbar">
        <span>{online ? `Live snapshot · ${captureTime(snapshot?.captured_at)}` : error || 'Open this inspector from the game Settings to pair'}</span>
        <span>Read-only · Local session</span>
      </footer>
      <Drawer title="Variable details" className="inspector-detail-drawer" placement="right"
        width="min(520px, 94vw)" open={Boolean(selected)} onClose={() => setSelected(null)}>
        {selected && <>
          <div className="detail-heading">
            <div><Text type="secondary">{selected.scope.toUpperCase()}</Text>
              <Title level={4}>{activeNode?.name || 'Variable unavailable'}</Title></div>
            <Button icon={selectedPinned ? <StarFilled /> : <StarOutlined />}
              aria-label={selectedPinned ? 'Remove favourite' : 'Add favourite'}
              onClick={() => pinVariable(selected.scope, selected.key)}>
              {selectedPinned ? 'Pinned' : 'Pin'}
            </Button>
          </div>
          <Descriptions column={1} size="small" bordered items={[
            { key: 'path', label: 'Path', children: <Text copyable={{ text: activeNode?.path ?? '' }} className="path-monospace">{activeNode?.path || 'Not in latest snapshot'}</Text> },
            { key: 'type', label: 'Type', children: <Tag color="geekblue">{activeNode?.type || 'Unknown'}</Tag> },
            { key: 'state', label: 'State', children: activeNode?.state || 'Missing from latest snapshot' },
          ]} />
          <div className="detail-preview-heading"><Text strong>Captured value preview</Text>
            <Tooltip title="Copy the captured preview, not a full live value">
              <Button icon={<CopyOutlined />} disabled={!activeNode} size="small"
                onClick={() => activeNode && navigator.clipboard?.writeText(activeNode.preview).catch(() => {})}>Copy preview</Button>
            </Tooltip>
          </div>
          <pre className="detail-value">{activeNode?.preview ?? '(not available)'}</pre>
          {activeNode?.limited && <Tag color="gold">Some descendants were omitted by snapshot limits</Tag>}
          <Paragraph type="secondary" className="detail-disclaimer">This is a bounded, read-only snapshot. Full values and uncaptured descendants are not available through the current bridge.</Paragraph>
        </>}
      </Drawer>
    </div>
  </ConfigProvider>;
}
