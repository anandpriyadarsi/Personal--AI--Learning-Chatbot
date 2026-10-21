/* ANVAYA Tutor: optional prompt helpers. This script never sends or stores a turn.
 * The student must review the text and explicitly submit the existing form. */
(() => {
  'use strict';
  function installTutorFollowups() {
    const composer = document.getElementById('agent-question');
    if (!composer) return;
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
