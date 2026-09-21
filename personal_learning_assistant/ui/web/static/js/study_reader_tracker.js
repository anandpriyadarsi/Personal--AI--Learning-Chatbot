(function () {
  "use strict";
  const HEARTBEAT_MS = 30000;
  const TICK_MS = 1000;
  const IDLE_MS = 90000;
  const MAX_EVENT_SECONDS = 60;

  function sameOriginUrl(value) {
    try {
      const u = new URL(value || "", window.location.href);
      return u.origin === window.location.origin ? u.pathname + u.search : null;
    } catch (_e) { return null; }
  }

  function progress() {
    const root = document.documentElement;
    const viewport = root.clientHeight || window.innerHeight || 0;
    const height = Math.max(root.scrollHeight || 0, document.body ? document.body.scrollHeight || 0 : 0);
    const max = height - viewport;
    if (max <= 0) return 10000;
    return Math.max(0, Math.min(10000, Math.round(((window.scrollY || root.scrollTop || 0) / max) * 10000)));
  }

  function boot() {
    const data = document.getElementById("study-reader-data");
    if (!data) return;
    const versionHash = data.dataset.versionHash || "";
    const startUrl = sameOriginUrl(data.dataset.startUrl);
    const heartbeatUrl = sameOriginUrl(data.dataset.heartbeatUrl);
    const endUrl = sameOriginUrl(data.dataset.endUrl);
    if (!versionHash || !startUrl || !heartbeatUrl || !endUrl) return;

    let sessionId = "";
    let sequence = 0;
    let pending = 0;
    let maxProgress = progress();
    let lastTick = performance.now();
    let lastActivity = lastTick;
    let stopped = false;
    let outstanding = null;

    function post(url, body, options) {
      return fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        credentials: "same-origin",
        body: JSON.stringify(body),
        ...(options || {})
      });
    }
    function active(now) {
      return document.visibilityState === "visible" && document.hasFocus() && now - lastActivity <= IDLE_MS;
    }
    function activity() {
      lastActivity = performance.now();
      maxProgress = Math.max(maxProgress, progress());
    }
    ["scroll","keydown","pointerdown","touchstart"].forEach(function (name) {
      window.addEventListener(name, activity, {passive: true});
    });
    window.addEventListener("focus", activity);

    function tick() {
      const now = performance.now();
      const elapsed = now - lastTick;
      lastTick = now;
      if (elapsed <= TICK_MS * 2 && active(now)) pending += elapsed / 1000;
      maxProgress = Math.max(maxProgress, progress());
    }

    function payload(delta) {
      return {
        version_hash: versionHash,
        session_id: sessionId,
        sequence: sequence,
        delta_seconds: delta,
        scroll_bps: maxProgress
      };
    }

    async function heartbeat() {
      if (stopped || !sessionId) return;
      let event = outstanding;
      if (!event) {
        const delta = Math.min(MAX_EVENT_SECONDS, Math.floor(pending));
        if (delta < 1) return;
        sequence += 1;
        event = {delta: delta, payload: payload(delta)};
        outstanding = event;
      }
      try {
        const response = await post(heartbeatUrl, event.payload);
        if (!response.ok) return;
        const result = await response.json();
        if (result && result.ok === true) {
          pending = Math.max(0, pending - event.delta);
          outstanding = null;
        }
      } catch (_e) {}
    }

    function finish() {
      if (stopped || !sessionId) return;
      stopped = true;
      const delta = Math.min(MAX_EVENT_SECONDS, Math.floor(pending));
      let p;
      if (outstanding) {
        p = payload(delta);
        p.sequence = outstanding.payload.sequence;
        p.replayed_delta_seconds = Math.min(outstanding.delta, delta);
      } else {
        sequence += 1;
        p = payload(delta);
        p.replayed_delta_seconds = 0;
      }
      const body = JSON.stringify(p);
      if (navigator.sendBeacon) {
        const blob = new Blob([body], {type:"application/json"});
        if (navigator.sendBeacon(endUrl, blob)) return;
      }
      post(endUrl, p, {keepalive:true}).catch(function(){});
    }

    post(startUrl, {version_hash: versionHash}).then(function (r) {
      if (!r.ok) throw new Error("start failed");
      return r.json();
    }).then(function (result) {
      if (!result || result.ok !== true || !result.session_id) throw new Error("bad start");
      sessionId = result.session_id;
      lastTick = performance.now();
      lastActivity = lastTick;
      window.setInterval(tick, TICK_MS);
      window.setInterval(heartbeat, HEARTBEAT_MS);
      document.addEventListener("visibilitychange", function () {
        if (document.visibilityState !== "visible") finish();
      });
      window.addEventListener("pagehide", finish, {once:true});
    }).catch(function(){ stopped = true; });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, {once:true});
  } else { boot(); }
})();
