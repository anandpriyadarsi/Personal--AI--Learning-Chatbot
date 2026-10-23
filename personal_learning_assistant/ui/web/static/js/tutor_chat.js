/* ANVAYA Tutor: optional prompt helpers. This script never sends or stores a turn.
 * The student must review the text and explicitly submit the existing form. */
(() => {
  'use strict';
  function installTutorFollowups() {
    const course = document.getElementById('session-course');
    const topic = document.getElementById('session-topic');
    if (course && topic) {
      const filterTopics = () => {
        for (const option of topic.options) {
          if (!option.value) continue;
          const matches = option.getAttribute('data-course-id') === course.value;
          option.hidden = !matches;
          option.disabled = !matches;
          if (!matches && option.selected) topic.value = '';
        }
        topic.disabled = !course.value;
      };
      course.addEventListener('change', filterTopics);
      filterTopics();
    }
    const topbar = document.querySelector('.topbar');
    const fitHeader = () => {
      if (topbar) document.documentElement.style.setProperty('--tutor-topbar-height', topbar.offsetHeight + 'px');
    };
    fitHeader();
    if (topbar && typeof ResizeObserver === 'function') new ResizeObserver(fitHeader).observe(topbar);
    window.addEventListener('resize', fitHeader);
    document.querySelectorAll('[data-tutor-mode]').forEach(button => {
      button.addEventListener('click', () => {
        const mode = document.getElementById('session-mode');
        if (!mode) return;
        mode.value = button.getAttribute('data-tutor-mode');
        mode.focus();
      });
    });
    document.querySelector('.tutor-context-bar a')?.addEventListener('click', () => {
      const details = document.getElementById('tutor-learning-details');
      if (details) details.open = true;
    });
    const composer = document.getElementById('agent-question');
    if (!composer) return;
    const fit = () => {
      composer.style.height = 'auto';
      const limit = window.innerHeight <= 500 ? 80 : 160;
      composer.style.height = Math.min(composer.scrollHeight, limit) + 'px';
    };
    composer.addEventListener('input', fit);
    fit();
    const panel = document.getElementById('tutor-composer');
    const composing = () => {
      // Do not move the panel between pointer-down and click on a prompt chip.
      // Once typing starts, retain its position while focus moves to Send.
      if (document.activeElement === composer) document.body.classList.add('tutor-writing');
      else if (!panel?.contains(document.activeElement)) document.body.classList.remove('tutor-writing');
    };
    panel?.addEventListener('focusin', composing);
    panel?.addEventListener('focusout', () => requestAnimationFrame(composing));
    const reserveSpace = () => {
      if (panel) document.documentElement.style.setProperty('--tutor-composer-height', panel.offsetHeight + 'px');
    };
    if (panel && typeof ResizeObserver === 'function') new ResizeObserver(reserveSpace).observe(panel);
    const resize = () => {
      const viewport = window.visualViewport;
      const offset = viewport ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0;
      document.documentElement.style.setProperty('--tutor-keyboard-offset', offset + 'px');
      fit(); reserveSpace();
    };
    window.visualViewport?.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('scroll', resize);
    window.addEventListener('resize', resize);
    resize();
    const form = document.getElementById('tutor-ask-form');
    const status = document.getElementById('tutor-submit-status');
    let submitting = false;
    form?.addEventListener('submit', event => {
      if (submitting) { event.preventDefault(); return; }
      submitting = true;
      form.setAttribute('aria-busy', 'true');
      form.querySelector('button[type="submit"]').setAttribute('aria-disabled', 'true');
      if (status) status.textContent = 'Sending your question. Waiting for the tutor response…';
      // Keep native form navigation, CSRF and request-id handling authoritative.
      // No automatic retry and no academic text in browser storage.
    });
    window.addEventListener('pageshow', () => {
      submitting = false;
      form?.removeAttribute('aria-busy');
      const send = form?.querySelector('button[type="submit"]');
      if (send) send.removeAttribute('aria-disabled');
      resize();
    });
    document.querySelector('.error-panel') && composer.focus();
    document.querySelectorAll('[data-tutor-prompt]').forEach(button => {
      button.addEventListener('click', () => {
        const prompt = button.getAttribute('data-tutor-prompt') || '';
        if (!prompt.trim()) return;
        if (composer.value.trim()) {
          const selection = composer.selectionStart ?? composer.value.length;
          const prefix = composer.value.slice(0, selection);
          const suffix = composer.value.slice(selection);
          composer.value = prefix + '\n' + prompt + '\n' + suffix;
        } else {
          composer.value = prompt;
        }
        fit();
        composer.focus();
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installTutorFollowups, {once: true});
  } else {
    installTutorFollowups();
  }
})();
