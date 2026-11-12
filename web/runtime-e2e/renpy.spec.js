import { test, expect } from '@playwright/test';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, writeFile, chmod, rm, mkdir } from 'node:fs/promises';
import { existsSync, createWriteStream } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

const exec = promisify(execFile);
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sdk = process.env.RENPY_SDK_SCRIPT;
const project = process.env.RENPY_E2E_PROJECT;
const results = process.env.RENPY_E2E_OUTPUT || join(process.cwd(), 'test-results', 'real-renpy');

async function eventually(fn, timeout = 40000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeout) {
    try {
      const found = await fn();
      if (found) return found;
    } catch (error) { lastError = error; }
    await delay(250);
  }
  throw new Error('Timed out waiting for real Ren\'Py state: ' + (lastError?.message || 'not ready'));
}

async function windowId() {
  const found = await exec('xdotool', ['search', '--onlyvisible', '--name',
    'Ren.Py Inspector Runtime E2E'], { timeout: 3000 });
  const ids = found.stdout.trim().split(/\s+/).filter(Boolean);
  return ids[ids.length - 1] || null;
}

async function key(window, name) {
  await exec('xdotool', ['windowfocus', '--sync', window], { timeout: 4000 });
  await exec('xdotool', ['mousemove', '--window', window, '380', '280'],
    { timeout: 4000 });
  await exec('xdotool', ['key', '--clearmodifiers', '--delay', '90', name],
    { timeout: 5000 });
  await delay(350);
}

function tail(value, max = 6000) {
  return value.length > max ? value.slice(-max) : value;
}

test('actual graphical RenPy SDK: F8, browser, live game state, rollback and save/load', async ({ page }) => {
  test.setTimeout(145000);
  if (!sdk || !project) throw new Error('Set RENPY_SDK_SCRIPT and RENPY_E2E_PROJECT');
  await mkdir(results, { recursive: true });
  const home = await mkdtemp(join(tmpdir(), 'renpy-runtime-e2e-'));
  const urlFile = join(home, 'browser-url.txt');
  const browserHelper = join(home, 'record-browser.sh');
  const gameLog = join(results, 'engine.log');
  await writeFile(browserHelper, [
    '#!/bin/sh',
    '# Receive Python webbrowser.open URL without starting a separate browser.',
    'printf "%s\\n" "$1" >> "$RENPY_E2E_URL_FILE"',
    '',
  ].join('\n'));
  await chmod(browserHelper, 0o700);

  const log = createWriteStream(gameLog, { flags: 'w' });
  const env = {
    ...process.env,
    HOME: home,
    XDG_DATA_HOME: join(home, '.local', 'share'),
    BROWSER: browserHelper,
    RENPY_E2E_URL_FILE: urlFile,
    SDL_AUDIODRIVER: 'dummy',
    LIBGL_ALWAYS_SOFTWARE: '1',
    RENPY_SKIP_SPLASHSCREEN: '1',
  };
  const engine = spawn('bash', [sdk, project], {
    cwd: dirname(sdk), env, detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  engine.stdout.pipe(log);
  engine.stderr.pipe(log);
  let exited = null;
  engine.on('exit', (code, signal) => { exited = [code, signal]; });

  const ensureEngine = async () => {
    if (exited) {
      let output = '';
      try { output = await readFile(gameLog, 'utf8'); } catch { /* file incomplete */ }
      throw new Error('Ren\'Py exited ' + JSON.stringify(exited) + '\n' + tail(output));
    }
  };

  try {
    const window = await eventually(async () => {
      await ensureEngine();
      return await windowId();
    }, 65000);
    // The X11 window may exist while Ren'Py is still loading/rendering its
    // first interaction. Only inject keys after label start signalled ready.
    await eventually(async () => {
      await ensureEngine();
      return existsSync(urlFile + '.ready');
    }, 65000);
    await delay(900);
    // Fixture-only F10 probes whether XTest keypresses actually reach the
    // running Ren'Py overlay before claiming an F8 integration failure.
    await key(window, 'F10');
    // Some virtual X11 setups distinguish XTEST keys from XSendEvent.
    // Probe both without ever sending duplicate F8 toggle events.
    if (!existsSync(urlFile + '.key')) {
      await exec('xdotool', ['key', '--window', window, 'F10'],
        { timeout: 5000 });
    }
    await eventually(async () => {
      await ensureEngine();
      return existsSync(urlFile + '.key') &&
        (await readFile(urlFile + '.key', 'utf8')).includes('F10');
    }, 10000);
    await key(window, 'F8');
    const rawUrl = await eventually(async () => {
      await ensureEngine();
      if (!existsSync(urlFile)) return null;
      const lines = (await readFile(urlFile, 'utf8')).trim().split('\n');
      return lines.find((line) => /^http:\/\/127\.0\.0\.1:\d+\/#token=[a-f0-9]{64}$/.test(line));
    }, 20000);
    const host = new URL(rawUrl);
    const token = new URLSearchParams(host.hash.slice(1)).get('token');
    const origin = host.origin;
    const headers = { 'X-Inspector-Token': token };
    const getSnapshot = async () => {
      const response = await page.request.get(origin + '/api/v1/snapshot', {
        headers, timeout: 5000,
      });
      expect(response.status()).toBe(200);
      return response.json();
    };
    const gameValue = async () => {
      const result = await getSnapshot();
      const node = result.scopes?.store?.find((item) => item.name === 'e2e_value');
      return { result, value: node?.preview };
    };
    const getChildren = async (name, offset = 0) => {
      const params = new URLSearchParams({
        scope: 'store', path: JSON.stringify([['attribute', name]]),
        offset: String(offset), size: '80',
      });
      const response = await page.request.get(origin + '/api/v1/children?' + params, {
        headers, timeout: 7000,
      });
      expect(response.status()).toBe(200);
      return response.json();
    };
    const storedFavourites = async () => {
      const response = await page.request.get(origin + '/api/v1/favourites', {
        headers, timeout: 5000,
      });
      expect(response.status()).toBe(200);
      return (await response.json()).favourites ?? [];
    };
    const revealVariable = async (name) => {
      await page.getByRole('tab', { name: 'Variables', exact: true }).click();
      await page.getByRole('tab', { name: 'Store', exact: true }).click();
      await page.getByRole('button', { name: 'Search variables' }).click();
      await page.getByRole('textbox', {
        name: 'Search variables across Store and Persistent',
      }).fill(name);
      const hits = page.getByRole('listbox', { name: 'Matching game variables' });
      const match = hits.getByRole('option').filter({ hasText: name }).first();
      await expect(match).toBeVisible();
      await match.click();
      await expect(page.getByRole('button', { name: 'Inspect ' + name, exact: true }))
        .toBeVisible();
    };
    await expect.poll(async () => (await gameValue()).value, { timeout: 10000 })
      .toBe('1');
    // This is an actual running Ren'Py interpreter, not the synthetic fixture.
    const initial = await getSnapshot();
    expect(initial.game?.version).toContain(process.env.RENPY_VERSION);
    expect(initial.scopes.store.some((node) => node.name === 'e2e_container')).toBeTruthy();
    const unauth = await page.request.get(origin + '/api/v1/snapshot');
    expect(unauth.status()).toBe(401);

    await page.goto(rawUrl);
    await expect(page.getByRole('tab', { name: 'Variables' })).toBeVisible();
    // A real Ren'Py Store has hundreds of engine-owned root variables. Ant
    // virtualisation correctly keeps e2e_value out of the initial viewport.
    // Use the actual bounded search/reveal flow to scroll to the game value.
    await revealVariable('e2e_value');
    await page.getByRole('button', { name: 'Add e2e_value to favourites' }).click();
    const valueKey = JSON.stringify(['store', [['attribute', 'e2e_value']]]);
    await expect.poll(async () => (await storedFavourites()).some(
      (pin) => pin.scope === 'store' && pin.key === valueKey
    ), { timeout: 15000 }).toBeTruthy();
    await expect(page.getByRole('tab', { name: /Favourites \(1\)/ })).toBeVisible();
    await page.getByRole('tab', { name: 'Overview' }).click();
    await expect(page.getByText('Connected', { exact: true })).toBeVisible();

    // F8 must reopen the SAME token/port, rather than starting a second server.
    await key(window, 'F8');
    await expect.poll(async () => (await readFile(urlFile, 'utf8')).trim().split('\n').length,
      { timeout: 5000 }).toBeGreaterThanOrEqual(2);
    const second = (await readFile(urlFile, 'utf8')).trim().split('\n')[1];
    expect(second).toBe(rawUrl);

    // Real engine state change via a native key event, observed in HTTP + UI.
    await key(window, 'space');
    await expect.poll(async () => (await gameValue()).value, { timeout: 12000 }).toBe('2');
    await page.getByRole('tab', { name: 'Variables' }).click();
    await expect(page.locator('.variable-row').filter({
      has: page.locator('.variable-key', { hasText: /^e2e_value$/ }),
    }).locator('.variable-preview')).toHaveText('2', { timeout: 12000 });

    // Save is an actual Ren'Py FileSave action bound only by this fixture.
    await key(window, 'F5');
    await delay(1200);
    await key(window, 'space');
    await expect.poll(async () => (await gameValue()).value, { timeout: 12000 }).toBe('3');
    const beforeLoad = (await getSnapshot()).generation;
    // FileLoad must trigger the registered after_load callback, invalidating
    // the previous inspector generation without changing the saved game.
    await key(window, 'F9');
    await expect.poll(async () => (await gameValue()).value, { timeout: 16000 }).toBe('2');
    await expect.poll(async () => (await getSnapshot()).generation,
      { timeout: 10000 }).toBeGreaterThan(beforeLoad);

    // The pin lives in inspector-owned preferences, not Ren'Py save state.
    await page.getByRole('tab', { name: /Favourites \(1\)/ }).click();
    const pinnedValue = page.locator('.variable-row').filter({
      has: page.locator('.variable-key', { hasText: /^e2e_value$/ }),
    }).locator('.variable-preview');
    await expect(pinnedValue).toHaveText('2', { timeout: 15000 });
    await page.reload();
    await expect(page.getByRole('tab', { name: /Favourites \(1\)/ })).toBeVisible();
    await page.getByRole('tab', { name: /Favourites \(1\)/ }).click();
    await expect(pinnedValue).toHaveText('2', { timeout: 15000 });
    expect((await storedFavourites()).some(
      (pin) => pin.scope === 'store' && pin.key === valueKey
    )).toBeTruthy();

    // Ren'Py's real rollback hotkey. Its exact checkpoint placement is
    // engine-specific, so require a game-generation invalidation and verify
    // that the resulting preview remains a valid game-owned value.
    const beforeRollback = (await getSnapshot()).generation;
    await key(window, 'Prior');
    await expect.poll(async () => (await getSnapshot()).generation,
      { timeout: 12000 }).toBeGreaterThan(beforeRollback);
    expect(['1', '2', '3']).toContain((await gameValue()).value);

    // A generation reset intentionally discards prior search/reveal and
    // virtual-tree scroll state. Check connection, not an off-screen row.
    await page.getByRole('tab', { name: 'Overview' }).click();
    await expect(page.getByText('Connected', { exact: true })).toBeVisible();
    // The HTTP generation can advance before the browser's 1250ms poll
    // observes rollback. A late React reset would close an in-flight search.
    // Reload the real authenticated session before starting new UI actions.
    await page.reload();
    await expect(page.getByRole('tab', { name: /Favourites \(1\)/ })).toBeVisible();
    // Exercise a 170-item *actual Ren'Py Store list*, not a mock collection.
    // A virtual list must request offset 80 when scrolled into view.
    await revealVariable('e2e_inventory');
    const inventory = page.locator('.variable-row').filter({
      has: page.locator('.variable-key', { hasText: /^e2e_inventory$/ }),
    });
    const listPath = JSON.stringify([['attribute', 'e2e_inventory']]);
    let secondPageObserved = false;
    page.on('response', (response) => {
      if (response.status() !== 200) return;
      const url = new URL(response.url());
      if (url.pathname === '/api/v1/children' &&
          url.searchParams.get('path') === listPath &&
          url.searchParams.get('offset') === '80') secondPageObserved = true;
    });
    await inventory.locator('.variable-label-expandable').click();
    await expect.poll(async () => (await getChildren('e2e_inventory')).items.length,
      { timeout: 15000 }).toBe(80);
    const treeViewport = page.locator('.ant-tree-list-holder').first();
    await expect.poll(async () => {
      // Virtual rows may put the collection anywhere in the full Store tree.
      // Sweep the viewport until its child-page sentinel enters view.
      await treeViewport.evaluate((element) => {
        if (element.scrollTop + element.clientHeight + 4 >= element.scrollHeight) {
          element.scrollTop = 0;
        } else {
          element.scrollTop += Math.max(230, element.clientHeight * 0.75);
        }
      });
      return secondPageObserved;
    }, { timeout: 24000, intervals: [250, 350, 400] }).toBeTruthy();
    expect((await getChildren('e2e_inventory', 80)).items.length).toBe(80);

    // SetVariable runs on the actual engine's interaction thread.
    // Its shorter list must retire old offset pages in the browser.
    await key(window, 'F6');
    await expect.poll(async () => (await getChildren('e2e_inventory')).items.length,
      { timeout: 16000 }).toBe(12);
    expect((await getChildren('e2e_inventory', 80)).items).toHaveLength(0);
    await expect(inventory.locator('.variable-preview')).toHaveText('12 items',
      { timeout: 18000 });

    // Replace a previously expanded dict with an int in the SAME generation.
    // The tree must not resurrect children sampled before replacement.
    await revealVariable('e2e_container');
    const containerRow = page.locator('.variable-row').filter({
      has: page.locator('.variable-key', { hasText: /^e2e_container$/ }),
    });
    await containerRow.locator('.variable-label-expandable').click();
    await expect(page.getByRole('button', { name: /Inspect.*hp/i }))
      .toBeVisible();
    await page.getByRole('button', { name: /Add.*hp.*to favourites/i }).click();
    await expect(page.getByRole('tab', { name: /Favourites \(2\)/ })).toBeVisible();
    await key(window, 'F7');
    await expect(containerRow.locator('.variable-preview')).toHaveText('7',
      { timeout: 18000 });
    await expect(containerRow.locator('.variable-label-expandable')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Inspect.*hp/i }))
      .toHaveCount(0);

    // The same durable nested pin must now resolve to <missing>, not an old 10.
    const hpKey = JSON.stringify(['store', [
      ['attribute', 'e2e_container'], ['key', 'hp'],
    ]]);
    await expect.poll(async () => (await storedFavourites()).some(
      (pin) => pin.scope === 'store' && pin.key === hpKey
    ), { timeout: 15000 }).toBeTruthy();
    await page.getByRole('tab', { name: /Favourites \(2\)/ }).click();
    const hpPinned = page.locator('.variable-row').filter({
      has: page.locator('.variable-key', { hasText: /hp/ }),
    }).locator('.variable-preview');
    await expect(hpPinned).toHaveText('<missing>', { timeout: 18000 });
    await page.reload();
    await page.getByRole('tab', { name: /Favourites \(2\)/ }).click();
    await expect(hpPinned).toHaveText('<missing>', { timeout: 18000 });

    await page.screenshot({ path: join(results, 'runtime-inspector.png') });
  } catch (error) {
    try {
      const focused = await exec('xdotool', ['getwindowfocus', 'getwindowname']);
      const geometry = await exec('xdotool', ['getactivewindow', 'getwindowgeometry', '--shell']);
      console.error('X11 focused window: ' + focused.stdout.trim());
      console.error('X11 active geometry: ' + geometry.stdout.trim());
    } catch (diagnostic) {
      console.error('X11 focus diagnostic failed: ' + diagnostic.message);
    }
    try {
      await exec('scrot', [join(results, 'native-xvfb-screen.png')],
        { timeout: 5000 });
      console.error('Captured real RenPy Xvfb screen for CI artifact');
    } catch (diagnostic) {
      console.error('X11 screenshot failed: ' + diagnostic.message);
    }
    let output = '';
    try { output = await readFile(gameLog, 'utf8'); } catch { /* no log */ }
    console.error('Real Ren\'Py failure (last engine lines):\n' + tail(output));
    throw error;
  } finally {
    // A minimal fixture has no quit confirmation UI. Graceful SIGTERM can
    // trigger an unrelated Ren'Py yes/no layout exception while tearing down.
    // Stop this disposable process group directly after all assertions.
    try { process.kill(-engine.pid, 'SIGKILL'); } catch { /* already exited */ }
    await delay(150);
    await rm(home, { recursive: true, force: true });
  }
});
