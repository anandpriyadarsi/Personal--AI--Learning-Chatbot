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
  const retry = document.getElementById("assessment-save-retry");
  const {questionId, questionType, heartbeatUrl, autosaveUrl, submitUrl, summaryUrl} = root.dataset;
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
    if (!response.ok) throw new Error("Request failed");
    return response.json();
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
  const withAction = async (work) => {
    if (actionBusy || terminal) return;
    actionBusy = true;
    const fieldset = form && form.querySelector("fieldset");
    if (fieldset) fieldset.disabled = true;
    try { if (await flush()) await work(); }
    catch (_error) {
      // flush reports its own failure. Other requests must also leave the input in place.
      if (!retry || retry.hidden) setSaveState("Action failed. Your saved answer is retained; try the action again.");
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
    await withAction(async () => {
      const current = form.querySelector('[name="current_ordinal"]');
      const next = form.querySelector('[name="next_ordinal"]');
      const result = await postJson(form.action, {
        action, response: responsePayload(), current_ordinal: current ? current.value : 1,
        next_ordinal: next ? next.value : 1, focus_seconds_delta: collectFocus()
      });
      if (!checkTerminal(result)) navigate(result.redirect_url);
    });
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
