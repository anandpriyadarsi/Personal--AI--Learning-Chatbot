(function () {
  "use strict";

  const HEARTBEAT_MS = 30000;
  const TICK_MS = 1000;
  const IDLE_MS = 90000;
  const MAX_EVENT_SECONDS = 60;
  const ACTIVITY_THROTTLE_MS = 250;
  const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  function boot() {
    const data = document.getElementById("obsidian-reader-data");
    if (!data) {
      return;
    }

    const path = data.dataset.path || "";
    const sourceHash = data.dataset.sourceHash || "";
    const startUrl = sameOriginUrl(data.dataset.startUrl);
    const heartbeatUrl = sameOriginUrl(data.dataset.heartbeatUrl);
    const endUrl = sameOriginUrl(data.dataset.endUrl);
    if (!path || !sourceHash || !startUrl || !heartbeatUrl || !endUrl) {
      return;
    }

    let sessionId = null;
    let sequence = 0;
    let pendingSeconds = 0;
    let maxScrollBps = scrollProgressBps();
    let lastActivityMs = performance.now();
    let lastActivitySignalMs = 0;
    let lastTickMs = lastActivityMs;
    let tickTimer = null;
    let heartbeatTimer = null;
    let stopped = false;
    let ending = false;
    let retryHeartbeat = null;
    let sendChain = Promise.resolve();

    function sameOriginJson(url, payload, extraOptions) {
      return fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        credentials: "same-origin",
        body: JSON.stringify(payload),
        ...(extraOptions || {}),
      });
    }

    function isActive(now) {
      return (
        document.visibilityState === "visible" &&
        document.hasFocus() &&
        now - lastActivityMs <= IDLE_MS
      );
    }

    function recordActivity() {
      if (stopped || ending) {
        return;
      }
      const now = performance.now();
      if (now - lastActivitySignalMs >= ACTIVITY_THROTTLE_MS) {
        lastActivityMs = now;
        lastActivitySignalMs = now;
      }
      maxScrollBps = Math.max(maxScrollBps, scrollProgressBps());
    }

    function resetTimeOrigin(markActive) {
      const now = performance.now();
      lastTickMs = now;
      if (markActive) {
        lastActivityMs = now;
        lastActivitySignalMs = now;
      }
      maxScrollBps = Math.max(maxScrollBps, scrollProgressBps());
    }

    function accrueActiveTime() {
      const now = performance.now();
      const elapsedMs = Math.max(0, now - lastTickMs);
      lastTickMs = now;
      // A large timer gap means the browser or machine was suspended. Do not
      // reinterpret that gap as active study time.
      if (elapsedMs <= TICK_MS * 2 && isActive(now)) {
        pendingSeconds += elapsedMs / 1000;
      }
      maxScrollBps = Math.max(maxScrollBps, scrollProgressBps());
    }

    function eventPayload(deltaSeconds) {
      return {
        path: path,
        source_hash: sourceHash,
        session_id: sessionId,
        sequence: sequence,
        delta_seconds: deltaSeconds,
        scroll_bps: maxScrollBps,
      };
    }

    function stopAutomaticTracking() {
      stopped = true;
      if (tickTimer !== null) {
        window.clearInterval(tickTimer);
      }
      if (heartbeatTimer !== null) {
        window.clearInterval(heartbeatTimer);
      }
    }

    async function performHeartbeat() {
      if (stopped || ending || !sessionId) {
        return;
      }

      let outbound = retryHeartbeat;
      if (!outbound) {
        const delta = Math.min(MAX_EVENT_SECONDS, Math.floor(pendingSeconds));
        if (delta < 1) {
          return;
        }
        sequence += 1;
        outbound = {delta: delta, payload: eventPayload(delta)};
        retryHeartbeat = outbound;
      }

      try {
        const response = await sameOriginJson(heartbeatUrl, outbound.payload);
        if (!response.ok) {
          stopAutomaticTracking();
          return;
        }
        const result = await response.json();
        if (!result || result.ok !== true) {
          stopAutomaticTracking();
          return;
        }
        pendingSeconds = Math.max(0, pendingSeconds - outbound.delta);
        retryHeartbeat = null;
      } catch (_error) {
        // Retain the exact sequence and delta for a safe replay on the next
        // heartbeat. The server treats a repeated sequence as idempotent.
      }
    }

    function queueHeartbeat() {
      if (stopped || ending) {
        return;
      }
      sendChain = sendChain.then(performHeartbeat);
    }

    function finalTransport(payload) {
      const body = JSON.stringify(payload);
      if (typeof navigator.sendBeacon === "function") {
        const blob = new Blob([body], {type: "application/json"});
        if (navigator.sendBeacon(endUrl, blob)) {
          return Promise.resolve();
        }
      }
      return sameOriginJson(endUrl, payload, {keepalive: true}).then(function () {
        return undefined;
      }).catch(function () {
        return undefined;
      });
    }

    function finishReading() {
      if (stopped || ending || !sessionId) {
        return;
      }
      ending = true;
      if (tickTimer !== null) {
        window.clearInterval(tickTimer);
      }
      if (heartbeatTimer !== null) {
        window.clearInterval(heartbeatTimer);
      }
      maxScrollBps = Math.max(maxScrollBps, scrollProgressBps());
      let payload;
      if (retryHeartbeat) {
        // Reuse the outstanding sequence, but include all time accumulated
        // since its payload was created. The replay marker lets the server
        // add either the full total or only the post-heartbeat remainder,
        // depending on which request wins the unload race.
        const delta = Math.min(
          MAX_EVENT_SECONDS,
          Math.floor(pendingSeconds)
        );
        payload = eventPayload(delta);
        payload.sequence = retryHeartbeat.payload.sequence;
        payload.replayed_delta_seconds = Math.min(
          retryHeartbeat.delta,
          delta
        );
      } else {
        const delta = Math.min(
          MAX_EVENT_SECONDS,
          Math.floor(pendingSeconds)
        );
        sequence += 1;
        payload = eventPayload(delta);
        payload.replayed_delta_seconds = 0;
      }
      // Unload-safe transport must be invoked during the pagehide/visibility
      // handler, not deferred behind an unresolved fetch promise.
      finalTransport(payload);
    }

    function onVisibilityChange() {
      const visible = document.visibilityState === "visible";
      resetTimeOrigin(visible);
      if (!visible) {
        finishReading();
      }
    }

    function beginTracking(id) {
      sessionId = id;
      resetTimeOrigin(true);
      window.addEventListener("scroll", recordActivity, {passive: true});
      window.addEventListener("keydown", recordActivity);
      window.addEventListener("pointerdown", recordActivity, {passive: true});
      window.addEventListener("touchstart", recordActivity, {passive: true});
      window.addEventListener("focus", function () {
        resetTimeOrigin(true);
      });
      document.addEventListener("visibilitychange", onVisibilityChange);
      window.addEventListener("pagehide", finishReading, {once: true});
      tickTimer = window.setInterval(accrueActiveTime, TICK_MS);
      heartbeatTimer = window.setInterval(queueHeartbeat, HEARTBEAT_MS);
    }

    sameOriginJson(startUrl, {path: path, source_hash: sourceHash})
      .then(function (response) {
        if (!response.ok) {
          throw new Error("reading start rejected");
        }
        return response.json();
      })
      .then(function (result) {
        if (!result || result.ok !== true || !SESSION_ID_PATTERN.test(result.session_id || "")) {
          throw new Error("invalid reading session");
        }
        beginTracking(result.session_id);
      })
      .catch(function () {
        stopAutomaticTracking();
      });
  }

  function sameOriginUrl(value) {
    try {
      const resolved = new URL(value || "", window.location.href);
      if (resolved.origin !== window.location.origin) {
        return null;
      }
      return resolved.pathname + resolved.search;
    } catch (_error) {
      return null;
    }
  }

  function scrollProgressBps() {
    const root = document.documentElement;
    const body = document.body;
    const viewport = root.clientHeight || window.innerHeight || 0;
    const height = Math.max(
      root.scrollHeight || 0,
      body ? body.scrollHeight || 0 : 0
    );
    const scrollable = height - viewport;
    if (scrollable <= 0) {
      return 10000;
    }
    const offset = window.scrollY || root.scrollTop || 0;
    const ratio = Math.round((offset / scrollable) * 10000);
    return Math.min(10000, Math.max(0, ratio));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, {once: true});
  } else {
    boot();
  }
})();
