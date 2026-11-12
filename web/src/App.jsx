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
  integrateChildPage, integrateRevealChain, keysOf, mergeRootSnapshot,
  readBridgeFragment, refreshWatchedPage, revealParentKeys, safeFavourites,
} from './tree.js';
import {
  collectWatchedPages, combineScopedWatches, nextWatchBatch, WATCH_INTERVAL_MS,
} from './watch.js';
import { createChangeTracker, comparisonText } from './comparison.js';
import { classifyGeneration } from './lifecycle.js';
import ScriptPane from './ScriptPane.jsx';

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

function VariablePane({ scope, treePages, watchValues, query, favourites, selected, onSelect, onFavourite,
  expanded, onExpand, onRequestPage, loadingPages, pageErrors, revealTarget }) {
  const viewportRef = useRef(null);
  const treeRef = useRef(null);
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
    ? favouriteNodes(treePages?.scopes, favourites, watchValues)
    : treePages?.scopes?.[scope] ?? [], [scope, treePages, favourites, watchValues]);
  const visible = useMemo(() => filteredTree(nodes, query), [nodes, query]);
  const favKeys = useMemo(() => new Set(favourites.map((x) => `${x.scope}:${x.key}`)), [favourites]);
  const hasQuery = Boolean(query.trim());
  const expandedKeys = hasQuery ? keysOf(visible) : expanded[scope] ?? [];
  const expandedSet = new Set(expandedKeys);
  const treeData = useMemo(() => {
    if (scope === 'favourites') return asVirtualTreeNodes(visible, scope, {}, false);
    return asVirtualTreeNodes(visible, scope, treePages?.roots, !hasQuery);
  }, [visible, scope, treePages?.roots, hasQuery]);

  useEffect(() => {
    if (revealTarget?.scope !== scope || !treeRef.current) return undefined;
    const frame = window.requestAnimationFrame(() =>
      treeRef.current?.scrollTo?.({ key: revealTarget.key }));
    return () => window.cancelAnimationFrame(frame);
  }, [revealTarget, scope, height]);

  return <section className="variable-pane" aria-label="Variable tree workspace">
    <div ref={viewportRef} className="variable-tree-viewport">
      {treeData.length ? <Tree
        ref={treeRef} className="full-width-variable-tree" blockNode showLine={{ showLeafIcon: false }}
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
            isActive={(selected?.scope === originScope && selected?.key === sourceKey) ||
              (revealTarget?.scope === originScope && revealTarget?.key === sourceKey)}
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

/** History has its own workspace; it never consumes height in the tree tab. */
function ComparePane({ changes, onClear, onInspect }) {
  return <section className="compare-workspace" aria-label="Variable change comparison">
    <div className="compare-toolbar">
      <Text type="secondary" className="compare-description">
        Read-only observed primitive previews · last 100 changes in this browser session.
        Only sampled paths are compared. Save/load resets the history.
      </Text>
      <Button size="small" disabled={!changes.length} onClick={onClear}>Clear history</Button>
    </div>
    <div className="compare-list" role="region" aria-label="Observed variable changes">
      {changes.length ? changes.map((change) =>
        <article className="compare-entry" key={change.id}>
          <div className="compare-entry-title">
            <Text className="compare-path" title={change.path}>{change.path}</Text>
            <Tag color={change.kind === 'added' ? 'green' :
              change.kind === 'removed' ? 'volcano' : 'blue'}>{change.kind}</Tag>
          </div>
          <div className="compare-context">
            <Text type="secondary">
              {new Date(change.capturedAt * 1000).toLocaleTimeString()}
              {change.context.filename ? ' · ' + change.context.filename : ''}
              {change.context.line !== null ? ':' + change.context.line : ''}
            </Text>
          </div>
          <div className="compare-values">
            <div><Text type="secondary">Before</Text>
              <code>{comparisonText(change.before)}</code></div>
            <div><Text type="secondary">After</Text>
              <code>{comparisonText(change.after)}</code></div>
          </div>
          <Button type="link" size="small" className="compare-inspect"
            onClick={() => onInspect(change)}>Inspect variable</Button>
        </article>) :
        <Empty className="compare-empty"
          description="No sampled changes yet. Expand branches or pin values to watch them." />}
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
  const [lastTreeScope, setLastTreeScope] = useState('store');
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef(null);
  const [searchMatches, setSearchMatches] = useState({
    query: '', items: [], limited: false, scanned: 0, busy: false, error: '',
  });
  const [revealBusy, setRevealBusy] = useState(false);
  const [revealTarget, setRevealTarget] = useState(null);
  const [revealError, setRevealError] = useState('');
  const revealCounterRef = useRef(0);
  const [selected, setSelected] = useState(null);
  const [expanded, setExpanded] = useState({ store: [], persistent: [], favourites: [] });
  const [favourites, setFavourites] = useState(loadLocalFavourites);
  const [favouritesReady, setFavouritesReady] = useState(false);
  const [preferencesStatus, setPreferencesStatus] = useState('Connecting');
  const preferenceWritesRef = useRef(Promise.resolve());
  const [watchValues, setWatchValues] = useState({});
  const valueLoadingRef = useRef(new Set());
  const trackerRef = useRef(createChangeTracker());
  const gameContextRef = useRef({});
  const [changes, setChanges] = useState([]);
  const publishChanges = useCallback(() => {
    setChanges(trackerRef.current.getChanges());
  }, []);
  const requestCounter = useRef(0);

  useEffect(() => {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(favourites)); } catch { /* private browsing */ }
  }, [favourites]);

  // Server preferences are per game, not per localhost port. Only import the
  // browser's old localStorage pins once if no server preference file exists.
  useEffect(() => {
    if (!token) { setPreferencesStatus('Not paired'); return undefined; }
    let disposed = false;
    const bootstrap = async () => {
      try {
        const response = await fetch(bridge + '/api/v1/favourites', {
          headers: { 'X-Inspector-Token': token }, cache: 'no-store', mode: 'cors',
        });
        if (!response.ok) throw new Error('Inspector storage HTTP ' + response.status);
        const data = await response.json();
        if (!disposed) {
          setFavourites(data.initialized
            ? safeFavourites(data.favourites)
            : loadLocalFavourites());
          setFavouritesReady(true);
          setPreferencesStatus('Inspector save directory');
        }
      } catch (failure) {
        if (!disposed) setPreferencesStatus('Local only: ' + (failure.message || 'Storage unavailable'));
      }
    };
    bootstrap();
    return () => { disposed = true; };
  }, [token, bridge]);

  // Serialize/debounce preference writes to prevent a slow earlier request
  // from overwriting a later pin/unpin. Never write gameplay variables.
  useEffect(() => {
    if (!favouritesReady || !token) return undefined;
    const timer = window.setTimeout(() => {
      const entries = safeFavourites(favourites);
      preferenceWritesRef.current = preferenceWritesRef.current.catch(() => {}).then(async () => {
        const response = await fetch(bridge + '/api/v1/favourites', {
          method: 'PUT', mode: 'cors',
          headers: { 'X-Inspector-Token': token, 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: 1, favourites: entries }),
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        setPreferencesStatus('Inspector save directory');
      }).catch((failure) => {
        setPreferencesStatus('Local only: ' + (failure.message || 'Write failed'));
      });
    }, 200);
    return () => window.clearTimeout(timer);
  }, [favourites, favouritesReady, token, bridge]);

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
          const transition = classifyGeneration(treePagesRef.current?.generation, data.generation);
          if (transition === 'invalid' || transition === 'stale') return;
          if (transition === 'new') {
            // Discard browser-only state attached to the previous game epoch.
            // Favourites are typed paths and deliberately survive to re-resolve.
            setSelected(null);
            setExpanded({ store: [], persistent: [], favourites: [] });
            setWatchValues({});
            loadingRef.current.clear();
            setLoadingPages(new Set());
            valueLoadingRef.current.clear();
            watchCursorRef.current = 0;
            setPageErrors({});
            setRevealTarget(null);
            setRevealError('');
            setSearchOpen(false);
            setQuery('');
            setSearchMatches({
              query: '', items: [], limited: false, scanned: 0, busy: false, error: '',
            });
          }
          gameContextRef.current = data.game ?? {};
          trackerRef.current.beginGeneration(data.generation);
          if (Number.isFinite(data.captured_at)) {
            for (const observedScope of ['store', 'persistent']) {
              trackerRef.current.observePage({
                scope: observedScope, parentKey: null, offset: 0,
                items: data.scopes[observedScope] ?? [],
                more: Boolean(data.root_pages?.[observedScope]?.more),
                generation: data.generation, capturedAt: data.captured_at,
                game: gameContextRef.current,
              });
            }
          }
          publishChanges();
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
  }, [token, bridge, publishChanges]);

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
      if (data.generation === previous.generation &&
          data.generation === treePagesRef.current?.generation) {
        trackerRef.current.observePage({
          scope: chosenScope, parentKey, offset, items: data.items,
          more: Boolean(data.more), generation: data.generation,
          capturedAt: data.captured_at, game: gameContextRef.current,
        });
        publishChanges();
      }
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
  }, [bridge, token, publishChanges]);

  const requestFavouriteValue = useCallback(async (job) => {
    if (!token || !job) return;
    const decoded = decodeTreeKey(job.key);
    if (!decoded || decoded.scope !== job.scope || !decoded.path.length) return;
    const expectedGeneration = treePagesRef.current?.generation;
    if (expectedGeneration === undefined) return;
    const requestId = JSON.stringify([expectedGeneration, job.key]);
    if (valueLoadingRef.current.has(requestId)) return;
    valueLoadingRef.current.add(requestId);
    try {
      const params = new URLSearchParams({
        scope: job.scope, path: JSON.stringify(decoded.path),
      });
      const response = await fetch(bridge + '/api/v1/value?' + params, {
        headers: { 'X-Inspector-Token': token },
        method: 'GET', cache: 'no-store', mode: 'cors',
      });
      if (!response.ok) return;
      const result = await response.json();
      if (result.generation !== treePagesRef.current?.generation ||
          expectedGeneration !== result.generation ||
          result.node?.key !== job.key) return;
      trackerRef.current.observeValue({
        scope: job.scope, node: result.node, generation: result.generation,
        capturedAt: result.captured_at, game: gameContextRef.current,
      });
      publishChanges();
      setWatchValues((old) => {
        if (treePagesRef.current?.generation !== expectedGeneration) return old;
        const before = old[job.key];
        const node = result.node;
        if (before && before.preview === node.preview && before.type === node.type &&
            before.state === node.state && before.expandable === node.expandable) return old;
        return { ...old, [job.key]: node };
      });
    } catch { /* A missing/paused game watch retries on the next scheduler turn. */ }
    finally { valueLoadingRef.current.delete(requestId); }
  }, [bridge, token, publishChanges]);

  // One scheduler for all expanded tree watches and independent favourites.
  // Never allocate a timer per virtualised row; browser/viewport changes only
  // change the current watch plan, not the shared scheduler's lifetime.
  const watchJobs = useMemo(() => combineScopedWatches(
    collectWatchedPages(treePages, expanded,
      scope === 'compare' ? lastTreeScope : scope, section, favourites),
    favourites,
  ), [treePages, expanded, scope, lastTreeScope, section, favourites]);
  watchJobsRef.current = watchJobs;
  useEffect(() => {
    if (connection !== 'online') return undefined;
    const timer = window.setInterval(() => {
      const batch = nextWatchBatch(watchJobsRef.current, watchCursorRef.current);
      watchCursorRef.current = batch.next;
      for (const job of batch.jobs) {
        if (job.kind === 'value') requestFavouriteValue(job);
        else requestPage(job.scope, job.parentKey, job.offset,
          { refresh: true, quiet: true });
      }
    }, WATCH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [connection, requestPage, requestFavouriteValue]);

  useEffect(() => {
    setPageErrors({});
    setWatchValues({});
  }, [treePages?.generation]);

  // Search is debounced, budgeted on the game thread and cancelled when closed.
  useEffect(() => {
    const term = query.trim();
    if (!searchOpen || section !== 'variables' || !token || term.length < 2) {
      setSearchMatches({ query: term, items: [], limited: false, scanned: 0,
        busy: false, error: '' });
      return undefined;
    }
    let active = true;
    const controller = new AbortController();
    setSearchMatches({ query: term, items: [], limited: false, scanned: 0,
      busy: true, error: '' });
    const timer = window.setTimeout(async () => {
      try {
        const params = new URLSearchParams({ scope: 'all', q: term });
        const response = await fetch(bridge + '/api/v1/search?' + params, {
          method: 'GET', mode: 'cors', cache: 'no-store',
          headers: { 'X-Inspector-Token': token }, signal: controller.signal,
        });
        if (!response.ok) throw new Error(response.status === 503
          ? 'Game is paused. Try again after resuming.'
          : response.status === 429 ? 'Search queue busy. Retry shortly.'
            : 'Search failed (HTTP ' + response.status + ')');
        const result = await response.json();
        if (!active || result.generation !== treePagesRef.current?.generation) return;
        setSearchMatches({
          query: term,
          items: Array.isArray(result.results)
            ? result.results.slice(0, 30).filter((item) => decodeTreeKey(item.key)) : [],
          limited: Boolean(result.limited), scanned: result.scanned ?? 0,
          busy: false, error: '',
        });
      } catch (reason) {
        if (active && reason.name !== 'AbortError') {
          setSearchMatches({ query: term, items: [], limited: false,
            scanned: 0, busy: false, error: reason.message || 'Search unavailable' });
        }
      }
    }, 350);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [query, searchOpen, section, token, bridge, treePages?.generation]);

  const revealResult = useCallback(async (item) => {
    const decoded = decodeTreeKey(item?.key);
    if (!decoded || !token || revealBusy) return;
    const previous = treePagesRef.current;
    if (!previous || !decoded.path.length) return;
    setRevealBusy(true);
    setRevealError('');
    try {
      const params = new URLSearchParams({
        scope: decoded.scope, path: JSON.stringify(decoded.path),
      });
      const response = await fetch(bridge + '/api/v1/reveal?' + params, {
        method: 'GET', mode: 'cors', cache: 'no-store',
        headers: { 'X-Inspector-Token': token },
      });
      if (!response.ok) throw new Error(response.status === 404
        ? 'Variable is no longer available in the current game state.'
        : response.status === 503 ? 'Game paused. Resume and retry.'
          : 'Could not reveal variable (HTTP ' + response.status + ')');
      const data = await response.json();
      if (data.generation !== previous.generation ||
          data.generation !== treePagesRef.current?.generation ||
          data.key !== item.key || data.scope !== decoded.scope) {
        throw new Error('Game state changed. Search again.');
      }
      setTreePages((old) => {
        const next = integrateRevealChain(old, data);
        treePagesRef.current = next;
        return next;
      });
      setExpanded((old) => ({
        ...old, [decoded.scope]: Array.from(
          new Set([...(old[decoded.scope] ?? []), ...revealParentKeys(data)])),
      }));
      setLastTreeScope(decoded.scope);
      setScope(decoded.scope);
      setSection('variables');
      setSelected(null);
      setRevealTarget({ scope: decoded.scope, key: item.key,
        request: ++revealCounterRef.current });
      setSearchOpen(false);
      setQuery('');
    } catch (reason) {
      setRevealError(reason.message || 'Reveal unavailable');
    } finally { setRevealBusy(false); }
  }, [bridge, token, revealBusy]);

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
    const captured = flatten(treePages?.scopes?.[selected.scope] ?? []).get(selected.key);
    return watchValues[selected.key] || captured || null;
  }, [treePages, selected, watchValues]);
  const selectedPinned = Boolean(selected && favourites.some((x) => x.scope === selected.scope && x.key === selected.key));
  const selectedHistory = selected ? changes.filter((entry) => entry.key === selected.key).slice(0, 20) : [];
  const inspectChange = useCallback((change) => {
    const parsed = decodeTreeKey(change.key);
    if (!parsed || parsed.scope !== change.scope) return;
    setSelected({ scope: change.scope, key: change.key });
    requestFavouriteValue({ scope: change.scope, key: change.key });
  }, [requestFavouriteValue]);
  const clearHistory = useCallback(() => {
    trackerRef.current.clear();
    publishChanges();
  }, [publishChanges]);
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
          <Tabs className="variable-scope-tabs" activeKey={scope}
            onChange={(next) => {
              if (next === 'store' || next === 'persistent') setLastTreeScope(next);
              setScope(next);
            }}
            tabBarExtraContent={<Popover placement="bottomRight" trigger="click" open={searchOpen}
              onOpenChange={setSearchOpen}
              content={<div className="search-popover" role="search">
                <Input ref={searchRef} prefix={<SearchOutlined />} allowClear size="middle"
                  aria-label="Search variables across Store and Persistent"
                  placeholder="Search variable names or paths"
                  value={query} onChange={(event) => {
                    setQuery(event.target.value);
                    setRevealError('');
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      event.stopPropagation(); event.preventDefault(); setSearchOpen(false);
                    } else if (event.key === 'Enter' &&
                      searchMatches.query === query.trim() && searchMatches.items.length) {
                      event.stopPropagation(); event.preventDefault();
                      revealResult(searchMatches.items[0]);
                    }
                  }} />
                <Text type="secondary" className="search-hint">
                  Global bounded search · type at least two characters · Esc to close
                </Text>
                {query.trim().length >= 2 && <div className="remote-search-results"
                  role="listbox" aria-label="Matching game variables">
                  {searchMatches.busy && <div className="remote-search-status">
                    <Spin size="small" /> Searching game state…</div>}
                  {!searchMatches.busy && searchMatches.error &&
                    <Text type="danger">{searchMatches.error}</Text>}
                  {!searchMatches.busy && searchMatches.query === query.trim() &&
                    searchMatches.items.map((match) =>
                      <button type="button" className="remote-search-hit"
                        role="option" aria-selected={false} key={match.key}
                        disabled={revealBusy} onClick={() => revealResult(match)}>
                        <span className="remote-search-path">{match.path}</span>
                        <span className="remote-search-preview">{match.type} · {match.preview}</span>
                      </button>)}
                  {!searchMatches.busy && !searchMatches.error &&
                    searchMatches.query === query.trim() && !searchMatches.items.length &&
                    <Text type="secondary">No matches within the search budget.</Text>}
                  {searchMatches.limited && <Text type="secondary" className="remote-search-warning">
                    Partial results: depth, traversal and result counts are bounded.
                    Narrow the term or expand a likely branch.
                  </Text>}
                  {revealError && <Text type="danger" role="alert">{revealError}</Text>}
                </div>}
              </div>}>
              <Tooltip title={query ? 'Search active: ' + query : 'Search variables'}>
                <Button className={query ? 'search-trigger search-trigger-active' : 'search-trigger'}
                  icon={<SearchOutlined />} size="small" type="text"
                  aria-label={query ? 'Search variables (filter active)' : 'Search variables'}
                  aria-expanded={searchOpen} />
              </Tooltip>
            </Popover>}
            items={[{ key: 'store', label: 'Store' }, { key: 'persistent', label: 'Persistent' },
              { key: 'favourites', label: `Favourites (${favourites.length})` },
              { key: 'compare', label: `Compare (${changes.length})` }]} />
          {scope === 'compare'
            ? <ComparePane changes={changes} onClear={clearHistory} onInspect={inspectChange} />
            : <VariablePane scope={scope} treePages={treePages} watchValues={watchValues}
                query={query} favourites={favourites}
                selected={selected} onSelect={selectNode} onFavourite={pinVariable}
                expanded={expanded} onExpand={onExpanded} onRequestPage={requestPage}
                loadingPages={loadingPages} pageErrors={pageErrors}
                revealTarget={revealTarget} />}
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
              { key: 'version', label: 'Inspector', children: 'External workspace · v0.6.8 preview' },
              { key: 'connection', label: 'Connection', children: <span className="overview-connection">
                {online ? <CheckCircleFilled style={{ color: '#57d5a5' }} /> :
                  connection === 'connecting' ? <Spin size="small" /> :
                    <DisconnectOutlined style={{ color: '#ff9b81' }} />}
                {online ? 'Connected' : connection === 'connecting' ? 'Connecting' : 'Disconnected'}
              </span> },
              ...(error ? [{ key: 'error', label: 'Connection error', children: error }] : []),
              { key: 'capture', label: 'Last capture', children: captureTime(snapshot?.captured_at) },
              { key: 'mode', label: 'Access', children: 'Game state read-only · authenticated local session' },
              { key: 'preferences', label: 'Favourite storage', children: preferencesStatus },
              { key: 'watches', label: 'Favourites', children:
                'Independent path watches · read-only values · persisted inspector settings' },
              { key: 'compare', label: 'Compare', children:
                'Last 100 observed preview changes · session-only · resets after game load' },
              { key: 'budget', label: 'Capture limits', children:
                '80 per page · up to 1,000 per branch · 8 levels · 6,000 loaded nodes per browser' },
              { key: 'coverage', label: 'Coverage', children: snapshot?.truncated?.store || snapshot?.truncated?.persistent ?
                'Partial snapshot. Some branches are not included.' : 'Within configured snapshot limits' },
            ]} />
          </Card>
        </section>}
        {section === 'scripts' && <ScriptPane token={token} bridge={bridge}
          activeGame={activeGame} generation={treePages?.generation} />}
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
          <div className="detail-history">
            <div className="detail-history-header">
              <Text strong>Observed history</Text>
              <Text type="secondary">{selectedHistory.length} recent changes</Text>
            </div>
            {selectedHistory.length ? selectedHistory.map((change) =>
              <div key={change.id} className="detail-history-entry">
                <Text type="secondary">{new Date(change.capturedAt * 1000).toLocaleTimeString()} · {change.kind}</Text>
                <code>{comparisonText(change.before)} → {comparisonText(change.after)}</code>
              </div>) :
              <Text type="secondary">No sampled changes for this variable yet.</Text>}
          </div>
          <Paragraph type="secondary" className="detail-disclaimer">
            This is a bounded, read-only snapshot preview. Compare records sampled
            previews, not complete values. Expand branches and scroll to request more pages.
          </Paragraph>
        </>}
      </Drawer>
    </div>
  </ConfigProvider>;
}
