const {test} = require('node:test');
const assert = require('node:assert/strict');
const helper = require('../../personal_learning_assistant/ui/web/static/js/assessment_coding_helper.js');

test('readable sections, code and predicted output preserve inert strings', () => {
  const blocks = helper.parseReply('## Explanation\nThink first.\n\n```python\nprint("<img onerror=x>")\n```\n```output\n<img onerror=x>\n```\nTry this yourself:\nChange one value.');
  assert.deepEqual(blocks.map(b => b.kind), ['heading','text','code','output','heading','text']);
  assert.equal(blocks[2].text, 'print("<img onerror=x>")');
  assert.equal(blocks[3].text, '<img onerror=x>');
});
test('unclosed fences stay code; arbitrary markup and links stay literal', () => {
  assert.deepEqual(helper.parseReply('<script>x</script> [x](javascript:x)'), [{kind:'text',text:'<script>x</script> [x](javascript:x)'}]);
  assert.deepEqual(helper.parseReply('```python\na = 1'), [{kind:'code',text:'a = 1'}]);
});
test('history is resettable; cancelled and stale completions cannot restore it', () => {
  const state = helper.createConversation();
  const first=state.start();
  assert.equal(state.finish(first, 'token'), true);
  assert.equal(state.token, 'token');
  const second=state.start(); state.reset();
  assert.equal(state.finish(second, 'stale'), false);
  assert.equal(state.token, '');
  const third=state.start();
  assert.equal(state.finish(third, 'new'), true);
  const fourth=state.start(); state.cancel();
  assert.equal(state.finish(fourth, 'late'), false);
  assert.equal(state.token, 'new');
});
