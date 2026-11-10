import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button, Card, ConfigProvider, Descriptions, Drawer, Empty, Input, Popover,
  Spin, Statistic, Tabs, Tag, Tooltip, Tree, Typography, theme,
} from 'antd';
import {
  CheckCircleFilled, CopyOutlined, DisconnectOutlined,
  EyeOutlined, RightOutlined, DownOutlined, SearchOutlined,
  StarFilled, StarOutlined,
} from '@ant-design/icons';
import {
  asVirtualTreeNodes, decodeTreeKey, flatten, filteredTree, favouriteNodes,
  integrateChildPage, keysOf, mergeRootSnapshot, readBridgeFragment, refreshWatchedPage,
  safeFavourites,
} from './tree.js';
import {
  collectWatchedPages, nextWatchBatch, WATCH_INTERVAL_MS,
} from './watch.js';

const { Text, Title, Paragraph } = Typography;
const initialConnection = readBridgeFragment(window.location.hash);
const FAVORITES_KEY = 'renpy-inspector-ant-favourites-v1';
const SNAPSHOT_REFRESH_MS = 1250;
const CHILD_PAGE_SIZE = 80;
const MAX_CLIENT_TREE_NODES = 6000;
function countNodes(nodes) {
  let total = 0;
  const stack = [...(nodes || [])];
  while (stack.length) {
    const node = stack.pop();
    total += 1;
    if (total > MAX_CLIENT_TREE_NODES) return total;
    for (const child of node.children || []) stack.push(child);
  }
  return total;
}
function pageRequestId(scope, parent, offset, generation) {
  // In-flight requests from a previous game load must not poison new pages.
  return JSON.stringify([generation, scope, parent, offset]);
}
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


/** Ant Design virtualises these sentinels: they mount only near the viewport.
 * When one is visible, request the next bounded page. No Load More click needed.
 * A manual retry control is available only when the request fails.
 */
function AutoPageSentinel({ scope, offset, loading, error, requestPage }) {
  const spanRef = useRef(null);
  const triggerRef = useRef(requestPage);
  triggerRef.current = requestPage;
  useEffect(() => {
    const element = spanRef.current;
    if (!element || loading || error) return undefined;
    if (!('IntersectionObserver' in window)) {
      triggerRef.current();
      return undefined;
    }
    const root = element.closest('.ant-tree-list-holder');
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) triggerRef.current();
    }, { root, rootMargin: '160px 0px 160px 0px' });
    observer.observe(element);
    return () => observer.disconnect();
  }, [offset, loading, error]);
  return <span ref={spanRef} className="auto-page-sentinel" aria-live="polite">
    {error ? <button type="button" onClick={() => triggerRef.current()}>
      Could not load · Retry</button> : loading ? 'Loading more…' : 'More entries below…'}
  </span>;
}

function TreeRow({ node, isFavourite, isActive, onToggle, onDetails, onFavourite }) {
  const canExpand = Boolean(node.expandable || node.children?.length) && typeof onToggle === 'function';
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

function VariablePane({ scope, treePages, query, favourites, selected, onSelect, onFavourite,
  expanded, onExpand, onRequestPage, loadingPages, pageErrors }) {
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
    ? favouriteNodes(treePages?.scopes, favourites)
    : treePages?.scopes?.[scope] ?? [], [scope, treePages, favourites]);
  const visible = useMemo(() => filteredTree(nodes, query), [nodes, query]);
  const favKeys = useMemo(() => new Set(favourites.map((x) => `${x.scope}:${x.key}`)), [favourites]);
  const hasQuery = Boolean(query.trim());
  const expandedKeys = hasQuery ? keysOf(visible) : expanded[scope] ?? [];
  const expandedSet = new Set(expandedKeys);
  const treeData = useMemo(() => {
    if (scope === 'favourites') return asVirtualTreeNodes(visible, scope, {}, false);
    return asVirtualTreeNodes(visible, scope, treePages?.roots, !hasQuery);
  }, [visible, scope, treePages?.roots, hasQuery]);

  return <section className="variable-pane" aria-label="Variable tree workspace">
    <div ref={viewportRef} className="variable-tree-viewport">
      {treeData.length ? <Tree
        className="full-width-variable-tree" blockNode showLine={{ showLeafIcon: false }}
        switcherIcon={({ expanded: isExpanded }) => isExpanded ? <DownOutlined /> : <RightOutlined />}
        selectable={false} virtual height={height}
        treeData={treeData} expandedKeys={expandedKeys} autoExpandParent={hasQuery}
        onExpand={(next, details) => {
          if (hasQuery) return;
          onExpand(scope, next);
          if (details.expanded && scope !== 'favourites') {
            const found = flatten(treePages?.scopes?.[scope] ?? []).get(details.node.key);
            if (found?.expandable && !found.loaded) onRequestPage(scope, found.key, 0);
          }
        }}
        titleRender={(raw) => {
          const node = raw;
          if (node.isLoadMore) {
            const requestId = pageRequestId(node.scope, node.parentKey, node.nextOffset, treePages?.generation);
            return <AutoPageSentinel scope={node.scope} offset={node.nextOffset}
              loading={loadingPages.has(requestId)} error={pageErrors[requestId]}
              requestPage={() => onRequestPage(node.scope, node.parentKey, node.nextOffset)} />;
          }
          const originScope = scope === 'favourites' ? node.favouriteScope : scope;
          const sourceKey = node.sourceKey ?? node.key;
          const pinned = favKeys.has(`${originScope}:${sourceKey}`);
          return <TreeRow node={{ ...node, expanded: expandedSet.has(node.key) }}
            isFavourite={pinned}
            isActive={selected?.scope === originScope && selected?.key === sourceKey}
            onToggle={hasQuery ? undefined : () => {
              const opening = !expandedSet.has(node.key);
              onExpand(scope, opening
                ? [...expandedKeys, node.key]
                : expandedKeys.filter((key) => key !== node.key));
              if (opening && scope !== 'favourites' && node.expandable && !node.loaded) {
                onRequestPage(scope, node.key, 0);
              }
            }}
            onDetails={() => onSelect(originScope, sourceKey)}
            onFavourite={() => onFavourite(originScope, sourceKey)} />;
        }} /> :
        <Empty className="empty-variables" description={hasQuery ? 'No captured variables match this search' :
          scope === 'favourites' ? 'Pin variables using the star on a tree row' : 'No variables captured'} />}
    </div>
  </section>;
}

export default function App() {
  const [token] = useState(initialConnection.token);
  const [bridge] = useState(initialConnection.bridge || window.location.origin);
  const [snapshot, setSnapshot] = useState(null);
  const [treePages, setTreePages] = useState(null);
  const treePagesRef = useRef(null);
  const watchJobsRef = useRef([]);
  const watchCursorRef = useRef(0);
  const loadingRef = useRef(new Set());
  const [loadingPages, setLoadingPages] = useState(new Set());
  const [pageErrors, setPageErrors] = useState({});
  const [connection, setConnection] = useState(token ? 'connecting' : 'unpaired');
  const [error, setError] = useState('');
  const [section, setSection] = useState('variables');
  const [scope, setScope] = useState('store');
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef(null);
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
          setSnapshot(data);
          setTreePages((prior) => {
            const next = mergeRootSnapshot(prior, data);
            treePagesRef.current = next;
            return next;
          });
          setConnection('online'); setError('');
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
  }, [token, bridge]);

  const requestPage = useCallback(async (chosenScope, parentKey, offset, options = {}) => {
    const { refresh = false, quiet = false } = options;
    if (!token || !['store', 'persistent'].includes(chosenScope)) return;
    const previous = treePagesRef.current;
    if (!previous) return;
    const pageId = pageRequestId(chosenScope, parentKey, offset, previous.generation);
    if (loadingRef.current.has(pageId)) return;
    const decoded = parentKey === null ? null : decodeTreeKey(parentKey);
    if (parentKey !== null && decoded?.scope !== chosenScope) return;
    const path = parentKey === null ? [] : decoded?.path;
    if (!path) return;
    const count = countNodes(previous.scopes?.store) +
      countNodes(previous.scopes?.persistent);
    if (!refresh && count >= MAX_CLIENT_TREE_NODES) {
      setPageErrors((before) => ({
        ...before, [pageId]: 'Client-side display limit reached',
      }));
      return;
    }
    loadingRef.current.add(pageId);
    setLoadingPages(new Set(loadingRef.current));
    if (!quiet) setPageErrors((before) => {
      const next = { ...before };
      delete next[pageId];
      return next;
    });
    try {
      const params = new URLSearchParams({
        scope: chosenScope, path: JSON.stringify(path),
        offset: String(offset), size: String(CHILD_PAGE_SIZE),
      });
      const response = await fetch(bridge + '/api/v1/children?' + params, {
        headers: { 'X-Inspector-Token': token }, method: 'GET',
        cache: 'no-store', mode: 'cors',
      });
      if (!response.ok) {
        throw new Error(response.status === 409 ? 'Game state changed' :
          response.status === 503 ? 'Game interaction paused' :
          response.status === 429 ? 'Request queue busy' :
          'Page fetch HTTP ' + response.status);
      }
      const data = await response.json();
      setTreePages((prior) => {
        const next = refresh
          ? refreshWatchedPage(prior, data, parentKey, CHILD_PAGE_SIZE)
          : integrateChildPage(prior, data, parentKey);
        treePagesRef.current = next;
        return next;
      });
    } catch (reason) {
      if (!quiet && treePagesRef.current?.generation === previous.generation) {
        setPageErrors((before) => ({
          ...before, [pageId]: reason.message || 'Page unavailable',
        }));
      }
    } finally {
      loadingRef.current.delete(pageId);
      setLoadingPages(new Set(loadingRef.current));
    }
  }, [bridge, token]);

  // One scheduler for all expanded tree watches and independent favourites.
  // Never allocate a timer per virtualised row; browser/viewport changes only
  // change the current watch plan, not the shared scheduler's lifetime.
  const watchJobs = useMemo(() => collectWatchedPages(
    treePages, expanded, scope, section, favourites,
  ), [treePages, expanded, scope, section, favourites]);
  watchJobsRef.current = watchJobs;
  useEffect(() => {
    if (connection !== 'online') return undefined;
    const timer = window.setInterval(() => {
      const batch = nextWatchBatch(watchJobsRef.current, watchCursorRef.current);
      watchCursorRef.current = batch.next;
      for (const job of batch.jobs) {
        requestPage(job.scope, job.parentKey, job.offset,
          { refresh: true, quiet: true });
      }
    }, WATCH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [connection, requestPage]);

  useEffect(() => { setPageErrors({}); }, [treePages?.generation]);

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
    return flatten(treePages?.scopes?.[selected.scope] ?? []).get(selected.key) || null;
  }, [treePages, selected]);
  const selectedPinned = Boolean(selected && favourites.some((x) => x.scope === selected.scope && x.key === selected.key));
  const activeGame = snapshot?.game ?? {};
  const online = connection === 'online';
  useEffect(() => {
    if (!searchOpen) return;
    const frame = window.requestAnimationFrame(() => searchRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [searchOpen]);
  useEffect(() => {
    const shortcut = (event) => {
      const element = event.target;
      if (event.key !== '/' || event.ctrlKey || event.altKey || event.metaKey ||
        element?.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(element?.tagName || '')) return;
      event.preventDefault();
      setSection('variables');
      setSearchOpen(true);
    };
    document.addEventListener('keydown', shortcut);
    return () => document.removeEventListener('keydown', shortcut);
  }, []);

  return <ConfigProvider theme={{ algorithm: [theme.darkAlgorithm, theme.compactAlgorithm], token: {
    colorPrimary: '#5b9ff3', colorBgBase: '#0e1726', colorText: '#e8eef9',
    fontSize: 13, borderRadius: 7,
  } }}>
    <div className="inspector-shell">
      <Tabs className="main-navigation" activeKey={section} onChange={setSection}
        items={[{ key: 'overview', label: 'Overview' }, { key: 'variables', label: 'Variables' }, { key: 'scripts', label: 'Scripts' }]} />
      <main className="inspector-main">
        {section === 'variables' && <div className="variables-workspace">
          <Tabs className="variable-scope-tabs" activeKey={scope} onChange={setScope}
            tabBarExtraContent={<Popover placement="bottomRight" trigger="click" open={searchOpen}
              onOpenChange={setSearchOpen}
              content={<div className="search-popover" role="search">
                <Input ref={searchRef} prefix={<SearchOutlined />} allowClear size="middle"
                  aria-label="Search captured variables" placeholder="Search captured variables"
                  value={query} onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape' || event.key === 'Enter') {
                      event.stopPropagation();
                      if (event.key === 'Escape') event.preventDefault();
                      setSearchOpen(false);
                    }
                  }} />
                <Text type="secondary" className="search-hint">Filters captured nodes · Esc to close</Text>
              </div>}>
              <Tooltip title={query ? 'Search active: ' + query : 'Search variables'}>
                <Button className={query ? 'search-trigger search-trigger-active' : 'search-trigger'}
                  icon={<SearchOutlined />} size="small" type="text"
                  aria-label={query ? 'Search variables (filter active)' : 'Search variables'}
                  aria-expanded={searchOpen} />
              </Tooltip>
            </Popover>}
            items={[{ key: 'store', label: 'Store' }, { key: 'persistent', label: 'Persistent' },
              { key: 'favourites', label: `Favourites (${favourites.length})` }]} />
          <VariablePane scope={scope} treePages={treePages} query={query} favourites={favourites}
            selected={selected} onSelect={selectNode} onFavourite={pinVariable}
            expanded={expanded} onExpand={onExpanded} onRequestPage={requestPage}
            loadingPages={loadingPages} pageErrors={pageErrors} />
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
              { key: 'version', label: 'Inspector', children: 'External workspace · v0.6.1 preview' },
              { key: 'connection', label: 'Connection', children: <span className="overview-connection">
                {online ? <CheckCircleFilled style={{ color: '#57d5a5' }} /> :
                  connection === 'connecting' ? <Spin size="small" /> :
                    <DisconnectOutlined style={{ color: '#ff9b81' }} />}
                {online ? 'Connected' : connection === 'connecting' ? 'Connecting' : 'Disconnected'}
              </span> },
              ...(error ? [{ key: 'error', label: 'Connection error', children: error }] : []),
              { key: 'capture', label: 'Last capture', children: captureTime(snapshot?.captured_at) },
              { key: 'mode', label: 'Access', children: 'Read-only · authenticated local session · automatic updates' },
              { key: 'budget', label: 'Capture limits', children:
                '80 per page · up to 1,000 per branch · 8 levels · 6,000 loaded nodes per browser' },
              { key: 'coverage', label: 'Coverage', children: snapshot?.truncated?.store || snapshot?.truncated?.persistent ?
                'Partial snapshot. Some branches are not included.' : 'Within configured snapshot limits' },
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
          <Paragraph type="secondary" className="detail-disclaimer">
            This is a bounded, read-only snapshot preview. Expand branches and scroll to request additional pages.
            Full string values and unrestricted Python objects are not exposed.
          </Paragraph>
        </>}
      </Drawer>
    </div>
  </ConfigProvider>;
}
