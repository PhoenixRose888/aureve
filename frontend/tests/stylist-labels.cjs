const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function loadTs(relativePath, overrides = {}) {
  const source = fs.readFileSync(path.join(__dirname, relativePath), 'utf8');
  const result = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
  });
  const exported = {};
  new Function('exports', 'require', result.outputText)(exported, (name) => overrides[name] || require(name));
  return exported;
}
const { shortItemName, shortItemReferences } = loadTs('../src/utils/itemLabel.ts');

for (const [full, short] of [
  ['Black open-front blazer', 'Black open-front'],
  ['Black wide-leg trousers', 'Black wide-leg'],
  ['Champagne satin long-sleeve blouse', 'Champagne satin long-sleeve'],
  ['White Calvin Klein logo t-shirt', 'White Calvin Klein logo'],
  ['Dress', 'Dress'],
]) {
  test(`short label for ${full}`, () => assert.equal(shortItemName(full), short));
}

test('chat references are replaced once with longest exact name first', () => {
  const items = [{ name: 'Black top blouse' }, { name: 'Black top' }];
  assert.equal(shortItemReferences('Try **Black top blouse**.', items), 'Try **Black top**.');
});

test('punctuation in brands is literal and unrelated words are preserved', () => {
  const items = [{ name: "Black Levi's (501) jeans" }];
  assert.equal(shortItemReferences("Try Black Levi's (501) jeans, then jeanswear.", items), "Try Black Levi's (501), then jeanswear.");
});

test('saved stylist replies render emphasis and list markers as formatting', () => {
  const { default: Message } = loadTs('../src/components/StylistMessage.tsx', {
    'react-native': { View: ({ children }) => React.createElement('div', null, children) },
    '@/src/components/Typography': { Txt: ({ children, style }) => React.createElement('span', { style }, children) },
    '@/src/theme': { fonts: { displayBold: 'Inter-Bold' }, spacing: { md: 12 } },
  });
  const html = renderToStaticMarkup(React.createElement(Message, { content: 'Try **Black open-front**.\n\n- *Champagne satin*\n- Cream textured' }));
  assert.ok(html.includes('Inter-Bold'));
  assert.ok(html.includes('font-style:italic'));
  assert.ok(html.includes('• '));
  assert.ok(!html.includes('**'));
  assert.ok(!html.includes('*Champagne'));
});
