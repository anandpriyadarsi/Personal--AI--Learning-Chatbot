(() => {
  const focusButton = document.getElementById('ls-focus');
  const contentsButton = document.getElementById('ls-contents');
  const dialog = document.getElementById('ls-contents-dialog');
  const status = document.getElementById('ls-control-status');
  if (!focusButton || !dialog) return;
  const column = document.getElementById('ls-reading-column');
  const ids = JSON.parse(document.getElementById('ls-section-ids')?.textContent || '[]');
  // Historical anchors still select the exact lesson/page/question, including old bookmarks.
  function translateAnchor() {
    const anchor = decodeURIComponent(location.hash.slice(1));
    const url = new URL(location.href);
    let changed = false;
    if (ids.includes(anchor) && url.searchParams.get('section') !== anchor && url.searchParams.get('all') !== '1') {
      url.searchParams.set('section', anchor); changed = true;
    }
    if (url.searchParams.get('view') === 'source' && /^source-page-\d+$/.test(anchor) && url.searchParams.get('page') !== anchor.slice(12)) {
      url.searchParams.set('page', anchor.slice(12)); changed = true;
    }
    if (url.searchParams.get('view') === 'practice' && anchor.startsWith('question-') && url.searchParams.get('question') !== anchor.slice(9)) {
      url.searchParams.set('question', anchor.slice(9)); changed = true;
    }
    if (changed) { location.replace(url.href); return true; }
    return false;
  }
  if (translateAnchor()) return;
  window.addEventListener('hashchange', translateAnchor);
  let previous = null;
  const preferenceKey = 'anvaya.learning.focus.v1';
  const sidebar = document.getElementById('app-sidebar');
  const toggle = document.getElementById('nav-toggle');
  function setFocus(enabled) {
    if (enabled && !document.body.classList.contains('ls-focus')) {
      previous = {collapsed: document.body.classList.contains('sidebar-collapsed'), inert: sidebar.inert};
      document.body.classList.remove('nav-open');
      const backdrop = document.getElementById('nav-backdrop');
      if (backdrop) backdrop.hidden = true;
      sidebar.inert = true;
    } else if (!enabled && previous) {
      const desktop = window.innerWidth > 860;
      document.body.classList.toggle('sidebar-collapsed', desktop && previous.collapsed);
      sidebar.inert = desktop ? previous.collapsed : true;
      toggle.setAttribute('aria-expanded', desktop && !previous.collapsed ? 'true' : 'false');
      toggle.setAttribute('aria-label', desktop ? (previous.collapsed ? 'Show navigation' : 'Hide navigation') : 'Open navigation');
      previous = null;
    }
    document.body.classList.toggle('ls-focus', enabled);
    focusButton.setAttribute('aria-pressed', String(enabled));
    focusButton.textContent = enabled ? 'Exit focus' : 'Focus Reading';
    const collapsed = Boolean(previous && previous.collapsed);
    try {
      sessionStorage.setItem(preferenceKey, JSON.stringify({enabled, collapsed}));
    } catch (_error) { /* Reading preference is optional, never learning evidence. */ }
    function decorate(url) {
      if (enabled) { url.searchParams.set('focus', '1'); url.searchParams.set('nav', collapsed ? 'collapsed' : 'expanded'); }
      else { url.searchParams.delete('focus'); url.searchParams.delete('nav'); }
      return url;
    }
    try { history.replaceState(history.state, '', decorate(new URL(location.href))); } catch (_error) { /* URL fallback below still works. */ }
    document.querySelectorAll('.ls-tabs a,.ls-lesson-rail a,.ls-source-chips a,#ls-contents-dialog a,.ls-related-lesson,.ls-practice-link,.ls-lesson-navigation a,.ls-reader-content nav a,#ls-resume,#ls-return-question,.ls-review-answer').forEach(link => {
      const destination = new URL(link.href, location.href);
      // Reading preferences belong only to Learning reader routes. Cross-owner
      // evidence endpoints intentionally reject unrelated query parameters.
      if (destination.origin === location.origin && /^\/learning\/(modules|staged)\//.test(destination.pathname)) {
        link.href = decorate(destination).href;
      }
    });
  }
  let remembered = null;
  try {
    const stored = sessionStorage.getItem(preferenceKey);
    if (stored && stored.length < 150) {
      const value = JSON.parse(stored);
      if (typeof value.enabled === 'boolean' && typeof value.collapsed === 'boolean') remembered = value;
    }
  } catch (_error) { /* Storage denial degrades to bounded URL state. */ }
  const params = new URLSearchParams(location.search);
  if (!remembered && params.get('focus') === '1') remembered = {enabled: true, collapsed: params.get('nav') === 'collapsed'};
  if (remembered) {
    if (remembered.enabled) document.body.classList.toggle('sidebar-collapsed', window.innerWidth > 860 && remembered.collapsed);
    setFocus(remembered.enabled);
  }
  focusButton.addEventListener('click', () => setFocus(!document.body.classList.contains('ls-focus')));
  contentsButton.addEventListener('click', () => dialog.showModal());
  document.getElementById('ls-close-rail')?.addEventListener('click',()=>{toggle.click();toggle.focus();});
  document.addEventListener('keydown',event=>{
    if(event.key!=='Tab'||innerWidth>860||!document.body.classList.contains('nav-open'))return;
    const targets=Array.from(sidebar.querySelectorAll('a[href],button,summary,select,input,textarea')).filter(e=>e.getClientRects().length&&!e.disabled);
    if(!targets.length)return;
    const first=targets[0],last=targets[targets.length-1];
    if(!sidebar.contains(document.activeElement)){event.preventDefault();(event.shiftKey?last:first).focus();}
    else if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  });
  document.getElementById('nav-backdrop')?.addEventListener('click',()=>toggle.focus());
  const closeContents = () => { dialog.close(); contentsButton.focus(); };
  document.getElementById('ls-close-contents').addEventListener('click', closeContents);
  dialog.querySelectorAll('a').forEach(a => a.addEventListener('click', () => dialog.close()));
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (dialog.open) { event.preventDefault(); event.stopImmediatePropagation(); closeContents(); }
    else if (document.body.classList.contains('ls-focus')) {
      event.preventDefault(); event.stopImmediatePropagation(); setFocus(false); focusButton.focus();
    }
  }, true);
  // Android WebView often denies the browser Fullscreen API. In that case the
  // button must still toggle a real full-width, distraction-free reading mode.
  const fullButton = document.getElementById('ls-fullscreen');
  let fallbackFull = false;
  function fullLabel() {
    fullButton.textContent = document.fullscreenElement ? 'Exit fullscreen' : (fallbackFull ? 'Exit full view' : 'Fullscreen');
    fullButton.setAttribute('aria-pressed', String(Boolean(document.fullscreenElement || fallbackFull)));
  }
  fullButton.addEventListener('click', async () => {
    if (fallbackFull) {
      fallbackFull = false;
      setFocus(false);
      fullLabel();
      status.textContent = 'Standard reading view restored.';
      return;
    }
    if (document.fullscreenElement) {
      try { await document.exitFullscreen(); }
      catch (_error) { status.textContent = 'Unable to exit native fullscreen. Use your device Back button.'; }
      return;
    }
    setFocus(true);
    if (typeof document.documentElement.requestFullscreen === 'function') {
      try {
        await document.documentElement.requestFullscreen();
        fullLabel();
        return;
      } catch (_error) { /* WebView or device policy declined native fullscreen. */ }
    }
    fallbackFull = true;
    fullLabel();
    status.textContent = 'Distraction-free full view enabled. Android may keep its system bars visible.';
  });
  document.addEventListener('fullscreenchange', () => {
    fullLabel();
    status.textContent = document.fullscreenElement ?
      'Fullscreen reading enabled.' : 'Native fullscreen ended. Focus reading remains available.';
  });
  fullLabel();
  const copyBrief = document.getElementById('ls-copy-brief');
  if (copyBrief) copyBrief.addEventListener('click', async () => {
    const brief = document.getElementById('ls-review-brief');
    const copyStatus = document.getElementById('ls-copy-status');
    try { await navigator.clipboard.writeText(brief.value); copyStatus.textContent = 'Review brief copied. Paste it explicitly where needed.'; }
    catch (_error) { brief.focus(); brief.select(); copyStatus.textContent = 'Clipboard unavailable. Selected text can be copied manually.'; }
  });
  const readingStatus = document.getElementById('ls-reading-status');
  const textSize = document.getElementById('ls-text-size');
  let savedSize = 18;
  let positionWrite = Promise.resolve(true);
  function savePosition(completed) {
    positionWrite = positionWrite.then(() => persistPosition(completed));
    return positionWrite;
  }
  async function persistPosition(completed) {
    if (!column?.dataset.progress || !['learn','visualise','source','revision','practice'].includes(column.dataset.view)) return true;
    const url = new URL(location.href);
    const payload = {event_id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      section_id: column.dataset.section, view: column.dataset.view, text_size: savedSize};
    if (typeof completed === 'boolean') payload.completed=completed;
    // Source/lesson remediation bookmarks retain the exact pending question.
    const pendingQuestion=url.searchParams.get('question');
    if(pendingQuestion)payload.question_id=pendingQuestion;
    if (column.dataset.view==='source') payload.page=Number(url.searchParams.get('page') || document.querySelector('.ls-source-page')?.id.slice(12));
    if (column.dataset.view==='revision') payload.budget=url.searchParams.get('budget') || 'full';
    const question = document.querySelector('.ls-question');
    if (column.dataset.view === 'practice' && question) { payload.question_id=question.dataset.questionId; payload.practice_mode=url.searchParams.get('mode') || 'mixed'; }
    try {
      const response=await fetch(column.dataset.progress,{method:'POST',headers:{'Content-Type':'application/json','X-Learning-CSRF':column.dataset.csrf},body:JSON.stringify(payload)});
      const result=await response.json();
      readingStatus.textContent=response.ok ? 'Reading position saved · not mastery evidence.' : (result.error || 'Position not saved. Keep this page link.');
      return response.ok;
    } catch (_) { readingStatus.textContent='Position could not be saved. Keep this page link and retry.'; return false; }
  }
  async function initializePosition() {
    if (!column?.dataset.progress) return;
    try {
      const response=await fetch(column.dataset.progress); const state=await response.json();
      if ([18,20,24].includes(state.current?.text_size)) savedSize=state.current.text_size;
    } catch (_) { /* Reading remains useful while storage is unavailable. */ }
    textSize.value=String(savedSize);column.style.fontSize=`${savedSize}px`;
    await savePosition();
  }
  textSize?.addEventListener('change',()=>{savedSize=Number(textSize.value);column.style.fontSize=`${savedSize}px`;savePosition();});
  document.getElementById('ls-complete')?.addEventListener('click',()=>savePosition(true));
  document.getElementById('ls-pause')?.addEventListener('click', async ()=>{
    if (await savePosition()) { const url=new URL(location.href);url.search='';url.hash='';location.assign(url.href); }
  });
  const positionReady = initializePosition();
  let navigationRequest = 0;
  async function finishPositionWrites() {
    await positionReady;
    let retried = false;
    while (true) {
      const pending = positionWrite;
      const saved = await pending;
      // Controls may enqueue another write while this one is in flight.
      if (pending !== positionWrite) continue;
      if (saved) return true;
      // One explicit navigation click retries a transient failed save once.
      // A further failure keeps the current page and its retryable controls.
      if (retried) return false;
      retried = true;
      savePosition();
    }
  }
  // A cross-owner view requires a closed, stable Learning snapshot. Finish the
  // real write before navigation, including slow text-size/bookmark saves.
  document.addEventListener('click', async event => {
    const link = event.target.closest('a[href]');
    if (!column?.dataset.progress || !link || event.defaultPrevented || event.button !== 0 ||
        event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.download) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin || target.pathname === location.pathname) return;
    event.preventDefault();
    const request = ++navigationRequest;
    if (await finishPositionWrites()) {
      if (request === navigationRequest) location.assign(target.href);
    } else {
      readingStatus.textContent = 'Reading position could not be saved. Try the link again to retry; this page keeps your work.';
    }
  });
  document.querySelectorAll('.ls-trusted-activity').forEach(widget=>{
    const details=widget.querySelector('details'); const choice=widget.querySelector('select'); const response=widget.querySelector('textarea');
    details.querySelector('summary').addEventListener('click',event=>{
      if (!details.open && (!choice.value || !response.value.trim())) {
        event.preventDefault(); (!choice.value ? choice : response).focus();
        response.setCustomValidity('Choose a perspective and write your response before revealing.');response.reportValidity();
      } else response.setCustomValidity('');
    });
    response.addEventListener('input',()=>response.setCustomValidity(''));
  });
  document.getElementById('ls-source-zoom')?.addEventListener('change',event=>{
    const image=document.querySelector('.ls-source-page img');if(!image)return;
    const fit=event.target.value==='fit';image.style.maxWidth=fit?'100%':'none';image.style.maxHeight=fit?'75vh':'none';
    image.style.width=fit?'auto':`${image.naturalWidth*Number(event.target.value)/100}px`;
  });
  const engagementUrl=column?.dataset.progress?.replace(/progress$/, 'engagement');
  async function saveEngagement(article,response,action) {
    const result=article.querySelector('.ls-engagement-status,.ls-teachback-status');
    if (!engagementUrl) {if(result)result.textContent='Preview reflection is not saved.';return;}
    const payload={event_id:crypto.randomUUID(),section_id:article.dataset.engagementSection,block_index:Number(article.dataset.engagementIndex),block_scope:article.dataset.engagementScope,response,action};
    try {
      const res=await fetch(engagementUrl,{method:'POST',headers:{'Content-Type':'application/json','X-Learning-CSRF':column.dataset.csrf},body:JSON.stringify(payload)});
      const data=await res.json();result.textContent=res.ok?'Self-report saved for revisiting · not a grade.':data.error;
    } catch (_) {result.textContent='Reflection not saved. Keep your response and retry.';}
  }
  document.querySelectorAll('.ls-save-engagement').forEach(button=>button.addEventListener('click',()=>{
    const article=button.closest('[data-engagement-index]');const widget=article.querySelector('.ls-trusted-activity');
    const choice=widget.querySelector('select');const response=widget.querySelector('textarea');
    if(!choice.value||!response.value.trim()){response.focus();return;}
    saveEngagement(article,JSON.stringify({choice:choice.value,response:response.value}),'reflection');
  }));
  document.querySelectorAll('.ls-save-teachback').forEach(button=>button.addEventListener('click',()=>{
    const article=button.closest('[data-engagement-index]'),input=article.querySelector('.ls-teachback-input');
    if(!input.value.trim()){input.focus();article.querySelector('.ls-teachback-status').textContent='Write your explanation before saving.';return;}
    saveEngagement(article,input.value,'reflection');
  }));
  document.querySelectorAll('.ls-remembered').forEach(button=>button.addEventListener('click',()=>saveEngagement(button.closest('[data-engagement-index]'),button.dataset.response,'remembered')));
  if(engagementUrl) fetch(engagementUrl+'?section='+encodeURIComponent(column.dataset.section)).then(r=>r.json()).then(events=>{
    for(const event of events){const article=document.querySelector(`[data-engagement-index="${event.block_index}"]${event.block_scope==='revision' ? '' : `[data-engagement-section="${event.section_id}"]`}[data-engagement-scope="${event.block_scope || 'section'}"]`);if(!article)continue;
      const status=article.querySelector('.ls-engagement-status,.ls-teachback-status');if(status)status.textContent='Saved self-report: '+(event.action==='remembered'?event.response:'reflection available for revisiting');
      const teachback=article.querySelector('.ls-teachback-input');if(teachback)teachback.value=event.response;
      const widget=article.querySelector('.ls-trusted-activity');if(widget){try{const saved=JSON.parse(event.response);widget.querySelector('select').value=saved.choice;widget.querySelector('textarea').value=saved.response;}catch(_){}}
    }
  }).catch(()=>{});
  const print = document.getElementById('ls-print');
  if (print) print.addEventListener('click', () => window.print());
  document.querySelectorAll('.ls-question').forEach(form => {
    let pending = null;
    const recheck=form.querySelector('.ls-deliberate-recheck');
    recheck?.addEventListener('keydown',event=>{if(event.key===' '){event.preventDefault();recheck.click();}});
    recheck?.addEventListener('click',event=>{
      event.preventDefault();form.querySelectorAll('input[type=radio]').forEach(input=>{input.checked=false;});
      pending=null;form.querySelector('.ls-feedback').textContent='Deliberate recheck: answer again from memory. No attempt is recorded until you submit.';
      recheck.hidden=true;form.querySelector('input[type=radio]')?.focus();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const selected = form.querySelector('input:checked');
      if (!selected) return;
      const selection = Number(selected.value);
      if (!pending || pending.selection !== selection) pending = {
        selection, event_id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`
      };
      const button = form.querySelector('button[type=submit]');
      const feedback = form.querySelector('.ls-feedback');
      button.disabled = true;
      feedback.textContent = 'Checking…';
      try {
        const response = await fetch(form.dataset.endpoint, {
          method: 'POST', headers: {'Content-Type': 'application/json', 'X-Learning-CSRF': form.dataset.csrf},
          body: JSON.stringify({...pending, module_revision: Number(form.dataset.moduleRevision),
            source_sha256: form.dataset.sourceHash, question_id: form.dataset.questionId,
            question_revision: Number(form.dataset.questionRevision)})
        });
        const result = await response.json();
        if (!response.ok) { feedback.textContent = result.error || 'Could not check answer.'; return; }
        feedback.textContent = `${result.correct ? 'Correct' : 'Incorrect'} · attempt ${result.attempt_number}. ${result.explanation}`;
        const progress=document.querySelector('.ls-practice-progress');
        if(progress&&Number.isInteger(result.practised_questions))progress.textContent=`${result.practised_questions} of ${result.total_questions} distinct questions practised in this revision · retries remain recorded attempts.`;
        const recovered=result.practice_state?.status==='recovered_needs_recheck';
        const state=form.querySelector('.ls-question-state');
        if(state&&result.practice_state)state.textContent=`${result.practice_state.status.replaceAll('_',' ')} · ${result.practice_state.attempt_count} recorded attempts. A correct retry is not proof of mastery.`;
        form.querySelector('.ls-next-actions').hidden=result.correct&&!recovered;
        form.querySelector('.ls-review-answer').hidden=result.correct;
        recheck.hidden=!recovered;
        if(recovered)feedback.textContent+=' Correct retry recorded; this item remains available for a deliberate recheck, not marked mastered.';
        if(!result.correct && result.attempt_number>1) feedback.textContent+=' Several attempts are recorded. Try the cited notes before another answer.';
        pending = null;
      } catch (_error) { feedback.textContent = 'Connection interrupted. Retry to submit the same event safely.'; }
      finally { button.disabled = false; }
    });
  });
})();
