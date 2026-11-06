const {test}=require('node:test');
const assert=require('node:assert/strict');
const {solutionAllowed,copyExact}=require('../../personal_learning_assistant/ui/web/static/js/tutor_coding.js');
test('solution permission belongs only to the three shared allowed action types',()=>{
  for(const action of ['debug','explain_code','pseudocode']) assert.equal(solutionAllowed(action),true);
  for(const action of ['hint','rebuild','predict','viva','check','forged']) assert.equal(solutionAllowed(action),false);
});
test('copy preserves exact whitespace and Unicode without interpreting HTML',async()=>{
  const text='  α = "</script><img src=x>"\n\tprint(α)\n';let copied;
  assert.equal(await copyExact({textContent:text},{writeText:async value=>{copied=value;}}),true);
  assert.equal(copied,text);
});
test('copy failure leaves content available for manual selection',async()=>{
  const node={textContent:'private draft'};
  assert.equal(await copyExact(node,{writeText:async()=>{throw Error('denied');}}),false);
  assert.equal(node.textContent,'private draft');
});
