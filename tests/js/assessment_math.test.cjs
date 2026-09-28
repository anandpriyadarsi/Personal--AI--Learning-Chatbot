const {test} = require('node:test');
const assert = require('node:assert/strict');

const math = require('../personal_learning_assistant/ui/web/static/js/assessment_math.js');

test('math renderer normalizes common linear algebra symbols', () => {
  assert.equal(math.replaceSymbols('\\lambda != 0'), 'λ ≠ 0');
  assert.equal(math.replaceSymbols('x \\in \\mathbb{R}'), 'x ∈ ℝ');
  assert.equal(math.replaceSymbols('S \\cap T'), 'S ∩ T');
});

test('math renderer reads superscript and subscript tokens safely', () => {
  assert.deepEqual(math.readScriptToken('{-1}', 0), {value: '-1', end: 4});
  assert.deepEqual(math.readScriptToken('B rest', 0), {value: 'B', end: 1});
});

test('math renderer recognizes rectangular matrix literals', () => {
  const parsed = math.parseMatrixAt('A = [[1, 2], [3, 4]]', 4);
  assert.deepEqual(parsed.rows, [['1', '2'], ['3', '4']]);
  assert.equal(parsed.end, 20);
});

test('math renderer leaves malformed matrix text unparsed', () => {
  assert.equal(math.parseMatrixAt('[[1, 2], [3]]', 0), null);
});
