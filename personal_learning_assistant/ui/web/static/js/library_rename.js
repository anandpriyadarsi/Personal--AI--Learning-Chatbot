(() => {
  const dialog = document.getElementById('library-rename-dialog');
  if (!dialog) return;
  const input = document.getElementById('library-rename-title');
  const error = document.getElementById('library-rename-error');
  const save = document.getElementById('library-rename-save');
  const cancel = document.getElementById('library-rename-cancel');
  let trigger = null;
  let pending = false;
  document.querySelectorAll('[data-library-rename]').forEach(button => {
    button.addEventListener('click', () => {
      trigger = button;
      input.value = Array.from(document.querySelectorAll('[data-library-title]')).find(label => label.dataset.libraryTitle === button.dataset.key)?.textContent || '';
      button.dataset.title = input.value;
      error.textContent = '';
      dialog.showModal();
      input.focus(); input.select();
    });
  });
  cancel.addEventListener('click', () => { if (!pending) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (pending) event.preventDefault(); });
  dialog.addEventListener('close', () => trigger?.focus());
  document.getElementById('library-rename-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (pending || !trigger) return;
    pending = true; save.disabled = true; cancel.disabled = true; input.disabled = true;
    error.textContent = '';
    try {
      const response = await fetch(trigger.dataset.libraryRename, {
        method:'POST', headers:{'Content-Type':'application/json','X-Library-CSRF':dialog.dataset.csrf},
        body:JSON.stringify({title:input.value,expected_title:trigger.dataset.title})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to save this name. Try again.');
      document.querySelectorAll('[data-library-title]').forEach(label => {
        if (label.dataset.libraryTitle === trigger.dataset.key) label.textContent = result.title;
      });
      document.querySelectorAll('[data-library-rename]').forEach(button => {
        if (button.dataset.key === trigger.dataset.key) button.dataset.title = result.title;
      });
      document.getElementById('library-rename-status').textContent = result.duplicate ?
        'Name saved. Another item has this name; both remain separate.' : 'Document name saved.';
      dialog.close();
    } catch (failure) {
      error.textContent = failure.message || 'Unable to save this name. Try again.';
    } finally {
      pending = false; save.disabled = false; cancel.disabled = false; input.disabled = false;
      if (dialog.open) input.focus();
    }
  });
})();
