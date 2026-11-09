import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Button, Card, ConfigProvider, Descriptions, Divider, Empty, Input, Layout,
  Segmented, Space, Spin, Statistic, Tabs, Tag, Tooltip, Tree, Typography, theme,
} from 'antd';
import {
  ApartmentOutlined, CheckCircleFilled, DisconnectOutlined, ReloadOutlined,
  SearchOutlined, StarFilled, StarOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { flatten, filteredTree, keysOf, readBridgeFragment, safeFavourites } from './tree.js';

const { Header, Content, Sider } = Layout;
const { Text, Title, Paragraph } = Typography;
const rootParams = readBridgeFragment(window.location.hash);
const storeKey = 'renpy-inspector-ant-favourites-v1';
const initialFavourites = (() => {
  try { return safeFavourites(JSON.parse(localStorage.getItem(storeKey) ?? '[]')); }
  catch { return []; }
})();

function formatTime(epoch) {
  if (!epoch) return 'Waiting for game snapshot';
  return new Date(epoch * 1000).toLocaleTimeString();
}

function NodeTitle({ node, isFavourite }) {
  return <span className="tree-item-title">
    <span className="tree-name">{node.name}</span>
    <span className="tree-meta"><span className="tree-type">{node.type}</span> · {node.preview}</span>
    {isFavourite && <StarFilled className="tree-favourite-marker" />}
  </span>;
}

export default function App() {
  const [token, setToken] = useState(rootParams.token);
  const [bridge, setBridge] = useState(rootParams.bridge || window.location.origin);
  const [snapshot, setSnapshot] = useState(null);
  const [status, setStatus] = useState('connecting');
  const [reloadCount, setReloadCount] = useState(0);
  const [error, setError] = useState('');
  const [scope, setScope] = useState('store');
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('explorer');
  const [selected, setSelected] = useState(null);
  const [expanded, setExpanded] = useState([]);
  const [favourites, setFavourites] = useState(initialFavourites);
  const [treeHeight, setTreeHeight] = useState(Math.max(280, window.innerHeight - 360));
  const requestId = useRef(0);

  useEffect(() => {
    const resize = () => setTreeHeight(Math.max(280, window.innerHeight - 360));
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  useEffect(() => {
    try { localStorage.setItem(storeKey, JSON.stringify(favourites)); } catch { /* private mode */ }
  }, [favourites]);

  useEffect(() => {
    if (!token) { setStatus('unpaired'); return; }
    let disposed = false;
    const seq = ++requestId.current;
    const refresh = async () => {
      try {
        const response = await fetch(`${bridge}/api/v1/snapshot`, {
          headers: { 'X-Inspector-Token': token },
          method: 'GET', cache: 'no-store', mode: 'cors',
        });
        if (!response.ok) throw new Error(response.status === 401 ? 'Pairing token expired' : `HTTP ${response.status}`);
        const data = await response.json();
        if (!data || data.protocol !== 1 || !data.scopes) throw new Error('Unsupported bridge protocol');
        if (!disposed && seq === requestId.current) {
          setSnapshot(data); setStatus('online'); setError('');
        }
      } catch (e) {
        if (!disposed && seq === requestId.current) {
          setStatus('offline'); setError(e.message || 'Connection failed');
        }
      }
    };
    refresh();
    const handle = window.setInterval(refresh, 1250);
    return () => { disposed = true; window.clearInterval(handle); };
  }, [token, bridge, reloadCount]);

  const nodes = snapshot?.scopes?.[scope] ?? [];
  const nodeMap = useMemo(() => flatten(nodes), [nodes]);
  const visibleNodes = useMemo(() => filteredTree(nodes, query), [nodes, query]);
  const selection = selected?.scope === scope ? nodeMap.get(selected.key) : null;
  const favKeys = useMemo(() => new Set(favourites.map((x) => `${x.scope}:${x.key}`)), [favourites]);
  const treeData = useMemo(() => {
    const decorate = (entries) => entries.map((node) => ({
      ...node,
      title: <NodeTitle node={node} isFavourite={favKeys.has(`${scope}:${node.key}`)} />,
      children: decorate(node.children ?? []),
      isLeaf: !node.children?.length,
    }));
    return decorate(visibleNodes);
  }, [visibleNodes, favKeys, scope]);
  const expandedKeys = query ? keysOf(visibleNodes) : expanded;
  const currentFavourite = selection && favKeys.has(`${scope}:${selection.key}`);
  const toggleFavourite = (key) => {
    const location = { scope, key };
    setFavourites((list) => {
      const kept = list.filter((x) => !(x.scope === scope && x.key === key));
      return kept.length !== list.length ? kept : [...kept, location].slice(0, 100);
    });
  };
  const selectNode = (key, selectedScope = scope) => {
    setScope(selectedScope); setTab('explorer'); setSelected({ key, scope: selectedScope });
  };

  return <ConfigProvider theme={{ algorithm: theme.darkAlgorithm, token: {
    colorPrimary: '#5b9ff3', colorBgBase: '#0c111e', colorText: '#e6edfb',
    borderRadius: 8, fontSize: 13, wireframe: false,
  } }}>
    <Layout className="root-shell">
      <Header className="app-header">
        <div className="header-brand"><ApartmentOutlined className="brand-icon" />
          <div><Title level={4} className="brand-title">Ren'Py Inspector</Title>
            <Text className="brand-caption">EXTERNAL WORKSPACE <span className="brand-version">/ v0.6 preview</span></Text>
          </div>
        </div>
        <Space size={14}>
          <Tag color="blue">READ ONLY</Tag>
          <span className="status-indicator">
            {status === 'online' ? <CheckCircleFilled style={{ color: '#55d7a5' }} /> :
              status === 'connecting' ? <Spin size="small" /> : <DisconnectOutlined style={{ color: '#ff9b81' }} />}
            <span>{status === 'online' ? 'Connected' : status === 'connecting' ? 'Connecting' : 'Disconnected'}</span>
          </span>
        </Space>
      </Header>
      <Layout className="workspace-layout">
        <Sider width={440} className="tree-sider" breakpoint="lg" collapsedWidth="100%" trigger={null}>
          <div className="sider-heading">
            <div><Text className="eyebrow">EXPLORER</Text><Title level={5} className="side-title">Variable Navigator</Title></div>
            <Tooltip title="Refresh snapshots"><Button size="small" type="text" icon={<ReloadOutlined />}
              onClick={() => setReloadCount((n) => n + 1)} /></Tooltip>
          </div>
          <Segmented className="scope-toggle" size="middle" block value={scope} onChange={(next) => { setScope(next); setSelected(null); setExpanded([]); }}
            options={[{ label: 'Store', value: 'store' }, { label: 'Persistent', value: 'persistent' }]} />
          <Input className="tree-search" allowClear prefix={<SearchOutlined />} placeholder="Filter variables by name, path or value"
            value={query} onChange={(event) => setQuery(event.target.value)} />
          <div className="tree-bar"><Text className="eyebrow">VARIABLES</Text><Text type="secondary">{snapshot?.counts?.[scope] ?? 0} inspected</Text></div>
          {status !== 'online' && !snapshot ? <Empty className="tree-empty" description="Enable External UI in the game's Settings, then open the browser window." /> :
            treeData.length ? <Tree blockNode showLine className="inspector-tree" treeData={treeData}
              height={treeHeight} selectable virtual selectedKeys={selection ? [selection.key] : []}
              expandedKeys={expandedKeys} autoExpandParent={Boolean(query)}
              onExpand={(keys) => { if (!query) setExpanded(keys); }}
              onSelect={(keys) => { if (keys[0]) setSelected({ scope, key: keys[0] }); }} /> :
              <Empty className="tree-empty" description={query ? 'No matching variables in snapshot' : 'No variables captured'} />}
          <div className="tree-footer">
            <Text type="secondary">Snapshot is bounded to protect game performance.</Text>
            {snapshot?.truncated?.[scope] && <Tag color="gold">Partial tree</Tag>}
          </div>
        </Sider>
        <Content className="main-content">
          <Tabs activeKey={tab} onChange={setTab} className="workspace-tabs" items={[
            { key: 'explorer', label: 'Inspector' }, { key: 'favourites', label: `Favourites (${favourites.length})` },
            { key: 'overview', label: 'Overview' },
          ]} />
          {tab === 'explorer' && <div className="content-inner">
            {selection ? <>
              <div className="content-title-row">
                <div><Text className="eyebrow">SELECTED VARIABLE</Text><Title level={3} className="content-title">{selection.name}</Title></div>
                <Tooltip title={currentFavourite ? 'Unpin variable' : 'Add to browser favourites'}><Button
                  type={currentFavourite ? 'primary' : 'default'}
                  icon={currentFavourite ? <StarFilled /> : <StarOutlined />}
                  onClick={() => toggleFavourite(selection.key)}>{currentFavourite ? 'Pinned' : 'Pin'}</Button></Tooltip>
              </div>
              <Card className="detail-card" bordered={false}>
                <Descriptions bordered size="middle" column={1} items={[
                  { key: 'path', label: 'Path', children: <Text copyable className="monospace">{selection.path}</Text> },
                  { key: 'type', label: 'Type', children: <Tag color="geekblue">{selection.type}</Tag> },
                  { key: 'state', label: 'State', children: selection.state },
                ]} />
                <Divider orientation="left">Current value</Divider>
                <pre className="value-pane">{selection.preview}</pre>
                {selection.limited && <Text type="warning">Children beyond the snapshot budget are not included.</Text>}
              </Card>
            </> : <div className="welcome-panel">
              <div className="welcome-icon"><ApartmentOutlined /></div>
              <Title level={3}>Explore your game state</Title>
              <Paragraph type="secondary">Select a variable on the left to inspect its type, path and current value. Expand collections without modifying gameplay.</Paragraph>
              <div className="welcome-steps"><span>01 &nbsp; Find a variable</span><span>02 &nbsp; Inspect safely</span><span>03 &nbsp; Pin what matters</span></div>
            </div>}
          </div>}
          {tab === 'favourites' && <div className="content-inner">
            <div className="content-title-row"><div><Text className="eyebrow">LOCAL WATCHLIST</Text><Title level={3}>Favourites</Title></div><Tag>Browser-local</Tag></div>
            <Paragraph type="secondary">Pins live in this browser's storage; they do not change Ren'Py's native watchlist.</Paragraph>
            {favourites.length === 0 ? <Empty description="Select a variable and click Pin" /> :
              <div className="favourites-list">{favourites.map((favorite) => {
                const node = flatten(snapshot?.scopes?.[favorite.scope] ?? []).get(favorite.key);
                return <Card key={`${favorite.scope}:${favorite.key}`} className="favourite-card" size="small" onClick={() => selectNode(favorite.key, favorite.scope)}>
                  <Space direction="vertical" size={2}><Text strong>{node?.name ?? 'Temporarily unavailable'}</Text><Text type="secondary" className="monospace">{node?.path ?? favorite.key}</Text></Space>
                  <Tag color={node ? 'cyan' : 'default'}>{node?.preview ?? 'Missing'}</Tag>
                </Card>;
              })}</div>}
          </div>}
          {tab === 'overview' && <div className="content-inner">
            <Text className="eyebrow">RUNTIME STATUS</Text><Title level={3}>Overview</Title>
            <div className="stat-grid"><Card><Statistic title="Store entries" value={snapshot?.counts?.store ?? 0}/></Card>
              <Card><Statistic title="Persistent entries" value={snapshot?.counts?.persistent ?? 0}/></Card>
              <Card><Statistic title="Browser watches" value={favourites.length}/></Card></div>
            <Card className="detail-card" title="Active session"><Descriptions column={1} size="middle" items={[
              { key: 'game', label: 'Game', children: snapshot?.game?.game || 'Unavailable' },
              { key: 'version', label: "Ren'Py", children: snapshot?.game?.version || 'Unavailable' },
              { key: 'time', label: 'Last capture', children: formatTime(snapshot?.captured_at) },
              { key: 'mode', label: 'Access', children: 'Read-only · local authenticated API' },
            ]} /></Card>
          </div>}
          <div className="connection-banner">
            <Space><ThunderboltOutlined /><Text type="secondary">{status === 'online' ? `Live snapshot · ${formatTime(snapshot?.captured_at)}` :
              status === 'unpaired' ? 'Not paired. Open this page from the game’s Settings tab.' : error || 'Connecting to game...'}</Text></Space>
            {status !== 'online' && <Tag color="orange">{status}</Tag>}
          </div>
        </Content>
      </Layout>
    </Layout>
  </ConfigProvider>;
}
