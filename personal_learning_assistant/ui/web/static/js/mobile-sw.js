/* Reviewed app assets only. Never store academic pages, API responses or mutations. */
'use strict';
const CACHE = 'anvaya-mobile-v1-2026-10-22-1';
const ASSETS = ['/mobile/offline', '/static/css/mobile_v1.css', '/static/js/mobile_v1.js',
  '/static/brand/anvaya-mobile-192.png', '/static/brand/anvaya-mobile-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(async cache => {
    // Redirects must not accidentally cache a gateway sign-in page.
    for (const path of ASSETS) {
      const response = await fetch(path, {cache: 'no-store', credentials: 'omit', redirect: 'error'});
      if (!response.ok || new URL(response.url).pathname !== path) throw new Error('Shell asset unavailable');
      await cache.put(path, response);
    }
  }));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith('anvaya-mobile-') && key !== CACHE)
    .map(key => caches.delete(key)))));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.method !== 'GET') {
    event.respondWith(fetch(request).catch(() => new Response(
      'Connection unavailable. This change was not saved. Reconnect and check saved state before retrying.',
      {status: 503, headers: {'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store'}})));
    return;
  }
  if (!url.search && ASSETS.includes(url.pathname)) {
    event.respondWith(caches.open(CACHE).then(async cache =>
      (await cache.match(url.pathname)) || fetch(request)));
  } else if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(async () =>
      (await caches.open(CACHE)).match('/mobile/offline')));
  }
  // All other requests use the browser network without runtime caching.
});
