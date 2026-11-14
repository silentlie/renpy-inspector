import { useCallback, useEffect, useRef, useState } from 'react';
import { safeFavourites } from './tree.js';
import { applyFavouriteAction, applyFavouriteActions, commitFavouriteAction,
  readFavouriteSnapshot, sameFavourites } from './favourites-sync.js';

const FAVORITES_KEY = 'renpy-inspector-ant-favourites-v1';
const SYNC_INTERVAL_MS = 2500;

function loadLocalFavourites() {
  try { return safeFavourites(JSON.parse(localStorage.getItem(FAVORITES_KEY) ?? '[]')); }
  catch { return []; }
}

/** Per-game server file is authoritative; only explicit actions issue writes.
 * Each queued operation rebases on the latest revision instead of replacing
 * another tab's list with a stale whole-list snapshot.
 */
export function useFavouritePreferences(token, bridge) {
  const [favourites, setFavourites] = useState(loadLocalFavourites);
  const [preferencesStatus, setPreferencesStatus] = useState('Connecting');
  const [ready, setReady] = useState(false);
  const [workTick, setWorkTick] = useState(0);
  const localRef = useRef(favourites);
  const initialLocalRef = useRef(favourites);
  const serverRef = useRef(null);
  const pendingRef = useRef([]);
  const runningRef = useRef(false);
  const sessionRef = useRef(0);

  const present = useCallback((next) => {
    const checked = safeFavourites(next);
    if (sameFavourites(localRef.current, checked)) return;
    localRef.current = checked;
    setFavourites(checked);
  }, []);

  const enqueue = useCallback((action) => {
    pendingRef.current.push(action);
    present(applyFavouriteAction(localRef.current, action));
    setWorkTick((value) => value + 1);
  }, [present]);

  const toggleFavourite = useCallback((scope, key) => {
    const [entry] = safeFavourites([{ scope, key }]);
    if (!entry) return;
    // Compare the validated canonical path, not the caller's JSON spelling.
    const pinned = localRef.current.some((x) => x.scope === entry.scope && x.key === entry.key);
    if (!pinned && localRef.current.length >= 100) return;
    enqueue({ kind: pinned ? 'unpin' : 'pin', entry });
  }, [enqueue]);

  const clearAllFavourites = useCallback(() => {
    if (!localRef.current.length) return;
    enqueue({ kind: 'clear', entries: localRef.current.slice() });
  }, [enqueue]);

  useEffect(() => {
    if (!ready) return;
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(favourites)); }
    catch { /* private browsing */ }
  }, [favourites, ready]);

  useEffect(() => {
    const session = ++sessionRef.current;
    serverRef.current = null;
    setReady(false);
    if (!token) { setPreferencesStatus('Not paired'); return undefined; }
    let fetching = false;
    let importedLegacy = false;

    const refresh = async () => {
      if (fetching || runningRef.current) return;
      fetching = true;
      try {
        const response = await fetch(bridge + '/api/v1/favourites', {
          headers: { 'X-Inspector-Token': token }, method: 'GET',
          cache: 'no-store', mode: 'cors',
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const next = readFavouriteSnapshot(await response.json());
        if (session !== sessionRef.current) return;
        // Only migrate the old browser cache if there is no saved server file.
        // Apply pending user actions afterwards so a pre-bootstrap unpin wins.
        if (!importedLegacy && !next.initialized) {
          const migration = initialLocalRef.current.map((entry) => ({ kind: 'pin', entry }));
          pendingRef.current.unshift(...migration);
        }
        importedLegacy = true;
        if (!serverRef.current || next.revision >= serverRef.current.revision) {
          serverRef.current = next;
          present(applyFavouriteActions(next.favourites, pendingRef.current));
        }
        setPreferencesStatus('Inspector save directory');
        setReady(true);
        if (pendingRef.current.length) setWorkTick((value) => value + 1);
      } catch (failure) {
        if (session === sessionRef.current) {
          setPreferencesStatus('Local only: ' + (failure.message || 'Storage unavailable'));
          setReady(true);
        }
      } finally {
        fetching = false;
      }
    };
    refresh();
    // A small preference-only GET is separate from all game-thread polling.
    // Periodically reconcile tabs on different browser origins/instances too.
    const timer = window.setInterval(() => {
      if (!pendingRef.current.length && !runningRef.current) refresh();
      else if (!serverRef.current) refresh();
      else setWorkTick((value) => value + 1); // retry transient failures
    }, SYNC_INTERVAL_MS);
    const onStorage = (event) => {
      if (event.key !== FAVORITES_KEY) return;
      if (serverRef.current) {
        if (!pendingRef.current.length) refresh();
      } else if (!pendingRef.current.length) {
        present(loadLocalFavourites()); // no writable save directory
      }
    };
    window.addEventListener('storage', onStorage);
    return () => {
      ++sessionRef.current;
      window.clearInterval(timer);
      window.removeEventListener('storage', onStorage);
    };
  }, [bridge, token, present]);

  useEffect(() => {
    if (!ready || !token || !serverRef.current || runningRef.current ||
        pendingRef.current.length === 0) return;
    const session = sessionRef.current;
    runningRef.current = true;
    const flush = async () => {
      try {
        while (pendingRef.current.length && session === sessionRef.current) {
          const action = pendingRef.current[0];
          const base = serverRef.current;
          const result = await commitFavouriteAction(base, action, async (revision, entries) => {
            const response = await fetch(bridge + '/api/v1/favourites', {
              method: 'PUT', mode: 'cors', cache: 'no-store',
              headers: { 'X-Inspector-Token': token, 'Content-Type': 'application/json' },
              body: JSON.stringify({ version: 1, revision, favourites: entries }),
            });
            const data = await response.json().catch(() => null);
            return { status: response.status, data };
          });
          if (session !== sessionRef.current) break;
          serverRef.current = result;
          pendingRef.current.shift();
          present(applyFavouriteActions(result.favourites, pendingRef.current));
          setPreferencesStatus('Inspector save directory');
        }
      } catch (failure) {
        if (session === sessionRef.current) {
          // Keep the user's queued intent and retry later. Never overwrite
          // the current server list with a stale whole-list state.
          setPreferencesStatus('Sync pending: ' + (failure.message || 'Retrying'));
        }
      } finally { runningRef.current = false; }
    };
    flush();
  }, [bridge, token, ready, workTick, present]);

  return { favourites, preferencesStatus, toggleFavourite, clearAllFavourites };
}
