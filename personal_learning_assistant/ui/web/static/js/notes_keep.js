/* Compact personal Notes controls. Content stays in the existing Notes store. */
(() => {
  'use strict';
  const menus = [...document.querySelectorAll('#notes-create-menu, #notes-reader-menu')];
  document.addEventListener('pointerdown', event => menus.forEach(menu => {
    if (!menu.contains(event.target)) menu.open = false;
  }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') menus.forEach(menu => { if (menu.open) { menu.open = false; menu.querySelector('summary').focus(); } });
  });
  menus.forEach(menu => menu.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { menu.open = false; })));
  const layoutButtons = [...document.querySelectorAll('[data-notes-layout]')];
  const setLayout = value => {
    const layout = value === 'list' ? 'list' : 'grid';
    document.body.dataset.notesLayout = layout;
    layoutButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.notesLayout === layout)));
    try { localStorage.setItem('anvaya.notes.layout', layout); } catch (_) {}
  };
  if (layoutButtons.length) {
    let saved; try { saved = localStorage.getItem('anvaya.notes.layout'); } catch (_) {}
    setLayout(saved);
    layoutButtons.forEach(button => button.addEventListener('click', () => setLayout(button.dataset.notesLayout)));
  }
  const menu = document.getElementById('notes-reader-menu');
  if (!menu) return;
  // Keep existing study tools reachable from the reader's compact action menu.
  // The shared shell positions its launcher during deferred script startup.
  document.addEventListener('DOMContentLoaded', () => {
    const launcher = document.getElementById('notes-study-tools-launcher');
    if (launcher) {
      menu.querySelector('nav').append(launcher);
      launcher.addEventListener('click', () => { menu.open = false; });
    }
  });
  const dialog = document.getElementById('note-action-dialog');
  const form = document.getElementById('note-action-form');
  const field = document.getElementById('note-action-field');
  const input = document.getElementById('note-action-value');
  const error = document.getElementById('note-action-error');
  const save = document.getElementById('note-action-save');
  const status = document.getElementById('note-action-status');
  let currentAction = '', busy = false;
  document.addEventListener('notes-version-changed', event => { menu.dataset.version = event.detail.version; });
  async function change(action, values = {}) {
    if (busy) return;
    const sections=document.getElementById('nested-notes');
    if (sections.dataset.draftDirty==='true' && !confirm('You have unsaved section changes. Discard them and continue with this note action?')) return;
    busy = true; save.disabled = true; error.textContent = ''; status.textContent = '';
    try {
      const response = await fetch(menu.dataset.url, { method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-Notes-CSRF':menu.dataset.csrf}, body:JSON.stringify({action, expected_updated_at:menu.dataset.version, ...values}) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'The note could not be changed. Please retry.');
      // This navigation has an explicit discard decision. Failed requests keep
      // the draft and its navigation guard intact for retrying or saving.
      sections.dataset.draftDirty='false';
      if (action === 'archive' || action === 'delete') location.assign('/notes');
      else location.reload();
    } catch (reason) {
      (dialog.open ? error : status).textContent = reason.message;
    } finally { busy = false; save.disabled = false; }
  }
  function show(action) {
    currentAction = action; error.textContent = '';
    const isRename = action === 'rename', isCourse = action === 'course';
    document.getElementById('note-action-title').textContent = isRename ? 'Rename note' : isCourse ? 'Move to course' : action === 'delete' ? 'Delete note?' : 'Archive note?';
    document.getElementById('note-action-description').textContent = action === 'delete' ? 'Move this note to Trash? Its content and attachments are kept, and you can restore it from Trash.' : action === 'archive' ? 'Move this note out of your main library? You can restore it from Archive.' : isCourse ? 'Enter a course, or leave it blank to remove the course.' : '';
    field.hidden = !(isRename || isCourse); input.required = isRename;
    input.maxLength = isCourse ? 100 : 200;
    input.value = isRename ? menu.dataset.title : isCourse ? menu.dataset.course : '';
    document.getElementById('note-action-label').textContent = isRename ? 'Note name' : 'Course';
    save.textContent = action === 'delete' ? 'Move to Trash' : action === 'archive' ? 'Archive' : 'Save';
    dialog.showModal(); if (!field.hidden) { input.focus(); input.select(); }
  }
  menu.querySelectorAll('[data-note-action]').forEach(button => button.addEventListener('click', () => {
    menu.open = false;
    const action = button.dataset.noteAction;
    if (['rename','course','archive','delete'].includes(action)) return show(action);
    if (action === 'pin' || action === 'restore') return change(action);
    if (action === 'focus') return document.querySelector('[data-workspace-focus]')?.click();
    if (action === 'section' || action === 'sections') return document.dispatchEvent(new Event(action === 'section' ? 'notes-add-section' : 'notes-manage-sections'));
    if (action === 'attachments') {
      const management = document.getElementById('notes-media-management');
      management.open = true;
      management.scrollIntoView({block:'start'});
      document.getElementById('notes-media-files').focus({preventScroll:true});
    }
  }));
  document.getElementById('note-action-cancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) { const bounds = dialog.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close(); } });
  form.addEventListener('submit', event => { event.preventDefault(); change(currentAction, currentAction === 'rename' ? {title:input.value} : currentAction === 'course' ? {course:input.value} : {}); });
})();
