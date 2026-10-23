/* The server owns state. A failed request preserves visible work and never says Paused. */
(function () {
  'use strict';
  const root = document.getElementById('workspace');
  if (!root) return;
  if (window.matchMedia('(max-width: 768px)').matches) document.querySelector('.palette-disclosure')?.removeAttribute('open');
  const status = document.getElementById('save-status');
  const started = performance.now();
  const remaining = Number(root.dataset.remaining);
  function remainingMillis(now) { return Math.max(0, remaining - (root.dataset.status === 'active' ? now - started : 0)); }
  function tick() {
    const seconds = Math.ceil(remainingMillis(performance.now()) / 1000);
    document.getElementById('timer').textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0');
  }
  tick(); setInterval(tick, 250);
  let pending = false;
  document.querySelectorAll('form:not(#coding-helper-form)').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    if (pending) return;
    const body = new FormData(form);
    if (event.submitter && event.submitter.name) body.set(event.submitter.name, event.submitter.value);
    const action = body.get('command') || form.action.split('/').pop();
    if (['submit', 'finish_solving', 'self_submit'].includes(action) && !window.confirm(action === 'self_submit' ? 'Submit these self-entered marks?' : 'Finish solving and freeze this attempt?')) return;
    pending = true;
    const buttons = Array.from(document.querySelectorAll('button'));
    const disabledBefore = buttons.map(button => button.disabled);
    buttons.forEach(button => { button.disabled = true; });
    status.textContent = 'Waiting for server acknowledgement…';
    try {
      const response = await fetch(form.action, { method: 'POST', body, headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'Request was not acknowledged.');
      if (result.state.revision < Number(root.dataset.revision)) throw new Error('Older acknowledgement received. Reload state before continuing.');
      // Reopen from persisted state, including the same attempt ID and native forms.
      window.location.reload();
    } catch (error) {
      status.textContent = 'No successful acknowledgement. Your visible work is preserved. ' + error.message + ' Retry the same action; do not assume the timer paused.';
      buttons.forEach((button, index) => { button.disabled = disabledBefore[index]; });
      pending = false;
    }
  }));
  // Selecting a question from the palette submits the *current* answer
  // before changing ordinal. Do not navigate to a question that was never
  // rendered or bypass the atomic save/acknowledgement.
  document.querySelectorAll('[data-palette-go]').forEach(link => link.addEventListener('click', event => {
    if (pending || root.dataset.status !== 'active') {
      event.preventDefault();
      return;
    }
    const form = document.querySelector('form.answer-form');
    const ordinal = form && form.querySelector('select[name="ordinal"]');
    const navigate = form && form.querySelector('button[name="command"][value="navigate"]');
    if (!ordinal || !navigate) return;
    if (!Array.from(ordinal.options).some(option => option.value === link.dataset.paletteGo)) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    ordinal.value = link.dataset.paletteGo;
    form.requestSubmit(navigate);
  }));
  if (root.dataset.status === 'paused') document.getElementById('state-banner').focus();
  else if (root.dataset.status === 'active') document.querySelector('.question').focus({ preventScroll: true });
})();
