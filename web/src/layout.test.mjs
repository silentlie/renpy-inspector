import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const jsx = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('./style.css', import.meta.url), 'utf8');

test('workspace uses a single deterministic layout, not responsive Sider', () => {
  assert.match(jsx, /<div className="workspace-layout">/);
  assert.match(jsx, /<aside className="tree-sider">/);
  assert.match(jsx, /<main className="main-content">/);
  assert.doesNotMatch(jsx, /<Sider|breakpoint="lg"|collapsedWidth/);
});

test('desktop columns are bounded and mobile stacks instead of collapsing details', () => {
  assert.match(css, /grid-template-columns:minmax\(300px,420px\) minmax\(0,1fr\)/);
  assert.match(css, /@media \(max-width: 960px\)/);
  assert.match(css, /grid-template-columns:minmax\(0,1fr\)/);
  assert.match(css, /\.main-content \{ min-height:560px;min-width:0;width:100% \}/);
  assert.doesNotMatch(css, /flex-direction:column!important|flex:auto!important/);
});

test('tall narrow windows have capped virtual tree height', () => {
  assert.match(jsx, /window\.innerWidth <= 960/);
  assert.match(jsx, /Math\.min\(460, Math\.round\(window\.innerHeight \* 0\.46\)\)/);
});
