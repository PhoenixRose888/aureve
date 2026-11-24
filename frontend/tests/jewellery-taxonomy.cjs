const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/utils/taxonomy.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
});
const taxonomy = {};
new Function('exports', compiled.outputText)(taxonomy);

const examples = [
  ['Gold chain bracelet', 'Bracelets'],
  ['Silver pendant necklace', 'Necklaces'],
  ['Black velvet choker necklace', 'Chokers'],
  ['Gold ankle chain bracelet', 'Anklets'],
  ['Gold thigh chain', 'Thigh chains'],
  ['Gold waist chain', 'Body jewellery'],
  ['Silver hoop earrings', 'Earrings'],
  ['Silver signet ring', 'Rings'],
  ['Gold chain watch', 'Watches'],
  ['Silver cufflinks', 'Cufflinks'],
  ['Gold cuff links', 'Cufflinks'],
  ['Silver neck chain', 'Necklaces'],
];

for (const [name, expected] of examples) {
  test(`${name} resolves to ${expected}`, () => {
    assert.equal(taxonomy.primarySub({ category: 'Jewellery', name }, 'Jewellery'), expected);
  });
}

for (const type of taxonomy.SUB_ORDER.Jewellery) {
  test(`saved ${type} correction survives reopening and contradictory AI names`, () => {
    const item = { category: 'Jewellery', subcategory: type, name: 'Gold chain necklace' };
    const category = taxonomy.displayCategory(item);
    assert.equal(category, 'Accessories');
    assert.equal(taxonomy.primarySub(item, category), 'Jewellery');
    assert.equal(taxonomy.primarySub(item, 'Jewellery'), type);
  });
}

test('legacy Accessories record with a jewellery subtype stays browsable', () => {
  const item = { category: 'Accessories', subcategory: 'Bracelets', name: 'Gold chain' };
  assert.equal(taxonomy.primarySub(item, 'Accessories'), 'Jewellery');
  assert.equal(taxonomy.primarySub(item, 'Jewellery'), 'Bracelets');
});

test('legacy Jewellery record without a correction is inferred', () => {
  const item = { category: 'Jewellery', name: 'Gold chain bracelet' };
  assert.equal(taxonomy.displayCategory(item), 'Accessories');
  assert.equal(taxonomy.primarySub(item, 'Accessories'), 'Jewellery');
  assert.equal(taxonomy.primarySub(item, 'Jewellery'), 'Bracelets');
});

test('clothing and bag corrections remain effective', () => {
  assert.equal(taxonomy.primarySub({ category: 'Tops', subcategory: 'Singlets', name: 'Logo t-shirt' }, 'Tops'), 'Singlets');
  assert.equal(taxonomy.primarySub({ category: 'Bags', name: 'Gold chain handbag' }, 'Accessories'), 'Bags');
});

test('ties and cufflinks file under their own accessory sections', () => {
  for (const name of ['Navy silk tie', 'Black bow tie', 'Blue necktie']) {
    assert.equal(taxonomy.primarySub({ category: 'Accessories', name }, 'Accessories'), 'Ties');
  }
  assert.equal(taxonomy.primarySub({ category: 'Accessories', name: 'Silver cuff links' }, 'Accessories'), 'Jewellery');
});
