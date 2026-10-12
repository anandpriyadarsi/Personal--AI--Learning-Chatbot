(() => {
  const focusButton = document.getElementById('ls-focus');
  const contentsButton = document.getElementById('ls-contents');
  const dialog = document.getElementById('ls-contents-dialog');
  const status = document.getElementById('ls-control-status');
  if (!focusButton || !dialog) return;
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
    document.querySelectorAll('.ls-tabs a,.ls-source-chips a,#ls-contents-dialog a,.ls-related-lesson,.ls-practice-link').forEach(link => {
      link.href = decorate(new URL(link.href, location.href)).href;
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
  document.getElementById('ls-fullscreen').addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else { setFocus(true); await document.documentElement.requestFullscreen(); }
    } catch (_error) { status.textContent = 'Fullscreen unavailable; Focus Reading still works.'; }
  });
  const copyBrief = document.getElementById('ls-copy-brief');
  if (copyBrief) copyBrief.addEventListener('click', async () => {
    const brief = document.getElementById('ls-review-brief');
    const copyStatus = document.getElementById('ls-copy-status');
    try { await navigator.clipboard.writeText(brief.value); copyStatus.textContent = 'Review brief copied. Paste it explicitly where needed.'; }
    catch (_error) { brief.focus(); brief.select(); copyStatus.textContent = 'Clipboard unavailable. Selected text can be copied manually.'; }
  });
  const print = document.getElementById('ls-print');
  if (print) print.addEventListener('click', () => window.print());
  document.querySelectorAll('.ls-question').forEach(form => {
    let pending = null;
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
        pending = null;
      } catch (_error) { feedback.textContent = 'Connection interrupted. Retry to submit the same event safely.'; }
      finally { button.disabled = false; }
    });
  });
})();
