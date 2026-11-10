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
