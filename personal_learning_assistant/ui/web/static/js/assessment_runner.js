(() => {
  "use strict";
  const root = document.getElementById("assessment-runner");
  if (!root) return;
  const form = document.getElementById("assessment-response-form");
  const submitForm = document.getElementById("assessment-submit-form");
  const timer = document.getElementById("assessment-timer");
  const saveStatus = document.getElementById("assessment-save-status");
  const palette = document.getElementById("assessment-palette");
  if (palette && window.matchMedia && window.matchMedia("(max-width: 760px)").matches) palette.open = false;
  const palettePanel = document.getElementById("assessment-palette-panel");
  const paletteClose = document.getElementById("assessment-palette-close");
  const paletteOpen = document.getElementById("assessment-palette-open");
  const paletteScroll = document.getElementById("assessment-palette-scroll");
  const retry = document.getElementById("assessment-save-retry");
  const {sessionId, questionId, questionType, heartbeatUrl, autosaveUrl, submitUrl, summaryUrl} = root.dataset;

  const paletteStorageKey = `anvaya:assessment:${sessionId || "session"}:palette-collapsed`;
  let paletteStorage = null;
  try { paletteStorage = window.sessionStorage || null; } catch (_error) { paletteStorage = null; }
  const setPaletteCollapsed = (collapsed, persist = true) => {
    const value = Boolean(collapsed);
    root.classList.toggle("is-palette-collapsed", value);
    if (palettePanel) palettePanel.setAttribute("aria-hidden", value ? "true" : "false");
    if (paletteClose) paletteClose.setAttribute("aria-expanded", value ? "false" : "true");
    if (paletteOpen) {
      paletteOpen.hidden = !value;
      paletteOpen.setAttribute("aria-expanded", value ? "false" : "true");
    }
    if (persist && paletteStorage) {
      try { paletteStorage.setItem(paletteStorageKey, value ? "1" : "0"); } catch (_error) {}
    }
  };
  let initialPaletteCollapsed = false;
  if (paletteStorage) {
    try { initialPaletteCollapsed = paletteStorage.getItem(paletteStorageKey) === "1"; } catch (_error) {}
  }
  setPaletteCollapsed(initialPaletteCollapsed, false);
  if (paletteClose) paletteClose.addEventListener("click", () => setPaletteCollapsed(true));
  if (paletteOpen) paletteOpen.addEventListener("click", () => setPaletteCollapsed(false));
  if (paletteScroll) {
    const current = paletteScroll.querySelector(".palette-item.is-current");
    if (current && typeof current.scrollIntoView === "function") current.scrollIntoView({block: "nearest"});
  }
  let remainingSeconds = Number(root.dataset.remainingSeconds || 0);
  let syncStartedAt = performance.now();
  let focusStartedAt = performance.now();
  let wasVisible = document.visibilityState === "visible";
  let focusMilliseconds = 0;
  let editVersion = 0;
  let savedVersion = 0;
  let saveFlight = null;
  let autosaveTimer = null;
  let actionBusy = false;
  let timeoutChecking = false;
  let allowLeave = false;
  let terminal = false;

  const sampleFocus = () => {
    const now = performance.now();
    if (wasVisible) focusMilliseconds += Math.max(0, now - focusStartedAt);
    focusStartedAt = now;
    wasVisible = document.visibilityState === "visible";
  };
  const collectFocus = () => {
    sampleFocus();
    const seconds = Math.min(60, Math.floor(focusMilliseconds / 1000));
    focusMilliseconds -= seconds * 1000;
    return seconds;
  };
  document.addEventListener("visibilitychange", sampleFocus);

  const navigate = (url) => { allowLeave = true; window.location.assign(url); };
  const checkTerminal = (result) => {
    if (result.status && result.status !== "active") {
      terminal = true;
      navigate(summaryUrl);
    }
    return terminal;
  };
  const setSaveState = (message, pending = false, failed = false) => {
    if (saveStatus) {
      saveStatus.textContent = message;
      saveStatus.classList.toggle("is-pending", pending);
    }
    if (retry) retry.hidden = !failed;
  };
  const cancelDebounce = () => {
    window.clearTimeout(autosaveTimer);
    autosaveTimer = null;
  };
  const responsePayload = () => {
    if (!form) return {};
    if (["mcq", "msq"].includes(questionType)) {
      return {selected_option_ids: Array.from(form.querySelectorAll('input[name="option_ids"]:checked')).map(input => input.value)};
    }
    if (questionType === "true_false") {
      const checked = form.querySelector('input[name="answer_value"]:checked');
      return {value: checked ? checked.value : ""};
    }
    if (questionType === "fill_blank") {
      const parts = Array.from(form.querySelectorAll("[data-fill-part]")).map(input => input.value);
      if (parts.length) return {parts, value: parts.join(",")};
      const input = form.querySelector('[name="answer_value"]');
      return {value: input ? input.value : ""};
    }
    if (questionType === "numerical") {
      const input = form.querySelector('[name="answer_value"]');
      return {value: input ? input.value : ""};
    }
    const input = form.querySelector('[name="answer_text"]');
    return {text: input ? input.value : ""};
  };
  const postJson = async (url, payload, keepalive = false) => {
    const response = await fetch(url, {
      method: "POST", headers: {"Content-Type": "application/json", "Accept": "application/json"},
      body: JSON.stringify(payload), credentials: "same-origin", keepalive
    });
    let result = null;
    try { result = await response.json(); } catch (_error) { result = null; }
    if (!response.ok) {
      const message = result && result.error ? String(result.error) : `Request failed (${response.status || "unknown"})`;
      throw new Error(message);
    }
    if (!result || typeof result !== "object") throw new Error("ANVAYA returned an invalid action response.");
    return result;
  };

  // One writer per page. Changes made during an in-flight save are saved next,
  // before navigation or submission is allowed to continue.
  const flush = () => {
    cancelDebounce();
    if (saveFlight) return saveFlight;
    if (terminal) return Promise.resolve(false);
    saveFlight = (async () => {
      do {
        const version = editVersion;
        setSaveState("Saving…", true);
        const result = await postJson(autosaveUrl, {response: responsePayload(), focus_seconds_delta: collectFocus()});
        if (checkTerminal(result)) return false;
        savedVersion = version;
      } while (savedVersion < editVersion);
      setSaveState("Saved to ANVAYA");
      return true;
    })().catch(error => {
      setSaveState("Changes not saved. Keep this page open and retry.", false, true);
      throw error;
    }).finally(() => { saveFlight = null; });
    return saveFlight;
  };
  const queueAutosave = () => {
    editVersion += 1;
    setSaveState("Unsaved changes", true);
    cancelDebounce();
    autosaveTimer = window.setTimeout(() => { flush().catch(() => {}); }, 900);
  };
  if (form) form.querySelectorAll("input, textarea").forEach(input => {
    if (input.type !== "hidden") input.addEventListener(input.tagName === "TEXTAREA" || input.type === "text" ? "input" : "change", queueAutosave);
  });
  if (retry) retry.addEventListener("click", () => flush().catch(() => {}));

  const countsFrom = (counts) => ({
    answered: counts.answered + counts.answered_marked_for_review,
    unanswered: counts.not_answered + counts.not_visited + counts.marked_for_review,
    marked: counts.marked_for_review + counts.answered_marked_for_review,
    not_visited: counts.not_visited
  });
  const heartbeat = async ({keepalive = false} = {}) => {
    const result = await postJson(heartbeatUrl, {session_question_id: questionId, focus_seconds_delta: collectFocus()}, keepalive);
    if (checkTerminal(result)) return result;
    remainingSeconds = Math.max(0, Number(result.remaining_seconds || 0));
    syncStartedAt = performance.now();
    if (result.palette_counts) {
      const counts = countsFrom(result.palette_counts);
      document.querySelectorAll("[data-runner-count]").forEach(node => { node.textContent = counts[node.dataset.runnerCount]; });
    }
    return result;
  };
  const withAction = async (work, {flushFirst = true} = {}) => {
    if (actionBusy || terminal) return;
    actionBusy = true;
    const fieldset = form && form.querySelector("fieldset");
    if (fieldset) fieldset.disabled = true;
    try {
      if (!flushFirst || await flush()) await work();
    } catch (error) {
      // Autosave reports its own failure. Action failures keep the current response
      // on-screen so the student can retry without re-entering an answer.
      if (!retry || retry.hidden) {
        setSaveState("Action failed. Your answer is still on this page; try the action again.");
      }
      if (window.console && typeof window.console.error === "function") {
        window.console.error("Assessment Runner action failed", error);
      }
    } finally {
      actionBusy = false;
      if (fieldset) fieldset.disabled = false;
    }
  };
  document.querySelectorAll("[data-runner-nav]").forEach(link => {
    link.addEventListener("click", async event => { event.preventDefault(); await withAction(async () => navigate(link.href)); });
  });
  if (form) form.addEventListener("submit", async event => {
    event.preventDefault();
    const action = event.submitter ? event.submitter.value : "save_next";
    // The action endpoint already saves the current response and updates the
    // review state atomically. Do not autosave first and then perform a second
    // write: one click should produce one authoritative action request.
    await withAction(async () => {
      cancelDebounce();
      // If an autosave was already sent before the click, let that single
      // in-flight write finish before the authoritative action request.
      if (saveFlight) await saveFlight;
      setSaveState(action === "clear" ? "Clearing response…" : "Saving response…", true);
      const current = form.querySelector('[name="current_ordinal"]');
      const next = form.querySelector('[name="next_ordinal"]');
      // Controls named "action" shadow the native form.action property.
      const result = await postJson(form.getAttribute("action"), {
        action, response: responsePayload(), current_ordinal: current ? current.value : 1,
        next_ordinal: next ? next.value : 1, focus_seconds_delta: collectFocus()
      });
      if (checkTerminal(result)) return;
      if (!result.redirect_url) throw new Error("ANVAYA did not return the next question.");
      savedVersion = editVersion;
      setSaveState("Saved to ANVAYA");
      navigate(result.redirect_url);
    }, {flushFirst: false});
  });
  if (submitForm) submitForm.addEventListener("submit", async event => {
    event.preventDefault();
    await withAction(async () => {
      const status = await heartbeat();
      if (terminal) return;
      const counts = countsFrom(status.palette_counts);
      if (!window.confirm(`${counts.answered} answered · ${counts.unanswered} unanswered · ${counts.marked} marked for review.\n\nSubmit test? This ends the timed attempt. Cancel to keep working.`)) return;
      const result = await postJson(submitUrl, {reason: "user"});
      if (result.status === "active") throw new Error("Submission not completed");
      terminal = true;
      navigate(summaryUrl);
    });
  });

  const renderTimer = () => {
    const remaining = Math.max(0, remainingSeconds - Math.floor((performance.now() - syncStartedAt) / 1000));
    if (timer) timer.textContent = [Math.floor(remaining / 3600), Math.floor((remaining % 3600) / 60), remaining % 60].map(part => String(part).padStart(2, "0")).join(":");
    root.classList.toggle("is-time-low", remaining <= 300);
    if (remaining === 0 && !timeoutChecking && !terminal) {
      timeoutChecking = true;
      heartbeat().catch(() => {
        setSaveState("Time check unavailable. Keep this page open; ANVAYA will retry.");
      }).finally(() => { timeoutChecking = false; });
    }
  };
  window.addEventListener("beforeunload", event => {
    if (!allowLeave && (editVersion > savedVersion || saveFlight || actionBusy)) {
      event.preventDefault();
      event.returnValue = "";
      return;
    }
    if (!terminal) heartbeat({keepalive: true}).catch(() => {});
  });
  renderTimer();
  window.setInterval(renderTimer, 1000);
  window.setInterval(() => { if (!terminal) return heartbeat().catch(() => {}); }, 30000);
})();
