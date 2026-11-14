import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const jsx = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('./style.css', import.meta.url), 'utf8');

test('SugarCube-style top-level and nested variable scope navigation', () => {
  for (const key of ["key: 'overview'", "key: 'variables'", "key: 'scripts'", "key: 'store'", "key: 'persistent'", "key: 'favourites'"]) {
    assert.ok(jsx.includes(key), `Missing navigation ${key}`);
  }
  assert.match(jsx, /className="main-navigation"/);
  assert.match(jsx, /className="variable-scope-tabs"/);
  assert.doesNotMatch(jsx, /<Sider|<aside className="tree-sider"|className="workspace-layout"/);
});

test('tree occupies the full available workspace with a measured viewport', () => {
  assert.match(css, /\.variables-workspace \{ display: flex; flex-direction: column; flex: 1 1 auto/);
  assert.match(css, /\.variable-tree-viewport \{ flex: 1 1 auto; min-height: 0/);
  assert.match(jsx, /ResizeObserver/);
  assert.match(jsx, /virtual height=\{height\}/);
  assert.match(jsx, /showLine=\{\{ showLeafIcon: false \}\}/);
});

test('inline preview and pin, details on demand and strict read-only mode', () => {
  assert.match(jsx, /variable-type/);
  assert.match(jsx, /variable-preview/);
  assert.match(jsx, /row-icon-button/);
  assert.match(jsx, /<Drawer title="Variable details"/);
  assert.match(jsx, /Captured value preview/);
  assert.match(jsx, /read-only snapshot/);
  assert.doesNotMatch(jsx, /Save value|Undo edit|Lock value|POST/);
});

test('small viewports preserve legible, unsqueezed navigation', () => {
  assert.match(css, /@media \(max-width: 680px\)/);
  assert.doesNotMatch(css, /grid-template-columns:minmax\(300px,420px\)/);
  assert.doesNotMatch(css, /flex-direction:column!important/);
});


test('two tab layers are the only permanent controls above the tree', () => {
  assert.doesNotMatch(jsx, /<header className="inspector-header"|className="product-brand"/);
  assert.doesNotMatch(jsx, /<footer|variable-pane-footer|variable-pane-summary|variables-toolbar/);
  assert.doesNotMatch(css, /inspector-header|inspector-statusbar|variable-pane-summary|variable-pane-footer/);
  assert.match(jsx, /className="main-navigation"/);
  assert.match(jsx, /className="variable-scope-tabs"/);
  assert.match(css, /min-height: 34px/);
  assert.match(css, /min-height: 33px/);
});

test('search opens as a transient popover without a refresh button', () => {
  assert.match(jsx, /<Popover placement="bottomRight"/);
  assert.match(jsx, /tabBarExtraContent=\{<Popover/);
  assert.match(jsx, /aria-label=\{query \? 'Search variables \(filter active\)' : 'Search variables'\}/);
  assert.match(jsx, /searchRef\.current\?\.focus\(\)/);
  assert.match(jsx, /setQuery\(event\.target\.value\)/);
  assert.match(jsx, /event\.key === 'Escape'/);
  assert.doesNotMatch(jsx, /ReloadOutlined|setRefresh|Refresh snapshot/);
});

test('session and snapshot diagnostics live in Overview', () => {
  for (const label of ['Connection', 'Capture limits', 'Coverage', 'Access', 'Last capture']) {
    assert.ok(jsx.includes("label: '"+label+"'"), 'Missing Overview field '+label);
  }
});


test('only the virtual tree may scroll; the document and app shell never scroll', () => {
  assert.match(css, /html, body, #root \{[\s\S]*?overflow: hidden;/);
  assert.match(css, /\.inspector-shell \{[\s\S]*?max-height:100dvh;/);
  assert.match(css, /\.full-width-variable-tree \.ant-tree-list-holder \{[\s\S]*?overflow-x: hidden !important; overflow-y: auto;/);
  assert.match(css, /overscroll-behavior-y: contain;/);
});

test('tree descendants and variable labels cannot widen the page', () => {
  assert.match(css, /\.full-width-variable-tree \.ant-tree-treenode \{[^\n]*width: auto; max-width: 100%; min-width: 0;/);
  assert.doesNotMatch(css, /\.full-width-variable-tree \.ant-tree-treenode \{\s*width: 100%/);
  assert.match(css, /\.ant-tree-node-content-wrapper \{[^\n]*min-width: 0; max-width: 100%/);
  assert.match(css, /\.variable-label \{[^\n]*max-width: 56%/);
  assert.match(css, /\.variable-type \{[^\n]*text-overflow: ellipsis/);
  assert.match(css, /\.variable-row \{[^\n]*max-width: 100%/);
});


test('SugarCube-style subscriptions use one bounded shared scheduler', () => {
  assert.match(jsx, /collectWatchedPages/);
  assert.match(jsx, /nextEligibleWatchBatch/);
  assert.match(jsx, /MAX_BACKGROUND_IN_FLIGHT/);
  assert.match(jsx, /WATCH_INTERVAL_MS/);
  assert.match(jsx, /window\.setInterval\(\(\) => \{/);
  assert.match(jsx, /refreshWatchedPage\(prior, data, parentKey/);
  assert.doesNotMatch(jsx, /<WebSocket|new WebSocket|EventSource/);
});


test('browser preferences use authenticated inspector-only storage', () => {
  assert.match(jsx, /api\/v1\/favourites/);
  assert.match(jsx, /method: 'PUT'/);
  assert.match(jsx, /api\/v1\/value/);
  assert.match(jsx, /requestFavouriteValue/);
  assert.match(jsx, /combineScopedWatches/);
  assert.match(jsx, /Favourite storage/);
});


test('Compare lives in the existing second tab row without shrinking the virtual tree', () => {
  assert.match(jsx, /key: 'compare', label: \`Compare/);
  assert.match(jsx, /scope === 'compare'/);
  assert.match(jsx, /<ComparePane changes=\{changes\}/);
  assert.match(jsx, /<VariablePane scope=\{scope\}/);
  assert.match(css, /\.compare-workspace \{ display:flex; flex:1 1 auto;/);
  assert.doesNotMatch(jsx, /new WebSocket|EventSource|Save gameplay/);
});

test('changes are derived from the existing shallow root, page and favourite samples', () => {
  assert.match(jsx, /trackerRef\.current\.observePage/);
  assert.match(jsx, /trackerRef\.current\.observeValue/);
  assert.match(jsx, /trackerRef\.current\.beginGeneration/);
  assert.match(jsx, /requestFavouriteValue/);
  assert.match(jsx, /clearHistory/);
  assert.match(jsx, /selectedHistory/);
});

test('auxiliary Compare, Locked, Edits and Pin history reuse the last tree scope', () => {
  assert.match(jsx, /lastTreeScope/);
  assert.match(jsx, /scope === 'compare' \|\| scope === 'edits' \|\| scope === 'locked' \|\|/);
  assert.match(jsx, /scope === 'pin-history'/);
  assert.match(jsx, /scope === 'locked' && snapshot\?\.capabilities\?\.primitive_edits === true/);
  assert.match(jsx, /<LockedVariablesPane locks=\{snapshot\?\.locks\}/);
  assert.match(jsx, /<FavouriteHistoryPane favourites=\{favourites\}/);
});


test('global search stays inside popup and reveals through the virtual Tree', () => {
  assert.match(jsx, /api\/v1\/search/);
  assert.match(jsx, /api\/v1\/reveal/);
  assert.match(jsx, /scope: 'all', q: term/);
  assert.match(jsx, /window\.setTimeout\(async \(\) => \{/);
  assert.match(jsx, /integrateRevealChain/);
  assert.match(jsx, /revealParentKeys/);
  assert.match(jsx, /treeRef\.current\?\.scrollTo\?\.\(\{ key: revealTarget\.key \}\)/);
  assert.match(jsx, /role="listbox" aria-label="Matching game variables"/);
  assert.doesNotMatch(jsx, /permanent-search-toolbar|new WebSocket/);
});


test('Scripts tab provides independent label navigation and read-only source viewer', () => {
  assert.match(jsx, /import ScriptPane from '.\/ScriptPane\.jsx'/);
  assert.match(jsx, /section === 'scripts' && <ScriptPane token=\{token\}/);
  assert.doesNotMatch(jsx, /Full source browsing is not supported/);
  assert.match(css, /\.script-workspace \{ display:grid;/);
  assert.match(css, /\.script-label-list \{ flex:1 1 auto;/);
  assert.match(css, /\.script-source-pane \{ min-width:0;min-height:0;/);
  assert.match(css, /@media \(max-width:670px\)/);
});

test('pin history reuses the existing comparison samples and does not grow the permanent chrome', () => {
  assert.match(jsx, /key: 'pin-history', label: `Pin history/);
  assert.match(jsx, /trackerRef\.current\.setFavourites\(favourites\)/);
  assert.match(jsx, /trackerRef\.current\.getFavouriteChanges\(\)/);
  assert.match(jsx, /trackerRef\.current\.getFavouriteBaselineKeys\(\)/);
  assert.match(jsx, /trackerRef\.current\.clearFavouriteHistory\(\)/);
  assert.match(jsx, /View pinned variable history/);
  assert.match(css, /\.pin-history-workspace \{ display:flex;/);
  assert.match(css, /\.pin-history-list \{ flex:1 1 auto;/);
  assert.doesNotMatch(jsx, /new WebSocket|EventSource|new SetInterval/);
});
