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
  await expect(page.getByText('Read-only queue (sampled)')).toBeVisible();
  await page.getByRole('tab', { name: 'Variables' }).click();
  await expect(page.getByRole('button', { name: 'Inspect score' })).toBeVisible();
  // The browser UI and queue GETs must not allow writes to game variables.
  const post = await page.request.post(game.origin + '/api/v1/snapshot', {
    headers: { 'X-Inspector-Token': game.token },
  });
  expect(post.status()).toBe(405);
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
