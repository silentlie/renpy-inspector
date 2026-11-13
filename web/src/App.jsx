import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button, Card, Checkbox, ConfigProvider, Descriptions, Drawer, Empty, Input, Popover,
  Select, Spin, Statistic, Tabs, Tag, Tooltip, Tree, Typography, theme,
} from 'antd';
import {
  CheckCircleFilled, CopyOutlined, DisconnectOutlined, LockOutlined,
  EyeOutlined, RightOutlined, DownOutlined, SearchOutlined,
  StarFilled, StarOutlined, WarningOutlined,
} from '@ant-design/icons';
import {
  asVirtualTreeNodes, decodeTreeKey, flatten, filteredTree, favouriteNodes,
  integrateChildPage, integrateRevealChain, keysOf, mergeRootSnapshot,
  readBridgeFragment, refreshWatchedPage, revealParentKeys, safeFavourites,
  staleSample, formatTypedPath, lockIdentity, preserveNewerLockSnapshot,
} from './tree.js';
import {
  collectWatchedPages, combineScopedWatches, nextEligibleWatchBatch,
  WATCH_INTERVAL_MS, MAX_BACKGROUND_IN_FLIGHT,
} from './watch.js';
import { createChangeTracker, comparisonText, filterChanges } from './comparison.js';
import { classifyGeneration } from './lifecycle.js';
import ScriptPane from './ScriptPane.jsx';
import RuntimePane from './RuntimePane.jsx';
import FullValuePanel from './FullValuePanel.jsx';
import EditValuePanel from './EditValuePanel.jsx';
import EditHistoryPane from './EditHistoryPane.jsx';
import LockedVariablesPane from './LockedVariablesPane.jsx';
import { parseExactPath } from './exact-path.js';
import { sourceTargetForContext } from './scripts.js';
import { valuePresentation } from './value-format.js';

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

function TreeRow({ node, isFavourite, isActive, isLocked, isLockStale, onToggle, onDetails, onFavourite }) {
  const canExpand = Boolean(node.expandable || node.children?.length) && typeof onToggle === 'function';
  const displayedType = valuePresentation(node.type, node.state);
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
      <Tooltip title={`${displayedType.category}: ${displayedType.detail}`}><span className="variable-type">{node.type}</span></Tooltip>
      {isLocked && <Tooltip title={isLockStale
        ? 'Stale lock: gameplay changed this path after it was locked. Inspector writes remain blocked.'
        : 'Protected from Inspector edits and Undo/Redo. Game scripts can still change this variable.'}>
        <span className={`variable-lock-indicator${isLockStale ? ' is-stale' : ''}`} role="status"
          aria-label={isLockStale ? 'Stale lock, protected from Inspector writes' : 'Locked against Inspector writes'}>
          <LockOutlined />
        </span>
      </Tooltip>}
      {node.capped && <Tooltip title="Partial collection: some entries are unsupported or exceed inspection limits.">
        <span className="variable-partial-icon" role="status"
          aria-label="Partial collection coverage"><WarningOutlined /></span>
      </Tooltip>}
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
  lockedKeys, staleLockKeys, expanded, onExpand, onRequestPage, loadingPages, pageErrors, revealTarget }) {
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
            isLocked={originScope === 'store' && lockedKeys?.has(lockIdentity(sourceKey))}
            isLockStale={originScope === 'store' && staleLockKeys?.has(lockIdentity(sourceKey))}
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

/** Change comparisons live in the Compare scope, not the variable tree.
 * All controls filter session-only observations without issuing new reads.
 */
function ComparePane({ changes, favourites, focusedKey, onResetFocus,
  onClear, onInspect, onReveal, onOpenSource }) {
  const [search, setSearch] = useState('');
  const [scopeFilter, setScopeFilter] = useState('all');
  const [kindFilter, setKindFilter] = useState('all');
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const [navigationError, setNavigationError] = useState('');
  const visible = useMemo(() => filterChanges(changes, {
    query: search, scope: scopeFilter, kind: kindFilter, favouritesOnly: pinnedOnly,
    favourites, focusKey: focusedKey,
  }), [changes, search, scopeFilter, kindFilter, pinnedOnly, favourites, focusedKey]);
  const focusPath = focusedKey ? formatTypedPath(focusedKey) : '';
  const reveal = async (change) => {
    setNavigationError('');
    const success = await onReveal(change);
    if (!success) setNavigationError(
      'This path is no longer visible in the current game state. Inspect the captured entry instead.');
  };

  return <section className="compare-workspace" aria-label="Variable change comparison">
    <div className="compare-toolbar">
      <Text type="secondary" className="compare-description">
        Last 100 observed changes in this browser session. Exact values are captured
        only for small built-in primitives; other entries are previews. Not every game
        mutation is observed. Save/load resets history.
      </Text>
      <div className="compare-controls">
        <Input allowClear size="small" value={search} maxLength={160}
          aria-label="Filter comparison paths" placeholder="Filter variable paths"
          onChange={(event) => setSearch(event.target.value)} />
        <Select size="small" value={scopeFilter} aria-label="Filter history scope"
          onChange={setScopeFilter} options={[
            { value: 'all', label: 'All scopes' }, { value: 'store', label: 'Store' },
            { value: 'persistent', label: 'Persistent' },
          ]} />
        <Select size="small" value={kindFilter} aria-label="Filter history event type"
          onChange={setKindFilter} options={[
            { value: 'all', label: 'All changes' }, { value: 'changed', label: 'Changed' },
            { value: 'added', label: 'Added' }, { value: 'removed', label: 'Removed' },
          ]} />
        <Checkbox checked={pinnedOnly} onChange={(event) => setPinnedOnly(event.target.checked)}>
          Pinned only
        </Checkbox>
        <Button size="small" disabled={!changes.length} onClick={onClear}>Clear history</Button>
      </div>
      {focusedKey && <div className="compare-focused" role="status">
        <Text type="secondary">History for {focusPath || 'selected variable'}</Text>
        <Button size="small" onClick={onResetFocus}>Show all paths</Button>
      </div>}
      <Text type="secondary" className="compare-count" aria-live="polite">
        {visible.length} of {changes.length} events shown
      </Text>
      {navigationError && <Text type="danger" role="alert">{navigationError}</Text>}
    </div>
    <div className="compare-list" role="region" aria-label="Observed variable changes">
      {visible.length ? visible.map((change) =>
        <article className="compare-entry" key={change.id}>
          <div className="compare-entry-title">
            <Text className="compare-path" title={change.path}>{change.path}</Text>
            <Tag>{change.scope}</Tag>
            <Tag color={change.kind === 'added' ? 'green' :
              change.kind === 'removed' ? 'volcano' : 'blue'}>{change.kind}</Tag>
          </div>
          <div className="compare-context">
            <Text type="secondary">
              Sampled {new Date(change.capturedAt * 1000).toLocaleTimeString()}
              {change.context.filename ? ' · ' + change.context.filename : ''}
              {change.context.line !== null ? ':' + change.context.line : ''}
            </Text>
          </div>
          <div className="compare-values">
            {[['Before', change.before], ['After', change.after]].map(([label, value]) =>
              <div key={label}>
                <Text type="secondary">{label} · {value.precision === 'exact'
                  ? 'exact sampled scalar' : 'preview/status'}</Text>
                <pre className={`compare-sample value-tone-${valuePresentation(value.type, value.kind).tone}`}>{comparisonText(value)}</pre>
              </div>)}
          </div>
          <div className="compare-actions">
            <Button type="link" size="small" className="compare-inspect"
              onClick={() => onInspect(change)}>Inspect variable</Button>
            <Button type="link" size="small" className="compare-inspect"
              onClick={() => reveal(change)}>Reveal in tree</Button>
            {sourceTargetForContext(change.context) && <Button type="link" size="small"
              aria-label="View sampled source" className="compare-inspect"
              title="Location observed when sampled, not proof of a change cause"
              onClick={() => onOpenSource(change.context)}>View sampled source</Button>}
          </div>
        </article>) :
        <Empty className="compare-empty"
          description={changes.length ? 'No changes match these filters.' :
            'No sampled changes yet. Expand branches or pin values to watch them.'} />}
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
  const watchPendingRef = useRef(new Set());
  const loadingRef = useRef(new Set());
  const [loadingPages, setLoadingPages] = useState(new Set());
  const [pageErrors, setPageErrors] = useState({});
  const [connection, setConnection] = useState(token ? 'connecting' : 'unpaired');
  const [error, setError] = useState('');
  const [section, setSection] = useState('variables');
  const [scope, setScope] = useState('store');
  useEffect(() => {
    if ((scope === 'edits' || scope === 'locked') && snapshot?.capabilities?.primitive_edits !== true) {
      setScope('store');
    }
  }, [scope, snapshot?.capabilities?.primitive_edits]);
  const [lastTreeScope, setLastTreeScope] = useState('store');
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef(null);
  const [searchMatches, setSearchMatches] = useState({
    query: '', items: [], limited: false, scanned: 0, busy: false, error: '',
  });
  const exactPath = useMemo(() => parseExactPath(query), [query]);
  const [revealBusy, setRevealBusy] = useState(false);
  const [revealTarget, setRevealTarget] = useState(null);
  const [revealError, setRevealError] = useState('');
  const revealCounterRef = useRef(0);
  const [selected, setSelected] = useState(null);
  const lockedKeys = useMemo(() => new Set((snapshot?.locks?.entries ?? [])
    .map((entry) => lockIdentity(entry.key)).filter((key) => typeof key === 'string')), [snapshot?.locks]);
  const staleLockKeys = useMemo(() => new Set((snapshot?.locks?.entries ?? [])
    .filter((entry) => entry.stale === true)
    .map((entry) => lockIdentity(entry.key)).filter((key) => typeof key === 'string')), [snapshot?.locks]);
  const syncLocks = useCallback((locks) => {
    setSnapshot((current) => {
      if (!current || !locks || !Number.isSafeInteger(locks.revision)) return current;
      if (Number.isSafeInteger(current.locks?.revision) &&
          locks.revision < current.locks.revision) return current;
      return { ...current, locks };
    });
  }, []);
  const [findRequest, setFindRequest] = useState(null);
  const [sourceRequest, setSourceRequest] = useState(null);
  const sourceRequestIdRef = useRef(0);
  const [expanded, setExpanded] = useState({ store: [], persistent: [], favourites: [] });
  const [favourites, setFavourites] = useState(loadLocalFavourites);
  const [favouritesReady, setFavouritesReady] = useState(false);
  const [preferencesStatus, setPreferencesStatus] = useState('Connecting');
  const preferenceWritesRef = useRef(Promise.resolve());
  const [watchValues, setWatchValues] = useState({});
  const valueLoadingRef = useRef(new Set());
  const watchCaptureRef = useRef(new Map());
  const trackerRef = useRef(createChangeTracker());
  const gameContextRef = useRef({});
  const [changes, setChanges] = useState([]);
  const [comparisonFocus, setComparisonFocus] = useState(null);
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
            setComparisonFocus(null);
            setExpanded({ store: [], persistent: [], favourites: [] });
            setWatchValues({});
            loadingRef.current.clear();
            setLoadingPages(new Set());
            valueLoadingRef.current.clear();
            watchCaptureRef.current.clear();
            watchCursorRef.current = 0;
            watchPendingRef.current.clear();
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
          setSnapshot((current) => preserveNewerLockSnapshot(data, current));
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
      // HTTP completion order is not Ren'Py capture order. Do not regress a
      // pinned value after a newer game-thread sample of the same location.
      const previousCapture = watchCaptureRef.current.get(job.key);
      if (staleSample(previousCapture, result.captured_at)) return;
      if (Number.isFinite(result.captured_at)) {
        watchCaptureRef.current.set(job.key, result.captured_at);
      }
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
      (scope === 'compare' || scope === 'edits' || scope === 'locked') ? lastTreeScope : scope, section, favourites),
    favourites,
  ), [treePages, expanded, scope, lastTreeScope, section, favourites]);
  watchJobsRef.current = watchJobs;
  useEffect(() => {
    if (connection !== 'online') return undefined;
    const timer = window.setInterval(() => {
      const generation = treePagesRef.current?.generation;
      if (generation === undefined) return;
      const budget = Math.max(0, MAX_BACKGROUND_IN_FLIGHT - watchPendingRef.current.size);
      const keyFor = (job) => JSON.stringify([generation, job.id]);
      const busy = (job) => watchPendingRef.current.has(keyFor(job)) ||
        (job.kind === 'value'
          ? valueLoadingRef.current.has(JSON.stringify([generation, job.key]))
          : loadingRef.current.has(pageRequestId(
              job.scope, job.parentKey, job.offset, generation)));
      const batch = nextEligibleWatchBatch(
        watchJobsRef.current, watchCursorRef.current, busy, budget);
      watchCursorRef.current = batch.next;
      for (const job of batch.jobs) {
        const id = keyFor(job);
        watchPendingRef.current.add(id);
        const task = job.kind === 'value'
          ? requestFavouriteValue(job)
          : requestPage(job.scope, job.parentKey, job.offset,
            { refresh: true, quiet: true });
        Promise.resolve(task).catch(() => {}).finally(() => {
          watchPendingRef.current.delete(id);
        });
      }
    }, WATCH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [connection, requestPage, requestFavouriteValue]);

  useEffect(() => {
    setPageErrors({});
    setWatchValues({});
    watchCaptureRef.current.clear();
  }, [treePages?.generation]);

  // Search is debounced, budgeted on the game thread and cancelled when closed.
  useEffect(() => {
    const term = query.trim();
    if (!searchOpen || section !== 'variables' || !token || term.length < 2 || exactPath !== null) {
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
  }, [query, exactPath, searchOpen, section, token, bridge, treePages?.generation]);

  const revealResult = useCallback(async (item, exact = false) => {
    const decoded = decodeTreeKey(item?.key);
    if (!decoded || !token || revealBusy) return false;
    const previous = treePagesRef.current;
    if (!previous || !decoded.path.length) return false;
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
        ? exact
          ? 'Exact path not found or not visible. Use .name for object attributes and ["key"] for dictionary entries.'
          : 'Variable is no longer available in the current game state.'
        : response.status === 503 ? 'Game paused. Resume and retry.'
          : 'Could not reveal variable (HTTP ' + response.status + ')');
      const data = await response.json();
      const canonical = decodeTreeKey(data.key);
      if (data.generation !== previous.generation ||
          data.generation !== treePagesRef.current?.generation ||
          data.scope !== decoded.scope ||
          !canonical || JSON.stringify(canonical.path) !== JSON.stringify(decoded.path)) {
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
      // The server may encode non-ASCII keys as \u escapes; use its canonical
      // typed key to match the actual tree node rendered after reveal.
      setRevealTarget({ scope: decoded.scope, key: data.key,
        request: ++revealCounterRef.current });
      setSearchOpen(false);
      setQuery('');
      return true;
    } catch (reason) {
      setRevealError(reason.message || 'Reveal unavailable');
      return false;
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
  const openSourceContext = useCallback((context) => {
    const target = sourceTargetForContext(context);
    if (!target) return;
    // Only one pending navigation intent may be replayed when Scripts mounts.
    // Otherwise an old Find References request overrides (or is overridden by)
    // a newer source request on the next tab switch.
    setFindRequest(null);
    setSourceRequest({ ...target, name: "Observed script location",
      id: ++sourceRequestIdRef.current, generation: treePagesRef.current?.generation });
    setSelected(null);
    setSection("scripts");
  }, []);
  const findReferences = useCallback(() => {
    const decoded = decodeTreeKey(selected?.key);
    if (!decoded?.path?.length) return;
    // Search source for a literal identifier/key, not a semantic read/write
    // graph. Select the nearest meaningful string segment from this path.
    const candidate = [...decoded.path].reverse().find(([kind, value]) =>
      (kind === 'attribute' || kind === 'key') &&
      typeof value === 'string' && value.length >= 2);
    if (!candidate) return;
    setSourceRequest(null);
    setFindRequest({ id: Date.now(), term: candidate[1].slice(0, 64) });
    setSelected(null);
    setSection('scripts');
  }, [selected]);
  const canFindReferences = Boolean(decodeTreeKey(selected?.key)?.path?.some(
    ([kind, value]) => (kind === 'attribute' || kind === 'key') &&
      typeof value === 'string' && value.length >= 2));
  const selectedPinned = Boolean(selected && favourites.some((x) => x.scope === selected.scope && x.key === selected.key));
  const selectedHistory = selected ? changes.filter((entry) => entry.key === selected.key).slice(0, 20) : [];
  const viewSelectedHistory = useCallback(() => {
    if (!selected) return;
    setComparisonFocus(selected.key);
    setSelected(null);
    setSearchOpen(false);
    setQuery('');
    setScope('compare');
  }, [selected]);
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
        items={[{ key: 'overview', label: 'Overview' }, { key: 'variables', label: 'Variables' }, { key: 'scripts', label: 'Scripts' }, { key: 'runtime', label: 'Runtime' }]} />
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
                  placeholder='Search or enter store.player["hp"]'
                  value={query} onChange={(event) => {
                    setQuery(event.target.value);
                    setRevealError('');
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      event.stopPropagation(); event.preventDefault(); setSearchOpen(false);
                    } else if (event.key === 'Enter' && exactPath?.key) {
                      event.stopPropagation(); event.preventDefault();
                      revealResult(exactPath, true);
                    } else if (event.key === 'Enter' &&
                      searchMatches.query === query.trim() && searchMatches.items.length) {
                      event.stopPropagation(); event.preventDefault();
                      revealResult(searchMatches.items[0]);
                    }
                  }} />
                <Text type="secondary" className="search-hint">
                  Search names or enter an exact store/persistent path · Enter to reveal · Esc to close
                </Text>
                {exactPath !== null && <div className="exact-path-results"
                  aria-label="Exact variable path">
                  {exactPath.error
                    ? <Text type="danger" role="alert">{exactPath.error}</Text>
                    : <>
                      <Text type="secondary">Direct typed-path lookup · bypasses the global search budget</Text>
                      <Button size="small" block loading={revealBusy}
                        aria-label="Reveal exact variable path"
                        onClick={() => revealResult(exactPath, true)}>
                        Reveal {query.trim()}
                      </Button>
                    </>}
                  {revealError && <Text type="danger" role="alert">{revealError}</Text>}
                </div>}
                {exactPath === null && query.trim().length >= 2 && <div className="remote-search-results"
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
              { key: 'compare', label: `Compare (${changes.length})` },
              ...(snapshot?.capabilities?.primitive_edits === true
                ? [
                  { key: 'locked', label: `Locked (${snapshot?.locks?.entries?.length ?? 0})` },
                  { key: 'edits', label: `Edits (${snapshot?.edit_history?.entries?.length ?? 0})` },
                ]
                : [])]} />
          {scope === 'compare'
            ? <ComparePane changes={changes} favourites={favourites}
                focusedKey={comparisonFocus} onResetFocus={() => setComparisonFocus(null)}
                onClear={clearHistory} onInspect={inspectChange}
                onReveal={revealResult} onOpenSource={openSourceContext} />
            : scope === 'locked' && snapshot?.capabilities?.primitive_edits === true
              ? <LockedVariablesPane locks={snapshot?.locks} generation={treePages?.generation}
                  bridge={bridge} token={token} onLocksChanged={syncLocks}
                  onInspect={selectNode} />
              : scope === 'edits' && snapshot?.capabilities?.primitive_edits === true
                ? <EditHistoryPane value={snapshot?.edit_history}
                    generation={treePages?.generation} enabled={true}
                    bridge={bridge} token={token} />
                : <VariablePane scope={scope} treePages={treePages} watchValues={watchValues}
                query={query} favourites={favourites}
                selected={selected} onSelect={selectNode} onFavourite={pinVariable}
                lockedKeys={lockedKeys} staleLockKeys={staleLockKeys} expanded={expanded} onExpand={onExpanded} onRequestPage={requestPage}
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
              { key: 'version', label: 'Inspector', children: 'External workspace · v0.7.15 preview' },
              { key: 'connection', label: 'Connection', children: <span className="overview-connection">
                {online ? <CheckCircleFilled style={{ color: '#57d5a5' }} /> :
                  connection === 'connecting' ? <Spin size="small" /> :
                    <DisconnectOutlined style={{ color: '#ff9b81' }} />}
                {online ? 'Connected' : connection === 'connecting' ? 'Connecting' : 'Disconnected'}
              </span> },
              ...(error ? [{ key: 'error', label: 'Connection error', children: error }] : []),
              { key: 'capture', label: 'Last capture', children: captureTime(snapshot?.captured_at) },
              { key: 'performance', label: 'Root scan (sampled)', children:
                Number.isFinite(snapshot?.diagnostics?.root_scan_ms)
                  ? snapshot.diagnostics.root_scan_ms + ' ms, excludes lock checks/serialization/transfer'
                  : 'Waiting for game-thread capture' },
              { key: 'lockchecks', label: 'Lock monitor (sampled)', children:
                snapshot?.diagnostics
                  ? `${snapshot.diagnostics.lock_checks ?? 0} / ${snapshot.diagnostics.lock_check_limit ?? 8} paths · ${snapshot.diagnostics.lock_check_ms ?? 0} ms · ${(snapshot.locks?.entries ?? []).filter((entry) => entry.stale).length} stale`
                  : 'Waiting for game-thread capture' },
              { key: 'queue', label: 'Game-thread queue (sampled)', children:
                snapshot?.diagnostics
                  ? `${snapshot.diagnostics.queue_pending} / ${snapshot.diagnostics.queue_capacity} pending · ${snapshot.diagnostics.queue_peak} peak · ${snapshot.diagnostics.queue_rejected} rejected (current epoch)`
                  : 'Waiting for game-thread capture' },
              { key: 'jobtiming', label: 'Last inspected request', children:
                Number.isFinite(snapshot?.diagnostics?.last_request_ms)
                  ? `${snapshot.diagnostics.last_request_ms} ms execution · ${snapshot.diagnostics.last_queue_wait_ms} ms queued`
                  : 'No queued requests sampled yet' },
              { key: 'mode', label: 'Access', children: snapshot?.capabilities?.primitive_edits === true ?
                'Read-only inspection · explicitly game-enabled Store primitive writes · authenticated local session' :
                'Game state read-only · authenticated local session' },
              { key: 'preferences', label: 'Favourite storage', children: preferencesStatus },
              { key: 'watches', label: 'Favourites', children:
                'Independent path watches · read-only values · persisted inspector settings' },
              { key: 'compare', label: 'Compare', children:
                'Last 100 sampled transitions · exact small built-in scalar values, otherwise previews · resets after game load' },
              { key: 'budget', label: 'Capture limits', children:
                '80 per page · up to 1,000 per branch · 8 levels · 6,000 loaded nodes per browser' },
              { key: 'coverage', label: 'Coverage', children: snapshot?.truncated?.store || snapshot?.truncated?.persistent ?
                'Partial snapshot. Some branches are not included.' : 'Within configured snapshot limits' },
            ]} />
          </Card>
        </section>}
        {section === 'runtime' && <RuntimePane snapshot={snapshot} onOpenSource={openSourceContext} />}
        {section === 'scripts' && <ScriptPane token={token} bridge={bridge}
          activeGame={activeGame} generation={treePages?.generation}
          findRequest={findRequest} sourceRequest={sourceRequest} />}
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
            { key: 'type', label: 'Type', children: <><Tag color="geekblue">{activeNode?.type || 'Unknown'}</Tag><Tag>{valuePresentation(activeNode?.type, activeNode?.state).category}</Tag></> },
            { key: 'description', label: 'Type information', children: valuePresentation(activeNode?.type, activeNode?.state).detail },
            { key: 'state', label: 'State', children: activeNode?.state || 'Missing from latest snapshot' },
          ]} />
          <div className="detail-preview-heading"><Text strong>Captured value preview</Text>
            <Tooltip title="Copy the captured preview, not a full live value">
              <Button icon={<CopyOutlined />} disabled={!activeNode} size="small"
                onClick={() => activeNode && navigator.clipboard?.writeText(activeNode.preview).catch(() => {})}>Copy preview</Button>
            </Tooltip>
          </div>
          <pre className={`detail-value value-tone-${valuePresentation(activeNode?.type, activeNode?.state).tone}`}>{activeNode?.preview ?? '(not available)'}</pre>
          <div className="detail-source-actions">
            <Button size="small" icon={<SearchOutlined />}
              aria-label="Find references in Scripts" disabled={!canFindReferences}
              onClick={findReferences}>Find references in Scripts</Button>
            <Button size="small" disabled={!sourceTargetForContext(activeGame)}
              aria-label="View current script context" onClick={() => openSourceContext(activeGame)}
              title="Current statement is not necessarily where this variable was assigned">View current script</Button>
          </div>
          <FullValuePanel key={JSON.stringify([treePages?.generation, selected.scope, selected.key])}
            selection={selected} generation={treePages?.generation}
            bridge={bridge} token={token} />
          {snapshot?.capabilities?.primitive_edits === true &&
            <EditValuePanel
              key={JSON.stringify(['edit', treePages?.generation, selected.scope, selected.key])}
              enabled={snapshot.capabilities.primitive_edits} selection={selected}
              generation={treePages?.generation} bridge={bridge} token={token}
              locks={snapshot?.locks} onApplied={() => setSelected(null)} onLocksChanged={syncLocks} />}
          {(activeNode?.limited || activeNode?.capped) &&
            <Tag color="gold">Some descendants were omitted by type or inspection limits</Tag>}
          <div className="detail-history">
            <div className="detail-history-header">
              <Text strong>Observed history</Text>
              <Text type="secondary">{selectedHistory.length} recent changes</Text>
              <Button size="small" onClick={viewSelectedHistory}
                aria-label="View variable history in Compare">View in Compare</Button>
            </div>
            {selectedHistory.length ? selectedHistory.map((change) =>
              <div key={change.id} className="detail-history-entry">
                <Text type="secondary">
                  Sampled {new Date(change.capturedAt * 1000).toLocaleTimeString()} · {change.kind}
                </Text>
                <div className="detail-history-samples">
                  <div><Text type="secondary">Before · {change.before.precision === 'exact'
                    ? 'exact scalar' : 'preview/status'}</Text>
                    <pre className={`value-tone-${valuePresentation(change.before.type, change.before.kind).tone}`}>{comparisonText(change.before)}</pre></div>
                  <div><Text type="secondary">After · {change.after.precision === 'exact'
                    ? 'exact scalar' : 'preview/status'}</Text>
                    <pre className={`value-tone-${valuePresentation(change.after.type, change.after.kind).tone}`}>{comparisonText(change.after)}</pre></div>
                </div>
              </div>) :
              <Text type="secondary">
                No sampled changes for this variable in the last 100 events.
              </Text>}
          </div>
          <Paragraph type="secondary" className="detail-disclaimer">
            This is a bounded, read-only snapshot. Full primitive values can be
            requested on demand. Compare records small exact scalar samples and
            explicitly labels preview-only observations. It does not capture
            every mutation or reconstruct earlier values after the fact.
          </Paragraph>
        </>}
      </Drawer>
    </div>
  </ConfigProvider>;
}
