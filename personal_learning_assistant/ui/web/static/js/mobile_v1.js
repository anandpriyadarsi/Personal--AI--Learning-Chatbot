/* Presentation and connectivity only. No academic data is persisted here. */
(() => {
  'use strict';
  const root = document.documentElement;
  const nativeRuntime = root.dataset.nativeRuntime === 'true';
  const choice = document.getElementById('mobile-theme');
  const system = window.matchMedia('(prefers-color-scheme: light)');
  let theme = 'dark';
  try { theme = localStorage.getItem('anvaya.mobile.theme') || 'dark'; } catch (_) { /* optional */ }
  if (!['dark', 'light', 'system'].includes(theme)) theme = 'dark';
  const applyTheme = () => {
    const resolved = theme === 'system' ? (system.matches ? 'light' : 'dark') : theme;
    root.dataset.theme = resolved;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'light' ? '#f4f7f8' : '#0b0f14');
  };
  applyTheme();
  const composing = () => {
    const field = document.activeElement;
    document.body.classList.toggle('mobile-composing', !!field?.matches('textarea,input:not([type=radio]):not([type=checkbox]):not([type=button]):not([type=submit])'));
  };
  document.addEventListener('focusin', composing);
  document.addEventListener('focusout', () => requestAnimationFrame(composing));
  if (choice) {
    choice.value = theme;
    choice.addEventListener('change', () => {
      theme = choice.value; applyTheme();
      try { localStorage.setItem('anvaya.mobile.theme', theme); } catch (_) { /* optional */ }
    });
  }
  system.addEventListener('change', applyTheme);
  const banner = document.getElementById('mobile-connection');
  const message = document.getElementById('mobile-connection-text');
  let checking = false;
  const check = async () => {
    if (!banner || checking) return;
    checking = true;
    // AbortSignal.timeout is absent in older supported Android WebViews.
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timeout = controller ? setTimeout(() => controller.abort(), 5000) : null;
    try {
      const response = await fetch('/healthz', {cache: 'no-store', credentials: 'same-origin',
        redirect: 'error', ...(controller ? {signal: controller.signal} : {})});
      const body = await response.json();
      if (!response.ok || body.status !== 'ok') throw new Error('Host unavailable');
      banner.hidden = true;
    } catch (_) {
      banner.hidden = false;
      message.textContent = 'Host unavailable. New changes may not save. Assessment time follows server rules.';
    } finally { if (timeout !== null) clearTimeout(timeout); checking = false; }
  };
  document.getElementById('mobile-reconnect')?.addEventListener('click', check);
  window.addEventListener('offline', () => {
    if (nativeRuntime) { check(); return; }
    if (!banner) return;
    banner.hidden = false;
    message.textContent = 'You appear offline. Check saved state after reconnecting; changes are never queued.';
  });
  window.addEventListener('online', check);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
  check();

  let installPrompt;
  const install = document.getElementById('mobile-install');
  const installStatus = document.getElementById('mobile-install-status');
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); installPrompt = event;
    if (install) install.hidden = false;
  });
  install?.addEventListener('click', async () => {
    if (!installPrompt) return;
    try {
      await installPrompt.prompt();
      const result = await installPrompt.userChoice;
      installStatus.textContent = result.outcome === 'accepted' ? 'Installation requested in your browser.' : 'You can install later from the browser menu.';
    } finally { installPrompt = null; install.hidden = true; }
  });
  if (!nativeRuntime && 'serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/mobile-sw.js', {scope: '/', updateViaCache: 'none'})
      .then(registration => {
        const showWaiting = () => {
          const status = document.getElementById('mobile-update-status');
          if (status && registration.waiting) status.textContent = 'Update ready. Save or pause, then close all ANVAYA windows. No page will reload automatically.';
        };
        showWaiting();
        registration.addEventListener('updatefound', () => registration.installing?.addEventListener('statechange', showWaiting));
      }).catch(() => { if (installStatus) installStatus.textContent = 'Offline shell unavailable. Online academic features can still be used.'; });
  } else if (installStatus && !nativeRuntime) {
    installStatus.textContent = 'Offline installation needs HTTPS or same-device localhost and a supported browser.';
  }
})();
