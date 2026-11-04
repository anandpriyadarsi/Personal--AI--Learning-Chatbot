/* ANVAYA Tutor: optional prompt helpers. This script never sends or stores a turn.
 * The student must review the text and explicitly submit the existing form. */
(() => {
  'use strict';
  function installTutorFollowups() {
    // Localized, concise date labels replace raw database timestamps.
    document.querySelectorAll('[data-tutor-time]').forEach(node => {
      const value = new Date(node.getAttribute('datetime') || '');
      if (Number.isNaN(value.getTime())) return;
      const today = new Date();
      const day = new Date(value.getFullYear(), value.getMonth(), value.getDate());
      const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
      const difference = Math.round((startToday - day) / 86400000);
      const clock = new Intl.DateTimeFormat(undefined, {hour: 'numeric', minute: '2-digit'}).format(value);
      if (difference === 0) node.textContent = 'Today · ' + clock;
      else if (difference === 1) node.textContent = 'Yesterday';
      else node.textContent = new Intl.DateTimeFormat(undefined, {
        month: 'short', day: 'numeric', ...(value.getFullYear() !== today.getFullYear() ? {year: 'numeric'} : {})
      }).format(value);
      node.title = value.toLocaleString();
    });
    // Rename is an in-flow editor, never a narrow overlay over other chats.
    const renameToggles = Array.from(document.querySelectorAll('[data-tutor-rename-toggle]'));
    const setRenameOpen = (toggle, open, focus = false) => {
      const editor = document.getElementById(toggle.getAttribute('aria-controls') || '');
      if (!editor) return;
      editor.hidden = !open;
      toggle.setAttribute('aria-expanded', String(open));
      if (focus) (open ? editor.querySelector('input[name="title"]') : toggle)?.focus();
    };
    renameToggles.forEach(toggle => {
      toggle.addEventListener('click', () => {
        const open = toggle.getAttribute('aria-expanded') !== 'true';
        renameToggles.forEach(other => {
          if (other !== toggle) setRenameOpen(other, false);
        });
        setRenameOpen(toggle, open, true);
      });
      const editor = document.getElementById(toggle.getAttribute('aria-controls') || '');
      editor?.querySelector('[data-tutor-rename-cancel]')?.addEventListener('click', () => {
        setRenameOpen(toggle, false, true);
      });
    });
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      const opened = renameToggles.find(toggle => toggle.getAttribute('aria-expanded') === 'true');
      if (opened) {
        event.preventDefault();
        setRenameOpen(opened, false, true);
      }
    });
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
    document.querySelectorAll('[data-tutor-mode]').forEach(button => {
      button.addEventListener('click', () => {
        const mode = document.getElementById('session-mode');
        if (!mode) return;
        mode.value = button.getAttribute('data-tutor-mode');
        mode.focus();
      });
    });
    const composer = document.getElementById('agent-question');
    if (!composer) return;
    const fit = () => {
      composer.style.height = 'auto';
      const limit = (window.visualViewport?.height || window.innerHeight) <= 520 ? 72 : 120;
      composer.style.height = Math.min(composer.scrollHeight, limit) + 'px';
    };
    composer.addEventListener('input', fit);
    fit();
    const panel = document.getElementById('tutor-composer');
    const toolsToggle = document.getElementById('tutor-tools-toggle');
    const tools = document.getElementById('tutor-quick-prompts');
    const setToolsOpen = open => {
      if (!tools || !toolsToggle) return;
      tools.hidden = !open;
      toolsToggle.setAttribute('aria-expanded', String(open));
      document.body.classList.toggle('tutor-tools-open', open);
      updateViewport();
    };
    toolsToggle?.addEventListener('click', () => setToolsOpen(tools.hidden));
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && tools && !tools.hidden) {
        event.preventDefault();
        setToolsOpen(false);
        toolsToggle.focus();
      }
    });
    const composing = () => {
      // Do not move the panel between pointer-down and click on a prompt chip.
      // Once typing starts, retain its position while focus moves to Send.
      if (document.activeElement === composer) document.body.classList.add('tutor-writing');
      else if (!panel?.contains(document.activeElement)) document.body.classList.remove('tutor-writing');
    };
    panel?.addEventListener('focusin', () => { composing(); updateViewport(); });
    panel?.addEventListener('focusout', () => requestAnimationFrame(() => {
      composing(); updateViewport();
    }));
    function updateViewport() {
      const root = document.documentElement;
      if (window.matchMedia('(max-width: 860px)').matches) {
        const visualHeight = window.visualViewport?.height || window.innerHeight;
        root.style.setProperty('--tutor-visual-height', Math.round(visualHeight) + 'px');
      } else {
        root.style.removeProperty('--tutor-visual-height');
      }
    }
    const resize = () => { updateViewport(); fit(); };
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
      if (status) {
        status.textContent = 'Sending your question. Waiting for the tutor response…';
        status.classList.remove('visually-hidden');
      }
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
        setToolsOpen(false);
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
