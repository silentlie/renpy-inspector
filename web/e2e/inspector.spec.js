import { test as base, expect } from '@playwright/test';
import { startBridgeFixture } from './bridge-fixture.js';

// Each browser test owns a fresh real HTTP server, auth token and synthetic
// game state. Commands modify the fixture via process stdin, never HTTP.
const test = base.extend({
  game: async ({}, use) => {
    const fixture = await startBridgeFixture();
    try { await use(fixture); } finally { await fixture.stop(); }
  },
});

test('real bridge authentication, browser startup and navigation', async ({ page, game }) => {
  const unpaired = await page.request.get(game.origin + '/api/v1/snapshot');
  expect(unpaired.status()).toBe(401);
  const foreign = await page.request.get(game.origin + '/api/v1/snapshot', {
    headers: { 'X-Inspector-Token': game.token, Origin: 'https://untrusted.example' },
  });
  expect(foreign.status()).toBe(403);
  const authenticated = await page.request.get(game.origin + '/api/v1/snapshot', {
    headers: { 'X-Inspector-Token': game.token },
  });
  expect(authenticated.ok()).toBeTruthy();
  expect((await authenticated.json()).scopes.store.some((item) => item.name === 'score'))
    .toBeTruthy();

  await page.goto(game.url);
  await expect(page.getByRole('button', { name: 'Inspect score' })).toBeVisible();
  await page.getByRole('tab', { name: 'Overview' }).click();
  await expect(page.getByText('Playwright Fixture')).toBeVisible();
  await expect(page.getByText('Connected', { exact: true })).toBeVisible();
  await expect(page.getByText('Game-thread queue (sampled)')).toBeVisible();
  await page.getByRole('tab', { name: 'Variables' }).click();
  await expect(page.getByRole('button', { name: 'Inspect score' })).toBeVisible();
  // The browser UI and queue GETs must not allow writes to game variables.
  const post = await page.request.post(game.origin + '/api/v1/snapshot', {
    headers: { 'X-Inspector-Token': game.token },
  });
  expect(post.status()).toBe(405);
});

test('primitive writes are disabled on the unconfigured bridge', async ({ page, game }) => {
  await page.goto(game.url);
  const snapshot = await (await page.request.get(game.origin + '/api/v1/snapshot', {
    headers: { 'X-Inspector-Token': game.token },
  })).json();
  expect(snapshot.capabilities.primitive_edits).toBe(false);
  expect(snapshot.locks.entries).toHaveLength(0);
  await expect(page.getByRole('tab', { name: /Edits \(/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Inspect score' }).click();
  await expect(page.getByRole('button', { name: 'Open primitive editor' })).toHaveCount(0);
  const disabledWrite = await page.request.put(game.origin + '/api/v1/edit', {
    headers: { 'X-Inspector-Token': game.token, 'Content-Type': 'application/json' },
    data: { scope: 'store', path: [['attribute', 'score']], generation: 0,
      type: 'int', text: '100', expected: 'a'.repeat(64) },
  });
  expect(disabledWrite.status()).toBe(403);
  const current = await (await page.request.get(game.origin + '/api/v1/snapshot', {
    headers: { 'X-Inspector-Token': game.token },
  })).json();
  expect(current.scopes.store.find((item) => item.name === 'score')?.preview).toBe('2');
});

test('explicit game opt-in permits a confirmed primitive edit and rejects stale samples', async ({ page }) => {
  const game = await startBridgeFixture({ editing: true });
  try {
    await page.goto(game.url);
    const headers = { 'X-Inspector-Token': game.token };
    const snapshot = await (await page.request.get(game.origin + '/api/v1/snapshot', {
      headers,
    })).json();
    expect(snapshot.capabilities.primitive_edits).toBe(true);
    await page.getByRole('button', { name: 'Inspect score' }).click();
    const editor = page.getByRole('region', { name: 'Primitive variable editing' });
    await expect(editor).toBeVisible();
    await editor.getByRole('button', { name: 'Open primitive editor' }).click();
    await expect(editor.getByRole('textbox', { name: 'New literal value' })).toHaveValue('2');
    await expect(editor.getByRole('button', { name: 'Apply primitive edit' })).toBeDisabled();
    await editor.getByRole('textbox', { name: 'New literal value' }).fill('17');
    await expect(editor.getByRole('button', { name: 'Apply primitive edit' })).toBeDisabled();
    await editor.getByRole('checkbox', {
      name: 'I understand this writes to the running game state',
    }).check();
    await editor.getByRole('button', { name: 'Apply primitive edit' }).click();
    await expect(page.getByRole('dialog', { name: 'Variable details' })).toHaveCount(0);
    const scoreRow = page.locator('.variable-row').filter({
      has: page.locator('.variable-key', { hasText: /^score$/ }),
    });
    await expect(scoreRow.locator('.variable-preview')).toHaveText('17', { timeout: 12000 });

    // A captured exact-value fingerprint detects changes within one generation.
    const params = new URLSearchParams({
      scope: 'store', path: JSON.stringify([['attribute', 'score']]),
    });
    const targetResponse = await page.request.get(game.origin + '/api/v1/edit-target?' + params, {
      headers,
    });
    expect(targetResponse.status()).toBe(200);
    const target = await targetResponse.json();
    await game.command('set_score', { value: 18 });
    const conflict = await page.request.put(game.origin + '/api/v1/edit', {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { scope: 'store', path: [['attribute', 'score']],
        generation: target.generation, type: target.type,
        expected: target.expected, text: '100' },
    });
    expect(conflict.status()).toBe(409);
    await expect(scoreRow.locator('.variable-preview')).toHaveText('18', { timeout: 12000 });

    // Stale generation is invalid even when an old exact value recurs.
    await game.command('restore_game');
    const stale = await page.request.put(game.origin + '/api/v1/edit', {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { scope: 'store', path: [['attribute', 'score']],
        generation: target.generation, type: target.type,
        expected: target.expected, text: '300' },
    });
    expect(stale.status()).toBe(409);
  } finally { await game.stop(); }
});

test('variable locks protect inspector writes without freezing game state', async ({ page }) => {
  const game = await startBridgeFixture({ editing: true });
  try {
    await page.goto(game.url);
    const headers = { 'X-Inspector-Token': game.token };
    const snapshot = await (await page.request.get(game.origin + '/api/v1/snapshot', {
      headers,
    })).json();
    expect(snapshot.locks.entries).toHaveLength(0);
    await page.getByRole('button', { name: 'Inspect score' }).click();
    const editor = page.getByRole('region', { name: 'Primitive variable editing' });
    await editor.getByRole('button', { name: 'Open primitive editor' }).click();
    await expect(editor.getByRole('textbox', { name: 'New literal value' })).toHaveValue('2');

    await editor.getByRole('button', { name: 'Lock variable' }).click();
    await expect(editor.getByRole('button', { name: 'Unlock variable' })).toBeVisible();
    await expect(editor).toContainText('does not prevent game scripts');
    await expect(page.locator('.variable-lock-indicator')).toHaveAttribute(
      'aria-label', 'Locked against Inspector writes');
    const params = new URLSearchParams({
      scope: 'store', path: JSON.stringify([['attribute', 'score']]),
    });
    const target = await (await page.request.get(
      game.origin + '/api/v1/edit-target?' + params, { headers })).json();
    expect(target.locked).toBe(true);
    expect(target.generation).toBe(snapshot.generation);

    const denied = await page.request.put(game.origin + '/api/v1/edit', {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { scope: 'store', path: [['attribute', 'score']],
        generation: target.generation, expected: target.expected,
        type: target.type, text: '100' },
    });
    expect(denied.status()).toBe(423);
    expect((await (await page.request.get(game.origin + '/api/v1/snapshot', {
      headers,
    })).json()).scopes.store.find((item) => item.name === 'score')?.preview).toBe('2');

    await editor.getByRole('button', { name: 'Unlock variable' }).click();
    await expect(page.locator('.variable-lock-indicator')).toHaveCount(0);
    await editor.getByRole('textbox', { name: 'New literal value' }).fill('17');
    await editor.getByRole('checkbox', {
      name: 'I understand this writes to the running game state',
    }).check();
    await editor.getByRole('button', { name: 'Apply primitive edit' }).click();
    await expect(page.getByRole('dialog', { name: 'Variable details' })).toHaveCount(0);
    await expect(page.locator('.variable-row').filter({
      has: page.locator('.variable-key', { hasText: /^score$/ }),
    }).locator('.variable-preview')).toHaveText('17', { timeout: 12000 });
    const latest = await (await page.request.get(game.origin + '/api/v1/snapshot', {
      headers,
    })).json();
    expect(latest.locks.entries).toHaveLength(0);
  } finally { await game.stop(); }
});

test('explicit edit history performs confirmed undo and redo without mixing with Compare', async ({ page }) => {
  const game = await startBridgeFixture({ editing: true });
  try {
    await page.goto(game.url);
    const headers = { 'X-Inspector-Token': game.token };
    const params = new URLSearchParams({
      scope: 'store', path: JSON.stringify([['attribute', 'score']]),
    });
    const targetResponse = await page.request.get(game.origin + '/api/v1/edit-target?' + params, {
      headers,
    });
    expect(targetResponse.status()).toBe(200);
    const target = await targetResponse.json();
    const edit = await page.request.put(game.origin + '/api/v1/edit', {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { scope: 'store', path: [['attribute', 'score']],
        generation: target.generation, expected: target.expected,
        type: target.type, text: '17' },
    });
    expect(edit.status()).toBe(200);
    const edited = await edit.json();
    expect(edited.edit_history.entries).toHaveLength(1);

    const tab = page.getByRole('tab', { name: /Edits \(1\)/ });
    await expect(tab).toBeVisible({ timeout: 12000 });
    await tab.click();
    const history = page.getByRole('region', { name: 'Inspector edit history' });
    await expect(history).toContainText('store.score');
    await expect(history).toContainText('Before');
    await expect(history).toContainText('17');

    const confirm = history.getByRole('checkbox', {
      name: 'I understand Undo/Redo writes to the running game',
    });
    await confirm.check();
    await history.getByRole('button', { name: 'Undo last inspector edit' }).click();
    await expect(history).toContainText('Undone');
    await expect.poll(async () => {
      const snapshot = await (await page.request.get(game.origin + '/api/v1/snapshot', {
        headers,
      })).json();
      return snapshot.scopes.store.find((item) => item.name === 'score')?.preview;
    }).toBe('2');

    await confirm.check();
    await history.getByRole('button', { name: 'Redo last inspector edit' }).click();
    await expect(history).toContainText('Applied');
    await expect.poll(async () => {
      const snapshot = await (await page.request.get(game.origin + '/api/v1/snapshot', {
        headers,
      })).json();
      return snapshot.scopes.store.find((item) => item.name === 'score')?.preview;
    }).toBe('17');

    // A new edit after Undo starts a new branch and removes the old Redo action.
    await confirm.check();
    await history.getByRole('button', { name: 'Undo last inspector edit' }).click();
    await expect(history).toContainText('Undone');
    const undoneSnapshot = await (await page.request.get(game.origin + '/api/v1/snapshot', {
      headers,
    })).json();
    const nextTarget = await (await page.request.get(
      game.origin + '/api/v1/edit-target?' + params, { headers })).json();
    const replacement = await page.request.put(game.origin + '/api/v1/edit', {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { scope: 'store', path: [['attribute', 'score']],
        generation: nextTarget.generation, expected: nextTarget.expected,
        type: nextTarget.type, text: '23' },
    });
    expect(replacement.status()).toBe(200);
    const latest = await replacement.json();
    expect(latest.edit_history.can_redo).toBe(false);
    expect(latest.edit_history.entries.find((entry) =>
      entry.id === edited.edit_history.entries[0].id)?.status).toBe('superseded');
    expect(undoneSnapshot.edit_history.can_redo).toBe(true);
    await expect(history.getByRole('button', { name: 'Redo last inspector edit' })).toBeDisabled();

    // Same-generation game-side changes are not overwritten by Undo.
    await game.command('set_score', { value: 99 });
    await confirm.check();
    await history.getByRole('button', { name: 'Undo last inspector edit' }).click();
    await expect(history).toContainText('Conflict');
    const currentTarget = await (await page.request.get(
      game.origin + '/api/v1/edit-target?' + params, { headers })).json();
    expect(currentTarget.text).toBe('99');

  } finally { await game.stop(); }
});

test('Runtime shows bounded observations without inventing rollback turns', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('tab', { name: 'Runtime' }).click();
  await expect(page.getByRole('region', { name: 'Observed runtime timeline' })).toContainText('game/script.rpy:1');
  await expect(page.getByText(/not SugarCube turns/i)).toBeVisible();
  await game.command('set_runtime_line', { line: 12 });
  await expect(page.getByRole('region', { name: 'Observed runtime timeline' }))
    .toContainText('game/script.rpy:12');
  await game.command('restore_game');
  await expect(page.getByRole('region', { name: 'Observed runtime timeline' }))
    .toContainText('Inspector state invalidated');
  await page.getByRole('combobox', { name: 'Filter runtime observations' }).click();
  await page.getByText('Inspector invalidations', { exact: true }).last().click();
  await expect(page.locator('.runtime-event')).toHaveCount(1);
  const response = await page.request.get(game.origin + '/api/v1/snapshot', {
    headers: { 'X-Inspector-Token': game.token },
  });
  const runtime = (await response.json()).runtime;
  expect(runtime.events.length).toBeLessThanOrEqual(64);
  expect(runtime.events.some((entry) => entry.kind === 'invalidation' && entry.signal === 'unspecified'))
    .toBeTruthy();
});

test('source highlighting, rich type labels, and navigation reuse the read-only bridge', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Inspect score' }).click();
  const drawer = page.getByRole('dialog', { name: 'Variable details' });
  await expect(drawer.getByText('Integer', { exact: true })).toBeVisible();
  await expect(drawer.getByText(/numeric preview, not an editable Python value/i)).toBeVisible();
  await drawer.getByRole('button', { name: 'View current script context' }).click();
  await expect(page.getByRole('tab', { name: 'Scripts' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('region', { name: 'Script source context' })).toContainText('script.rpy:1');
  const source = page.locator('.script-source-lines');
  await expect(source.locator('.source-token-keyword').filter({ hasText: 'label' }).first()).toBeVisible();
  await expect(source.locator('.script-source-active')).toHaveCount(1);
  await page.getByRole('tab', { name: 'Runtime' }).click();
  await expect(page.getByRole('button', { name: 'View current in Scripts' })).toBeVisible();
  await page.getByRole('button', { name: 'View current in Scripts' }).click();
  await expect(page.getByRole('region', { name: 'Script source context' })).toContainText('script.rpy:1');
  await page.getByRole('tab', { name: 'Variables' }).click();
  await game.command('set_score', { value: 17 });
  await page.getByRole('tab', { name: /Compare \(/ }).click();
  const changed = page.locator('.compare-entry').filter({ hasText: 'store.score' });
  await expect(changed).toBeVisible({ timeout: 12000 });
  await changed.getByRole('button', { name: 'View sampled source' }).click();
  await expect(page.getByRole('tab', { name: 'Scripts' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('region', { name: 'Script source context' })).toContainText('script.rpy:1');

  // A later Find References must not be replaced by an earlier source request
  // when the Scripts panel unmounts and mounts again.
  await page.getByRole('tab', { name: 'Variables' }).click();
  // The preceding step was in Compare. Switching the top-level tab does not
  // change the nested variable scope, so explicitly return to Store.
  await page.getByRole('tab', { name: 'Store', exact: true }).click();
  await page.getByRole('button', { name: 'Inspect score' }).click();
  await page.getByRole('dialog', { name: 'Variable details' })
    .getByRole('button', { name: 'Find references in Scripts' }).click();
  await expect(page.getByRole('textbox', { name: 'Search source text' })).toHaveValue('score');
  await expect(page.getByRole('region', { name: 'Script source context' }))
    .toContainText('Choose a label or view the current statement');

  // The reverse order must also work: a source navigation should replace a
  // previous literal reference search, never resurrect that search on remount.
  await page.getByRole('tab', { name: 'Runtime' }).click();
  await page.getByRole('button', { name: 'View current in Scripts' }).click();
  await expect(page.getByRole('region', { name: 'Script source context' })).toContainText('script.rpy:1');
  await expect(page.getByRole('textbox', { name: 'Search script labels or filenames' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Search script labels or filenames' })).toHaveValue('');
});

test('pinned values update and survive a simulated game reload', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('tab', { name: 'Overview' }).click();
  await expect(page.getByText('Inspector save directory')).toBeVisible();
  await page.getByRole('tab', { name: 'Variables' }).click();
  await page.getByRole('button', { name: 'Add score to favourites' }).click();
  await page.getByRole('tab', { name: /Favourites \(1\)/ }).click();
  const scoreRow = page.locator('.variable-row').filter({
    has: page.locator('.variable-key', { hasText: /^score$/ }),
  });
  await expect(scoreRow.locator('.variable-preview')).toHaveText('2');
  await game.command('set_score', { value: 17 });
  await expect(scoreRow.locator('.variable-preview')).toHaveText('17');
  await game.command('restore_game');
  await expect(scoreRow.locator('.variable-preview')).toHaveText('2');
  await expect(page.getByRole('tab', { name: /Favourites \(1\)/ })).toBeVisible();
  // A real page reload must recover pins from inspector-owned preferences.
  await page.reload();
  await expect(page.getByRole('tab', { name: /Favourites \(1\)/ })).toBeVisible();
});

test('global popup search reveals a nested value across real HTTP', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Search variables' }).click();
  await page.getByRole('textbox', { name: 'Search variables across Store and Persistent' })
    .fill('hp');
  const matches = page.getByRole('listbox', { name: 'Matching game variables' });
  await expect(matches.getByRole('option').first()).toBeVisible();
  await matches.getByRole('option').first().click();
  await expect(page.getByRole('button', { name: /Inspect.*hp/i }).first()).toBeVisible();
  await expect(page.locator('.variable-row-active').first()).toBeVisible();
});

test('Scripts shows real queued label lookup and restricted source excerpt', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('tab', { name: 'Scripts' }).click();
  const start = page.locator('.script-label-item').filter({ hasText: 'start' }).first();
  await expect(start).toBeVisible();
  await start.click();
  await expect(page.locator('.script-source-line code').filter({
    hasText: 'label start:',
  })).toBeVisible();
  await expect(page.locator('.script-source-heading')).toContainText('script.rpy:1');
});

test('virtualised expanded collection loads subsequent pages, then resets on load', async ({ page, game }) => {
  await page.goto(game.url);
  const inventory = page.locator('.variable-label-expandable').filter({
    has: page.locator('.variable-key', { hasText: /^inventory$/ }),
  });
  await inventory.click();
  await expect(page.getByRole('button', { name: 'Inspect [0]' })).toBeVisible();

  let laterPageObserved = false;
  page.on('response', (response) => {
    if (response.url().includes('/api/v1/children?') &&
        new URL(response.url()).searchParams.get('offset') === '80' &&
        response.status() === 200) laterPageObserved = true;
  });
  const list = page.locator('.ant-tree-list-holder').first();
  await expect.poll(async () => {
    await list.evaluate((element) => { element.scrollTop = element.scrollHeight; });
    return laterPageObserved;
  }, { timeout: 12000, intervals: [150, 250, 350] }).toBeTruthy();

  await game.command('shrink_inventory');
  await game.command('restore_game');
  await expect(page.getByRole('button', { name: 'Inspect inventory' })).toBeVisible();
  await expect(page.locator('.variable-row-active')).toHaveCount(0);
});


// Full values use a separate authenticated game-thread job. Small previews,
// automatic watches and Compare remain unchanged.
test('full value drawer loads multiline text on demand and caps oversized strings', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Inspect story_text' }).click();
  await expect(page.getByRole('region', { name: 'Full value inspection' })).toBeVisible();
  await expect(page.getByLabel('Full variable value')).toHaveCount(0);
  await page.getByRole('button', { name: 'Show full value' }).click();
  const full = page.getByLabel('Full variable value');
  await expect(full).toHaveText('Line one\nLine two: ☃');
  await expect(page.getByRole('button', { name: 'Copy Value' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Copy Path' })).toBeEnabled();
  await page.getByRole('button', { name: 'Refresh full value' }).click();
  await expect(full).toHaveText('Line one\nLine two: ☃');

  await page.getByRole('button', { name: 'Close', exact: true }).last().click();
  await page.getByRole('button', { name: 'Inspect large_text' }).click();
  await page.getByRole('button', { name: 'Show full value' }).click();
  await expect(page.getByLabel('Full variable value')).toHaveText('L'.repeat(16384));
  await expect(page.getByText(/Truncated: 16,384-character budget/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy Value' })).toBeDisabled();

  await page.getByRole('button', { name: 'Close', exact: true }).last().click();
  await page.getByRole('button', { name: 'Inspect player_stats' }).click();
  await page.getByRole('button', { name: 'Show full value' }).click();
  await expect(page.getByRole('status').filter({
    hasText: 'Full value is available only for built-in primitives',
  })).toBeVisible();
  await expect(page.getByLabel('Full variable value')).toHaveCount(0);
});

test('full value API rejects unauthorised, foreign and non-GET requests', async ({ page, game }) => {
  const params = new URLSearchParams({
    scope: 'store', path: JSON.stringify([['attribute', 'story_text']]),
  });
  const endpoint = game.origin + '/api/v1/full-value?' + params;
  expect((await page.request.get(endpoint)).status()).toBe(401);
  expect((await page.request.get(endpoint, {
    headers: { 'X-Inspector-Token': game.token, Origin: 'https://evil.invalid' },
  })).status()).toBe(403);
  expect((await page.request.post(endpoint, {
    headers: { 'X-Inspector-Token': game.token },
  })).status()).toBe(405);
  const response = await page.request.get(endpoint, {
    headers: { 'X-Inspector-Token': game.token },
  });
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.kind).toBe('string');
  expect(body.truncated).toBe(false);
  expect(body.text).toBe('Line one\nLine two: ☃');
});


test('exact typed path reveals nested and off-page values without a global search scan', async ({ page, game }) => {
  const scanned = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/search') scanned.push(request.url());
  });
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Search variables' }).click();
  const input = page.getByRole('textbox', {
    name: 'Search variables across Store and Persistent',
  });
  await input.fill('store.player_stats["hp"]');
  await expect(page.getByRole('button', { name: 'Reveal exact variable path' })).toBeVisible();
  await expect(page.getByRole('listbox', { name: 'Matching game variables' })).toHaveCount(0);
  await input.press('Enter');
  await expect(page.getByRole('button', { name: /Inspect.*hp/i })).toBeVisible();
  await expect(page.locator('.variable-row-active')).toBeVisible();

  await page.getByRole('button', { name: 'Search variables' }).click();
  await input.fill('store.inventory[169]');
  await page.getByRole('button', { name: 'Reveal exact variable path' }).click();
  await expect(page.getByRole('button', { name: 'Inspect [169]', exact: true }))
    .toBeVisible({ timeout: 15000 });
  await expect(page.locator('.variable-row-active')).toBeVisible();
  expect(scanned).toEqual([]);
});

test('exact path supports persistent dictionary keys and explicit integer dictionary keys', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Search variables' }).click();
  const input = page.getByRole('textbox', {
    name: 'Search variables across Store and Persistent',
  });
  await input.fill('persistent["test_flag"]');
  await input.press('Enter');
  await expect(page.getByRole('tab', { name: 'Persistent', exact: true }))
    .toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('button', { name: /Inspect.*test_flag/i })).toBeVisible();

  await page.getByRole('button', { name: 'Search variables' }).click();
  await input.fill('store.player_stats[key:3]');
  await input.press('Enter');
  await expect(page.getByRole('tab', { name: 'Store', exact: true }))
    .toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('button', { name: /Inspect.*\[3\]/i }))
    .toBeVisible();
});

test('exact path reports missing keys and rejects unsafe expressions in the popup', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Search variables' }).click();
  const input = page.getByRole('textbox', {
    name: 'Search variables across Store and Persistent',
  });
  await input.fill('store.player_stats["does-not-exist"]');
  await input.press('Enter');
  await expect(page.getByRole('alert')).toContainText('Exact path not found');
  await expect(page.getByRole('search')).toBeVisible();

  let revealRequests = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/reveal') revealRequests += 1;
  });
  await input.fill('store.player_stats[__import__("os")]');
  await expect(page.getByRole('alert')).toContainText('Expressions are not supported');
  await expect(page.getByRole('button', { name: 'Reveal exact variable path' })).toHaveCount(0);
  await input.press('Enter');
  expect(revealRequests).toBe(0);
});


test('source text search finds literal matches in multiple .rpy files and opens excerpts', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('tab', { name: 'Scripts' }).click();
  await page.getByText('Source text', { exact: true }).click();
  const input = page.getByRole('textbox', { name: 'Search source text' });
  await input.fill('score');
  const results = page.getByRole('region', { name: 'Source text matches' });
  await expect(results.getByRole('button', { name: 'Open source match references.rpy:3' })).toBeVisible();
  await expect(results.getByRole('button', { name: 'Open source match script.rpy:3' })).toBeVisible();
  await results.getByRole('button', { name: 'Open source match references.rpy:3' }).click();
  await expect(page.locator('.script-source-heading')).toContainText('references.rpy:3');
  await expect(page.locator('.script-source-line.script-source-active')).toContainText('score');
  await expect(results.getByText(/Literal, case-insensitive text matches/)).toBeVisible();
  await page.getByText('Labels', { exact: true }).click();
  await expect(page.getByRole('region', { name: 'Script labels' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Search script labels or filenames' })).toBeVisible();
});

test('Find References from variable details opens source text search without editing gameplay', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Inspect score' }).click();
  await page.getByRole('button', { name: 'Find references in Scripts' }).click();
  await expect(page.getByRole('tab', { name: 'Scripts' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('textbox', { name: 'Search source text' })).toHaveValue('score');
  const results = page.getByRole('region', { name: 'Source text matches' });
  await expect(results.getByRole('button', { name: 'Open source match script.rpy:3' })).toBeVisible();
  await results.getByRole('button', { name: 'Open source match script.rpy:3' }).click();
  await expect(page.locator('.script-source-heading')).toContainText('script.rpy:3');
});

test('source search is authenticated, read-only and rejects traversal-like cursors', async ({ page, game }) => {
  const url = game.origin + '/api/v1/source-search?' +
    new URLSearchParams({ q: 'score', cursor: '0:0', size: '20' });
  expect((await page.request.get(url)).status()).toBe(401);
  expect((await page.request.get(url, {
    headers: { 'X-Inspector-Token': game.token, Origin: 'https://foreign.invalid' },
  })).status()).toBe(403);
  expect((await page.request.post(url, {
    headers: { 'X-Inspector-Token': game.token },
  })).status()).toBe(405);
  const valid = await page.request.get(url, {
    headers: { 'X-Inspector-Token': game.token },
  });
  expect(valid.ok()).toBeTruthy();
  const body = await valid.json();
  expect(body.available).toBe(true);
  expect(body.matches.some((item) => item.file === 'references.rpy')).toBe(true);
  const invalid = game.origin + '/api/v1/source-search?' +
    new URLSearchParams({ q: 'score', cursor: '../../secret.rpy', size: '20' });
  expect((await page.request.get(invalid, {
    headers: { 'X-Inspector-Token': game.token },
  })).status()).toBe(400);
});


test('Compare records exact small strings even when their previews are identical', async ({ page, game }) => {
  await page.goto(game.url);
  const memo = page.locator('.variable-row').filter({
    has: page.locator('.variable-key', { hasText: /^memo$/ }),
  });
  const initialPreview = await memo.locator('.variable-preview').innerText();
  await game.command('change_memo', { value: 'after' });
  await page.getByRole('tab', { name: /Compare \(/ }).click();
  const entry = page.locator('.compare-entry').filter({ hasText: 'store.memo' });
  await expect(entry).toBeVisible({ timeout: 12000 });
  await expect(entry.getByText('exact sampled scalar')).toHaveCount(2);
  await expect(entry.locator('.compare-sample').first()).toHaveText('A'.repeat(110) + 'before');
  await expect(entry.locator('.compare-sample').last()).toHaveText('A'.repeat(110) + 'after');
  await page.getByRole('tab', { name: 'Store' }).click();
  await expect(memo.locator('.variable-preview')).toHaveText(initialPreview);
});

test('Compare filters, pinned-only history, detail history and Reveal in tree', async ({ page, game }) => {
  await page.goto(game.url);
  await page.getByRole('button', { name: 'Add score to favourites' }).click();
  await game.command('set_score', { value: 17 });
  await game.command('change_memo', { value: 'after' });
  await page.getByRole('tab', { name: /Compare \(/ }).click();
  const changes = page.getByRole('region', { name: 'Observed variable changes' });
  await expect(changes.locator('.compare-entry')).toHaveCount(2, { timeout: 12000 });
  await page.getByRole('textbox', { name: 'Filter comparison paths' }).fill('memo');
  await expect(changes.locator('.compare-entry')).toHaveCount(1);
  await expect(changes.locator('.compare-entry')).toContainText('store.memo');
  await page.getByRole('textbox', { name: 'Filter comparison paths' }).fill('');
  await page.getByRole('checkbox', { name: 'Pinned only' }).check();
  await expect(changes.locator('.compare-entry')).toHaveCount(1);
  await expect(changes.locator('.compare-entry')).toContainText('store.score');
  await page.getByRole('checkbox', { name: 'Pinned only' }).uncheck();
  await changes.locator('.compare-entry').filter({ hasText: 'store.memo' })
    .getByRole('button', { name: 'Reveal in tree' }).click();
  await expect(page.getByRole('tab', { name: 'Store', exact: true }))
    .toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('.variable-row-active')).toContainText('memo');

  await page.getByRole('button', { name: 'Inspect memo' }).click();
  const drawer = page.getByRole('dialog', { name: 'Variable details' });
  await expect(drawer.getByText('Observed history')).toBeVisible();
  await expect(drawer.locator('.detail-history-samples pre').last()).toHaveText(
    'A'.repeat(110) + 'after');
  await drawer.getByRole('button', { name: 'View variable history in Compare' }).click();
  await expect(page.getByRole('tab', { name: /Compare \(/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('status')).toContainText('History for store.memo');
  await expect(changes.locator('.compare-entry')).toHaveCount(1);
  await page.getByRole('button', { name: 'Show all paths' }).click();
  await expect(changes.locator('.compare-entry')).toHaveCount(2);
  await game.command('restore_game');
  await expect(page.getByRole('tab', { name: 'Compare (0)' })).toBeVisible({ timeout: 12000 });
});


test('set and frozenset scalar members expand, reveal by value and expose full primitives', async ({ page, game }) => {
  await page.goto(game.url);
  const flags = page.locator('.variable-label-expandable').filter({
    has: page.locator('.variable-key', { hasText: /^set_flags$/ }),
  });
  await expect(flags).toBeVisible();
  await flags.click();
  await expect(page.getByRole('button', { name: "Inspect {'open'}", exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspect {42}', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspect {True}', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspect {None}', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Search variables' }).click();
  const input = page.getByRole('textbox', {
    name: 'Search variables across Store and Persistent',
  });
  await input.fill('store.frozen_flags{"blue"}');
  await expect(page.getByRole('button', { name: 'Reveal exact variable path' })).toBeVisible();
  await input.press('Enter');
  await expect(page.getByRole('button', { name: "Inspect {'blue'}", exact: true }))
    .toBeVisible({ timeout: 12000 });
  await expect(page.locator('.variable-row-active')).toContainText("{'blue'}");
  await page.getByRole('button', { name: "Inspect {'blue'}", exact: true }).click();
  await page.getByRole('button', { name: 'Show full value' }).click();
  await expect(page.getByLabel('Full variable value')).toHaveText('blue');
});

test('unsupported set members show explicit partial coverage without endless pagination', async ({ page, game }) => {
  await page.goto(game.url);
  const mixed = page.locator('.variable-label-expandable').filter({
    has: page.locator('.variable-key', { hasText: /^mixed_set$/ }),
  });
  await mixed.click();
  await expect(page.locator('.variable-partial-icon[aria-label="Partial collection coverage"]'))
    .toBeVisible({ timeout: 12000 });
  await expect(page.getByRole('button', { name: "Inspect {'visible'}", exact: true }))
    .toBeVisible();
  // Unsupported object members are omitted and do not create page sentinels.
  const row = page.locator('.variable-row').filter({
    has: page.locator('.variable-key', { hasText: /^mixed_set$/ }),
  }).first();
  await expect(row.locator('.variable-partial-icon')).toBeVisible();
  expect(await page.getByText('More entries below…').count()).toBe(0);
});

test('pinned set member follows membership deletion and recovery without positional drift', async ({ page, game }) => {
  await page.goto(game.url);
  const flags = page.locator('.variable-label-expandable').filter({
    has: page.locator('.variable-key', { hasText: /^set_flags$/ }),
  });
  await flags.click();
  await page.getByRole('button', { name: "Add {'open'} to favourites", exact: true }).click();
  await page.getByRole('tab', { name: /Favourites \(1\)/ }).click();
  // Ant's virtual transition can briefly keep the Store row mounted as the
  // Favourites scope becomes active. Select the new favourites row.
  const row = page.locator('.variable-row').filter({
    has: page.locator('.variable-key', { hasText: /\{'open'\}/ }),
  }).last();
  await expect(row.locator('.variable-preview')).toHaveText("'open'", { timeout: 12000 });
  await game.command('remove_set_member');
  await expect(row.locator('.variable-preview')).toHaveText('<missing>', { timeout: 12000 });
  await game.command('restore_set_member');
  await expect(row.locator('.variable-preview')).toHaveText("'open'", { timeout: 12000 });
});

test('read-only set membership rejects made-up members and executable paths', async ({ page, game }) => {
  const endpoint = game.origin + '/api/v1/reveal?';
  const valid = new URLSearchParams({
    scope: 'store', path: JSON.stringify([['attribute', 'set_flags'], ['member', 'open']]),
  });
  const headers = { 'X-Inspector-Token': game.token };
  const response = await page.request.get(endpoint + valid, { headers });
  expect(response.status()).toBe(200);
  const data = await response.json();
  expect(data.chain.at(-1).name).toBe("{'open'}");
  const unknown = new URLSearchParams({
    scope: 'store', path: JSON.stringify([['attribute', 'set_flags'], ['member', 'not-there']]),
  });
  expect((await page.request.get(endpoint + unknown, { headers })).status()).toBe(404);
  const hostile = new URLSearchParams({
    scope: 'store', path: JSON.stringify([['attribute', 'set_flags'], ['member', { code: 'evil' }]]),
  });
  expect((await page.request.get(endpoint + hostile, { headers })).status()).toBe(400);
  expect((await page.request.post(endpoint + valid, { headers })).status()).toBe(405);
});
