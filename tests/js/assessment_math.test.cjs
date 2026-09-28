const {test} = require('node:test');
const assert = require('node:assert/strict');
const math = require('../../personal_learning_assistant/ui/web/static/js/assessment_math.js');

test('normalizes common linear algebra symbols without HTML interpretation', () => {
  assert.equal(
    math.replaceSymbols('A^T \\cap B != C, \\lambda <= \\mu'),
    'A^T ∩ B ≠ C, λ ≤ μ'
  );
  assert.equal(math.replaceSymbols('<img src=x onerror=alert(1)>'), '<img src=x onerror=alert(1)>');
});

test('parses rectangular matrix literals used by authored assessment packages', () => {
  const parsed = math.parseMatrixAt('A = [[1, 2], [-3, λ]]', 4);
  assert.deepEqual(parsed.rows, [['1', '2'], ['-3', 'λ']]);
  assert.equal(parsed.end, 'A = [[1, 2], [-3, λ]]'.length);
});

test('reads grouped and signed superscript/subscript tokens', () => {
  assert.deepEqual(math.readScriptToken('{-1}', 0), {value: '-1', end: 4});
  assert.deepEqual(math.readScriptToken('-1 rest', 0), {value: '-1', end: 2});
  assert.deepEqual(math.readScriptToken('34 rest', 0), {value: '34', end: 2});
});


test('parses determinant literals and common LaTeX matrix environments', () => {
  const determinant = math.parseDeterminantAt('det([[1, 2], [3, 4]]) + 1', 0);
  assert.deepEqual(determinant.rows, [['1', '2'], ['3', '4']]);
  assert.equal(determinant.delimiter, 'determinant');

  const source = String.raw`\begin{vmatrix}1 & 2 \\ 3 & 4\end{vmatrix}`;
  const latex = math.parseLatexMatrixAt(source, 0);
  assert.deepEqual(latex.rows, [['1', '2'], ['3', '4']]);
  assert.equal(latex.delimiter, 'determinant');
  assert.equal(latex.end, source.length);
});
