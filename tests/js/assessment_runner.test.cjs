const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('personal_learning_assistant/ui/web/static/js/assessment_runner.js', 'utf8');
class Element {
  constructor(props={}) { Object.assign(this, {listeners:{},dataset:{},value:'',type:'text',tagName:'INPUT',textContent:'',hidden:false,disabled:false}, props); this.classList={toggle(){}}; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  async emit(name, extra={}) { const e={preventDefault(){this.prevented=true},...extra}; for(const fn of this.listeners[name]||[]) await fn(e); return e; }
  setAttribute() {}
}
const settle = async () => { for(let i=0;i<15;i++) await Promise.resolve(); };
function harness(type='numerical') {
  let now=0, serial=0, responder=async()=>({status:'active',remaining_seconds:3600,state:'answered',palette_counts:{answered:2,not_answered:1,not_visited:1,marked_for_review:1,answered_marked_for_review:1}});
  const timers=new Map(), intervals=new Map(), calls=[], navigations=[], confirmations=[];
  const input=new Element({name:type==='long_subjective'?'answer_text':'answer_value',value:type==='true_false'?'True':'',type:type==='true_false'?'radio':'text'});
  const fieldset=new Element(), focus=new Element({type:'hidden'}), button=new Element({value:'save_next'});
  const form=new Element({action:'/action'});
  form.querySelectorAll=(selector)=>selector==='input, textarea'?[input]:selector.includes(':checked')?[]:[button];
  form.querySelector=(selector)=>selector==='fieldset'?fieldset:selector.includes(':checked')?null:input;
  const nav=new Element({href:'/next'}), submit=new Element(), retry=new Element(), status=new Element(), timer=new Element();
  const root=new Element({dataset:{sessionId:'s',questionId:'q',questionType:type,remainingSeconds:'3600',heartbeatUrl:'/heartbeat',autosaveUrl:'/autosave',submitUrl:'/submit',summaryUrl:'/summary'}});
  const nodes={'assessment-runner':root,'assessment-response-form':form,'assessment-submit-form':submit,'assessment-timer':timer,'assessment-save-status':status,'assessment-focus-seconds':focus,'assessment-save-retry':retry};
  const document=new Element({visibilityState:'visible',getElementById:id=>nodes[id]||null,querySelectorAll:selector=>selector==='[data-runner-nav]'?[nav]:[]});
  const window=new Element({location:{assign:url=>navigations.push(url)},setTimeout:(fn)=>{timers.set(++serial,fn);return serial},clearTimeout:id=>timers.delete(id),setInterval:(fn,ms)=>{intervals.set(ms,fn)},confirm:message=>{confirmations.push(message);return window.confirmResult},confirmResult:true});
  const fetch=async(url,opts)=>{const payload=JSON.parse(opts.body);calls.push({url,payload});const data=await responder(url,payload);return {ok:true,json:async()=>data}};
  vm.runInNewContext(source,{document,window,performance:{now:()=>now},fetch,URLSearchParams,FormData,console});
  return {input,form,button,nav,submit,retry,status,window,document,calls,navigations,confirmations,
    setResponder:fn=>responder=fn,advance:ms=>{now+=ms},interval:async ms=>{await intervals.get(ms)();await settle()},
    edit:async value=>{input.value=value;await input.emit('input');await input.emit('change')},
    debounce:async()=>{const tasks=[...timers.values()];timers.clear();tasks.forEach(fn=>fn());await settle()}};
}
test('untouched true/false remains unanswered when leaving the question',async()=>{
  const h=harness('true_false');await h.nav.emit('click');
  assert.equal(h.calls.find(x=>x.url==='/autosave').payload.response.value,'');
});
test('failed save blocks navigation and submission and offers retry',async()=>{
  for(const action of ['nav','submit']){
    const h=harness();await h.edit('42');h.setResponder(async()=>{throw Error('offline')});await h[action].emit(action==='nav'?'click':'submit');
    assert.deepEqual(h.navigations,[]);assert.equal(h.calls.some(x=>x.url==='/submit'),false);assert.equal(h.input.value,'42');assert.match(h.status.textContent,/not saved/i);assert.equal(h.retry.hidden,false);
  }
});
test('autosaves serialize and finish with the latest edit',async()=>{
  const h=harness();let release;h.setResponder(()=>new Promise(resolve=>{release=resolve}));
  await h.edit('old');await h.debounce();assert.equal(h.calls.length,1);
  await h.edit('new');await h.debounce();assert.equal(h.calls.length,1);
  h.setResponder(async()=>({status:'active',state:'answered'}));release({status:'active',state:'answered'});await settle();
  assert.equal(h.calls.length,2);assert.equal(h.calls[1].payload.response.value,'new');assert.match(h.status.textContent,/saved/i);
});
test('clear waits for prior autosave then performs the clear once',async()=>{
  const h=harness();let release;h.setResponder(()=>new Promise(resolve=>{release=resolve}));
  await h.edit('old');await h.debounce();const action=h.form.emit('submit',{submitter:{value:'clear'}});await settle();
  assert.equal(h.calls.length,1);h.setResponder(async()=>({status:'active',redirect_url:'/current'}));release({status:'active'});await action;
  assert.deepEqual(h.calls.map(x=>x.url),['/autosave','/action']);assert.equal(h.calls[1].payload.action,'clear');assert.deepEqual(h.navigations,['/current']);
});
test('focus includes the visible interval before hiding and excludes hidden time',async()=>{
  const h=harness();h.advance(5000);h.document.visibilityState='hidden';await h.document.emit('visibilitychange');
  h.advance(15000);h.document.visibilityState='visible';await h.document.emit('visibilitychange');h.advance(10000);await h.interval(30000);
  assert.equal(h.calls[0].payload.focus_seconds_delta,15);
});
test('submit confirms current saved counts and cancellation keeps session active',async()=>{
  const h=harness();h.window.confirmResult=false;await h.submit.emit('submit');
  assert.match(h.confirmations[0],/3 answered/);assert.match(h.confirmations[0],/3 unanswered/);assert.match(h.confirmations[0],/2 marked/);
  assert.equal(h.calls.some(x=>x.url==='/submit'),false);assert.deepEqual(h.navigations,[]);
});
test('unsaved changes warn on page close and successful retry removes the warning',async()=>{
  const h=harness();await h.edit('42');h.setResponder(async()=>{throw Error('offline')});await h.debounce();
  assert.equal((await h.window.emit('beforeunload')).prevented,true);
  h.setResponder(async()=>({status:'active',state:'answered'}));await h.retry.emit('click');
  assert.equal((await h.window.emit('beforeunload')).prevented,undefined);
});
test('failed clear or final submit preserves the page and re-enables the answer',async()=>{
  for(const action of ['clear','submit']) {
    const h=harness();await h.edit('42');
    h.setResponder(async url=>{
      if(url==='/action'||url==='/submit') throw Error('offline');
      return {status:'active',remaining_seconds:3600,palette_counts:{answered:1,answered_marked_for_review:0,not_answered:0,not_visited:0,marked_for_review:0}};
    });
    await (action==='clear'?h.form.emit('submit',{submitter:{value:'clear'}}):h.submit.emit('submit'));
    assert.deepEqual(h.navigations,[]);assert.equal(h.input.value,'42');assert.equal(h.form.querySelector('fieldset').disabled,false);assert.match(h.status.textContent,/action failed/i);
  }
});
