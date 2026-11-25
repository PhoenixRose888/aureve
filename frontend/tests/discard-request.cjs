const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

test('discard resets the generated look and request without deleting saved data', () => {
  const source = fs.readFileSync(path.join(__dirname, '../app/(tabs)/dressme.tsx'), 'utf8');
  const ast = ts.createSourceFile('dressme.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let discard;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'discard') discard = node.initializer.getText(ast);
    ts.forEachChild(node, visit);
  }
  visit(ast);
  assert.ok(discard);
  const values = {};
  const setters = ['setResult', 'setOutcome', 'setRequest', 'setFollowupQ', 'setFollowupA',
                   'setCalendarLabel', 'setSwapIndex', 'setSearch', 'setError', 'setPhase'];
  const run = new Function('haptics', ...setters, `return (${discard})();`);
  run({ tap() {} }, ...setters.map((name) => (value) => { values[name] = value; }));
  assert.deepEqual(values, { setResult: null, setOutcome: '', setRequest: '', setFollowupQ: '',
    setFollowupA: '', setCalendarLabel: '', setSwapIndex: null, setSearch: '', setError: '', setPhase: 'ask' });
});
