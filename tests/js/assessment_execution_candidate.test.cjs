const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('personal_learning_assistant/ui/web/static/js/assessment_execution_candidate.js', 'utf8');
function clock(status, remaining) {
  let elapsed = 0, interval;
  const timer = { textContent: '' }, banner = { focus() {} }, question = { focus() {} };
  const elements = {workspace:{dataset:{status,remaining,revision:'1'}},timer,'state-banner':banner,'save-status':{textContent:''}};
  vm.runInNewContext(source, {document:{getElementById:id=>elements[id],querySelectorAll:()=>[],querySelector:()=>question},performance:{now:()=>elapsed},setInterval:fn=>{interval=fn;}});
  return {read:()=>timer.textContent, advance:ms=>{elapsed+=ms; interval();}};
}
test('paused display remains frozen as wall display time advances',()=>{const c=clock('paused',48000);c.advance(36000000);assert.equal(c.read(),'00:48');});
test('active timer uses remaining milliseconds and ceiling',()=>{const c=clock('active',1001);assert.equal(c.read(),'00:02');c.advance(2);assert.equal(c.read(),'00:01');});
test('active display never becomes negative or mutates server state',()=>{const c=clock('active',1000);c.advance(500000);assert.equal(c.read(),'00:00');});
test('terminal display is frozen',()=>{const c=clock('submitted',9000);c.advance(36000000);assert.equal(c.read(),'00:09');});
