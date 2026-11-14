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
    installPanels();
    installCodeCopy();
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
      const native = toggle.closest('li')?.querySelector('.tutor-native-rename');
      if (native) { native.open = true; native.classList.add('tutor-rename-enhanced'); }
      setRenameOpen(toggle, false);
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
      if (form.dataset.workspace === 'coding') {
        if (form.dataset.codingReady !== 'true') event.preventDefault();
        return;
      }
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
  function installCodeCopy() {
    document.querySelectorAll('.tutor-transcript pre').forEach(pre => {
      if (pre.querySelector('button')) return;
      const code = pre.querySelector('code');
      if (!code) return;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'coding-copy'; button.textContent = 'Copy code';
      button.addEventListener('click', async () => {
        try {
          if (!navigator.clipboard) throw new Error('Clipboard unavailable');
          await navigator.clipboard.writeText(code.textContent);
          button.textContent = 'Copied';
        } catch (_) { button.textContent = 'Select code and copy manually'; }
      });
      pre.append(button);
    });
  }
  function installPanels() {
    const panels = new Map();
    let opener = null;
    ['sessions', 'evidence'].forEach(name => {
      const panel = document.getElementById('tutor-' + name + '-panel');
      if (!panel || typeof HTMLDialogElement === 'undefined' || !HTMLDialogElement.prototype.showModal) return;
      const fallback = panel.parentElement;
      const dialog = document.createElement('dialog');
      dialog.className = 'tutor-modal'; dialog.setAttribute('aria-labelledby', 'tutor-' + name + '-title');
      dialog.append(panel); document.body.append(dialog); fallback.hidden = true;
      panels.set(panel.id, dialog);
      panel.querySelector('[data-tutor-close]').addEventListener('click', () => dialog.close());
      dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
      dialog.addEventListener('close', () => {
        document.body.classList.remove('tutor-modal-open');
        if (opener?.isConnected) opener.focus();
      });
      // Explicit containment also handles browsers whose native tab loop visits chrome.
      dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const nodes = [...dialog.querySelectorAll('a[href],button,input,select,textarea,summary')].filter(node => !node.disabled && node.getClientRects().length);
        if (!nodes.length) return;
        if (event.shiftKey && document.activeElement === nodes[0]) {event.preventDefault(); nodes.at(-1).focus();}
        else if (!event.shiftKey && document.activeElement === nodes.at(-1)) {event.preventDefault(); nodes[0].focus();}
      });
    });
    function open(id, trigger) {
      const dialog = panels.get(id); if (!dialog) return;
      panels.forEach(other => { if (other !== dialog && other.open) other.close(); });
      // Do not stack a global mobile navigation drawer behind another modal.
      if (document.body.classList.contains('nav-open')) document.getElementById('nav-toggle')?.click();
      opener = trigger;
      if (!dialog.open) dialog.showModal();
      document.body.classList.add('tutor-modal-open');
      (dialog.querySelector('input[type="search"]') || dialog.querySelector('button'))?.focus();
    }
    document.addEventListener('click', event => {
      const trigger = event.target.closest('[data-tutor-open],[data-tutor-evidence]');
      if (!trigger) return;
      if (trigger.hasAttribute('data-tutor-open')) { open(trigger.dataset.tutorOpen, trigger); return; }
      const templates = [...document.querySelectorAll('.tutor-transcript template[data-evidence-turn]')];
      const selected = trigger.dataset.tutorEvidence === 'latest' ? templates.at(-1) : templates.find(node => node.dataset.evidenceTurn === trigger.dataset.tutorEvidence);
      const content = document.getElementById('tutor-evidence-content');
      if (!content) return;
      content.replaceChildren();
      if (selected) content.append(selected.content.cloneNode(true));
      else content.textContent = 'No answer evidence yet. Ask a question to begin.';
      open('tutor-evidence-panel', trigger);
    });
    document.getElementById('tutor-session-search')?.addEventListener('input', event => {
      const query = event.target.value.trim().toLocaleLowerCase();
      const items = [...document.querySelectorAll('#tutor-sessions-panel [data-history-title]')];
      items.forEach(item => {item.hidden = !item.dataset.historyTitle.toLocaleLowerCase().includes(query);});
      const empty = document.getElementById('tutor-search-empty');
      if (empty) empty.hidden = !items.length || items.some(item => !item.hidden);
    });
    document.addEventListener('tutor:transcript-updated', () => {
      const dialog = panels.get('tutor-evidence-panel'); if (dialog?.open) dialog.close();
      const content = document.getElementById('tutor-evidence-content');
      if (content) content.textContent = 'Conversation updated. Select an answer to inspect its evidence.';
      installCodeCopy();
      // The existing math renderer observes new markup; no provider HTML is injected.
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installTutorFollowups, {once: true});
  } else {
    installTutorFollowups();
  }
})();
