/* Coding context stays in page memory. Nothing executes student code. */
(function (root) {
  'use strict';
  const solutionActions = new Set(['debug', 'explain_code', 'pseudocode']);
  function solutionAllowed(action) { return solutionActions.has(action); }
  function requestId() { return crypto.randomUUID().replaceAll('-', '_'); }
  async function copyExact(node, clipboard) {
    const value = node.textContent;
    try { await clipboard.writeText(value); return true; } catch (_) { return false; }
  }
  function install() {
    const studio = document.getElementById('coding-studio');
    if (!studio) return;
    const $ = id => document.getElementById('coding-' + id);
    const form = document.getElementById('tutor-ask-form');
    const question = document.getElementById('agent-question');
    const base = '/agent/sessions/' + encodeURIComponent(studio.dataset.session);
    const csrf = studio.dataset.csrf;
    let tasks = JSON.parse($('tasks-data').textContent);
    const cards = JSON.parse($('cards-data').textContent);
    let task = null, busy = false, dirty = false, pending = null, preview = null, generation = 0;
    let consentRevision = Number(studio.dataset.consent);
    let waiting = null, suppressLeave = false;
    const status = message => { $('status').textContent = message; };
    async function post(path, data, signal) {
      const response = await fetch(base + path, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify(data), signal});
      if (!response.ok) {
        let problem;
        try { problem = await response.json(); } catch (_) { problem = null; }
        const error = new Error(problem?.error?.message || 'Request failed. Your draft is retained.');
        error.code = problem?.error?.code;
        throw error;
      }
      return response;
    }
    async function json(path, data, signal) { return (await post(path,data,signal)).json(); }
    function tools(open, focus=false) {
      $('tools').hidden = !open;
      document.body.classList.toggle('tutor-tools-open',open);
      $('tools-toggle').setAttribute('aria-expanded',String(open));
      if (focus) (open ? $('task') : $('tools-toggle')).focus();
    }
    $('tools-toggle').addEventListener('click',() => tools($('tools').hidden,true));
    $('tools-close').addEventListener('click',() => tools(false,true));
    document.addEventListener('keydown',event => {
      if (event.key==='Escape' && !$('tools').hidden) { event.preventDefault(); tools(false,true); }
    });
    function setWorkspace(value) {
      studio.dataset.workspace = value;
      form.dataset.workspace = value;
      document.body.classList.toggle('tutor-coding-active',value==='coding');
      document.querySelectorAll('[data-coding-workspace]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.codingWorkspace===value)));
      $('solution').checked = false;
      document.getElementById('tutor-quick-prompts').hidden = true;
      if (value==='academic') tools(false);
      question.maxLength = value==='coding' ? 2000 : 4000;
      question.placeholder = value==='coding' ? 'Ask about your task, or describe what happened…' : 'Ask Alex, or share where you got stuck…';
    }
    setWorkspace(studio.dataset.workspace);
    document.querySelectorAll('[data-coding-workspace]').forEach(button => button.addEventListener('click',async () => {
      if (busy) { status('A reply is in progress. Stop waiting and reopen the conversation to reconcile it.'); return; }
      try {
        await json('/workspace',{workspace:button.dataset.codingWorkspace});
        generation++; setWorkspace(button.dataset.codingWorkspace);
      } catch (error) { status(error.message); }
    }));
    function controls() {
      $('solution-label').hidden = !solutionAllowed($('action').value);
      if (!solutionAllowed($('action').value)) $('solution').checked=false;
      $('download').disabled = !task;
      $('archive').disabled = !task;
      $('task-label').textContent = task ? task.title + ' · v' + task.revision : 'Save a task to begin';
    }
    function selectTask(value) {
      generation++; pending=null; preview=null;
      task = tasks.find(t => t.id===value) || null;
      $('task').value = task?.id || '';
      $('title').value = task?.title || '';
      $('objective').value = task?.snapshot.objective || '';
      $('template').value = task?.template_id || '';
      $('template').disabled = Boolean(task);
      $('code').value = task?.snapshot.code || '';
      $('error').value = ''; $('attempt').value = ''; $('solution').checked = false;
      dirty=false; controls();
    }
    $('task').addEventListener('change',() => {
      if (busy || (dirty && !window.confirm('Discard this unsaved task draft? Sent history stays in the conversation.'))) { $('task').value=task?.id || ''; return; }
      selectTask($('task').value);
      if(task) json('/workspace',{workspace:studio.dataset.workspace,selected_task_id:task.id}).catch(error=>status(error.message));
    });
    $('new').addEventListener('click',() => {
      if (busy || (dirty && !window.confirm('Discard this unsaved task draft and start fresh?'))) return;
      selectTask(''); $('action').value='rebuild';
      // Hide prior answers in the active view, never delete history or resend it.
      document.querySelector('.tutor-transcript')?.setAttribute('data-rebuild','true');
      status('Fresh task. Earlier answers are hidden until you reopen the conversation.');
      $('title').focus();
    });
    $('action').addEventListener('change',() => {
      $('solution').checked=false; controls();
      if($('action').value==='rebuild') $('new').click();
    });
    const draftFields = ['title','objective','topic','code','error','attempt','template'];
    draftFields.forEach(id => $(id).addEventListener('input',() => { dirty=true; }));
    question.addEventListener('input',() => { if(form.dataset.workspace==='coding') dirty=true; });
    window.addEventListener('beforeunload',event => {
      if ((dirty || busy) && !suppressLeave) { event.preventDefault(); event.returnValue=''; }
    });
    async function save() {
      if (busy) return;
      const data = {title:$('title').value,objective:$('objective').value,code:$('code').value};
      let response;
      if (task) response=await json('/coding/tasks/'+task.id,{...data,expected_task_revision:task.revision});
      else response=await json('/coding/tasks',{...data,request_id:requestId(),language:'python',template_id:$('template').value});
      task=response.task;
      const index=tasks.findIndex(t=>t.id===task.id);
      if(index<0) { tasks.push(task); const option=document.createElement('option'); option.value=task.id; option.textContent=task.title; $('task').append(option); }
      else { tasks[index]=task; $('task').selectedOptions[0].textContent=task.title; }
      $('task').value=task.id; $('template').disabled=true; pending=null; dirty=false;
      controls(); status('Task saved locally. No AI request was sent.');
    }
    $('save').addEventListener('click',async()=>{try{await save();}catch(error){status(error.message);}});
    $('archive').addEventListener('click',async()=>{
      if(!task || busy || !window.confirm('Archive this task? Sent code and feedback stay in history.')) return;
      try {
        await json('/coding/tasks/'+task.id+'/archive',{expected_task_revision:task.revision});
        tasks=tasks.filter(t=>t.id!==task.id); $('task').selectedOptions[0].remove(); selectTask('');
        status('Task archived. Conversation history is retained.');
      } catch(error) {status(error.message);}
    });
    $('preview').addEventListener('click',async()=>{
      try {
        preview=await json('/coding/sources/preview',{topic:$('topic').value,message:question.value});
        $('source-list').textContent = (preview.sources.length ? preview.sources.map(s=>s.id+' · version '+s.hash.slice(0,12)).join('\n') : 'No matching project source. ' + (preview.source_policy==='source_only' ? 'Source Only needs evidence. Create a Source First conversation for general practice.' : 'General Python practice will be labelled as such.')) + '\nYour existing Tutor AI provider receives the reviewed fields, approved source excerpts and bounded task history. ANVAYA never reads Colab.';
        $('consent').disabled=false;
        preview.topic=$('topic').value; preview.message=question.value;
      } catch(error) {status(error.message);}
    });
    $('consent').addEventListener('click',async()=>{
      if(!preview) return;
      try {
        const state=await json('/coding/consent',{expected_consent_revision:consentRevision,review_token:preview.review_token,topic:preview.topic,message:preview.message});
        consentRevision=state.consent_revision; $('consent').disabled=true; pending=null; $('solution').checked=false;
        status('Scope approved. Review your fields, close tools and press Send when ready.');
      } catch(error) {status(error.message);}
    });
    $('download').addEventListener('click',async()=>{
      if(!task || busy) return;
      try {
        const response=await post('/coding/tasks/'+task.id+'/notebook',{expected_task_revision:task.revision,template_id:task.template_id || '',include_student_code:$('include-code').checked});
        const blob=await response.blob(); const url=URL.createObjectURL(blob);
        const link=document.createElement('a'); link.href=url; link.download='anvaya-practice-'+task.id.slice(0,8)+'.ipynb'; document.body.append(link); link.click(); link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
        status('Notebook downloaded. In Colab choose File → Upload notebook, then run cells manually.');
      } catch(error) {status(error.message);}
    });
    function installCopy() {
      document.querySelectorAll('.tutor-transcript pre').forEach(pre=>{
        if(pre.querySelector('button')) return;
        const code=pre.querySelector('code'); if(!code) return;
        const button=document.createElement('button'); button.type='button'; button.className='coding-copy'; button.textContent='Copy code';
        button.addEventListener('click',async()=>{button.textContent=await copyExact(code,navigator.clipboard) ? 'Copied' : 'Select code and copy manually';});
        pre.append(button);
      });
    }
    installCopy();
    function showCards() {
      const query=$('card-search').value.toLowerCase(); const target=$('cards'); target.replaceChildren();
      cards.filter(card=>JSON.stringify(card).toLowerCase().includes(query)).slice(0,12).forEach(card=>{
        const article=document.createElement('article'); const title=document.createElement('strong'); title.textContent=card.id+' · '+card.what; article.append(title);
        Object.entries(card).filter(([key])=>!['id','what','category'].includes(key)).forEach(([key,value])=>{
          const p=document.createElement(key==='syntax'||key==='example' ? 'pre':'p'); p.textContent=key.replaceAll('_',' ')+': '+(typeof value==='string'?value:JSON.stringify(value));article.append(p);
        }); target.append(article);
      });
    }
    $('card-search').addEventListener('input',showCards); showCards();
    $('stop').addEventListener('click',()=>{
      generation++; waiting?.abort(); busy=false; $('stop').hidden=true;
      form.removeAttribute('aria-busy');
      status('Stopped waiting in this tab. The server may still finish. Reopen the conversation before another send to reconcile its receipt. Your draft is retained.');
    });
    form.addEventListener('submit',async event=>{
      if(form.dataset.workspace!=='coding') return;
      event.preventDefault();
      if(busy) return;
      if(!task) {tools(true);status('Enter a title and save a task locally first.');return;}
      if(!consentRevision) {tools(true);$('source-review').open=true;status('Review sources and approve the provider scope before sending.');return;}
      const data={expected_task_revision:task.revision,action:$('action').value,topic:$('topic').value,message:question.value,
        code:$('code').value,error:$('error').value,attempt:$('attempt').value,hint_level:Number($('hint').value),explanation_depth:$('depth').value,
        full_solution:$('solution').checked,source_consent_revision:consentRevision};
      const fingerprint=JSON.stringify(data);
      if(!pending || pending.fingerprint!==fingerprint) pending={fingerprint,id:requestId()};
      const token=++generation; const activeTask=task.id;
      busy=true; waiting=new AbortController(); form.setAttribute('aria-busy','true'); $('stop').hidden=false;
      status('Sending reviewed context. Waiting for AI feedback…');tools(false);
      const timeout=setTimeout(()=>waiting?.abort(),55000);
      try {
        await json('/coding/tasks/'+activeTask+'/ask',{...data,request_id:pending.id},waiting.signal);
        if(token!==generation) return;
        const response=await fetch(base,{cache:'no-store'}); if(!response.ok) throw new Error('Reply saved. Reopen the conversation to read it.');
        const documentCopy=new DOMParser().parseFromString(await response.text(),'text/html');
        const transcript=documentCopy.querySelector('.tutor-transcript');
        document.querySelector('.tutor-transcript').replaceWith(transcript);
        question.value='';question.dispatchEvent(new Event('input'));dirty=false;pending=null;$('solution').checked=false;
        installCopy(); document.getElementById('tutor-latest-turn')?.scrollIntoView({block:'end'});
        status('AI feedback saved · code not executed. Paste reviewed Colab output here for your next step.');
      } catch(error) {
        if(token!==generation) return;
        status(error.name==='AbortError' ? 'Wait ended. The server may finish; reopen this conversation to reconcile. Your draft is retained.' : error.message);
      } finally {
        clearTimeout(timeout);
        if(token===generation){busy=false;$('stop').hidden=true;form.removeAttribute('aria-busy');}
      }
    });
    // Academic native form navigation is an explicit action; let it proceed.
    form.addEventListener('submit',()=>{if(form.dataset.workspace!=='coding') suppressLeave=true;});
    if(tasks.length) selectTask(tasks.some(t=>t.id===studio.dataset.selectedTask) ? studio.dataset.selectedTask : tasks[tasks.length-1].id);
    controls();
  }
  const api={solutionAllowed,copyExact};
  if(typeof module!=='undefined') module.exports=api;
  if(typeof document!=='undefined') {
    if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true}); else install();
  }
})(typeof globalThis!=='undefined'?globalThis:this);
