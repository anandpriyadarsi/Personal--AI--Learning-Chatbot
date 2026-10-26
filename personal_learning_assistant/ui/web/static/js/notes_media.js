(() => {
  'use strict';
  const root = document.getElementById('notes-media');
  if (!root) return;
  const list = root.querySelector('#notes-media-list');
  const status = root.querySelector('#notes-media-status');
  const form = root.querySelector('#notes-media-upload');
  const picker = root.querySelector('#notes-media-files');
  const submit = form.querySelector('button');
  let busy = false;
  const message = (text) => { status.textContent = text; };
  const size = (bytes) => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const request = async (url, options = {}) => {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options});
    let body;
    try { body = await response.json(); } catch (_) { throw new Error('The attachment request failed. Refresh the note and try again.'); }
    if (!response.ok) throw new Error(body.error || 'The attachment request failed.');
    return body;
  };
  const mutate = async (url, options, success) => {
    if (busy) return;
    busy = true; submit.disabled = true;
    root.setAttribute('aria-busy', 'true');
    message('Saving attachments…');
    try {
      await request(url, {method: 'POST', ...options, headers: {'X-Notes-CSRF': root.dataset.csrf, ...options.headers}});
      await load();
      document.dispatchEvent(new Event('notes-media-changed'));
      message(success);
      return true;
    } catch (error) { message(error.message || 'Media could not be saved. Try again.'); return false; }
    finally { busy = false; submit.disabled = false; root.setAttribute('aria-busy', 'false'); }
  };
  const render = (items) => {
    list.replaceChildren();
    items.forEach((item) => {
      const row = element('li', '', 'notes-media-row');
      const content = element('div', '', 'notes-media-info');
      const icon = element('span', item.mimetype.startsWith('audio/') ? '🎧' : item.mimetype.startsWith('video/') ? '🎬' : '📎');
      icon.setAttribute('aria-hidden', 'true');
      const link = element('a', item.filename, 'notes-media-open');
      // Ordinary same-origin links form the Android navigation bridge. Browsers
      // receive Content-Disposition: attachment, never an embedded media player.
      link.href = item.open_url;
      const heading = element('div', '', 'notes-media-name'); heading.append(icon, link);
      const format = item.filename.split('.').pop().toUpperCase();
      content.append(heading, element('small', `${format} · ${size(item.size)} · Open in device app`));
      const menu = element('details', '', 'notes-media-menu');
      const summary = element('summary', 'Attachment options');
      const actions = element('div', '', 'notes-media-actions');
      const rename = element('form');
      const label = element('label', 'Attachment name');
      const input = element('input'); input.value = item.filename; input.maxLength = 200; input.required = true;
      label.append(input);
      const save = element('button', 'Rename'); save.type = 'submit';
      rename.append(label, save);
      rename.addEventListener('submit', (event) => {
        event.preventDefault();
        mutate(`${root.dataset.url}/${item.id}/rename`, {headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filename: input.value})}, 'Attachment renamed.');
      });
      const share = element('a', 'Share / Export'); share.href = item.share_url;
      const download = element('a', 'Download'); download.href = item.url;
      const remove = element('button', 'Delete attachment'); remove.type = 'button';
      remove.addEventListener('click', () => {
        if (!busy && window.confirm(`Remove “${item.filename}” from this note?`)) {
          mutate(`${root.dataset.url}/${item.id}/delete`, {}, 'Attachment removed. Your note content is kept.');
        }
      });
      actions.append(rename, share, download, remove);
      menu.append(summary, actions); row.append(content, menu); list.append(row);
    });
  };
  const load = async () => {
    const result = await request(root.dataset.url);
    render(result.attachments);
    message(result.attachments.length ? 'Tap a file to open it in a device application.' : 'No media attached.');
  };
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy || !picker.files.length) return;
    if (picker.files.length > 20 || Array.from(picker.files).some((file) => file.size > 512 * 1024 * 1024)) {
      message('Choose up to 20 files, each 512 MB or smaller.'); return;
    }
    const saved = await mutate(root.dataset.url, {body: new FormData(form)}, 'Media attached. Tap a file to open it.');
    if (saved) picker.value = '';
  });
  // Metadata only, once the handwritten reader loads. No media bytes, duration,
  // thumbnails or video processing during page navigation.
  load().catch(() => message('Attachments could not be loaded. Refresh the note to try again.'));
})();
