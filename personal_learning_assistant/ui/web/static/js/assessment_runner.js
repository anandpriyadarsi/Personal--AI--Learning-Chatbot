(() => {
  const root = document.getElementById("assessment-runner");
  if (!root) return;

  const form = document.getElementById("assessment-response-form");
  const submitForm = document.getElementById("assessment-submit-form");
  const timer = document.getElementById("assessment-timer");
  const saveStatus = document.getElementById("assessment-save-status");
  const focusInput = document.getElementById("assessment-focus-seconds");

  const sessionId = root.dataset.sessionId;
  const questionId = root.dataset.questionId;
  const questionType = root.dataset.questionType;
  const heartbeatUrl = root.dataset.heartbeatUrl;
  const autosaveUrl = root.dataset.autosaveUrl;
  const submitUrl = root.dataset.submitUrl;
  const summaryUrl = root.dataset.summaryUrl;

  let remainingSeconds = Math.max(0, Number(root.dataset.remainingSeconds || "0"));
  let syncStartedAt = performance.now();
  let focusStartedAt = performance.now();
  let unsentFocusSeconds = 0;
  let autosaveTimer = null;
  let timeoutHandled = false;
  let autosaveInFlight = null;

  const visibleElapsedSeconds = () => {
    if (document.visibilityState !== "visible") return 0;
    const now = performance.now();
    const elapsed = Math.max(0, Math.floor((now - focusStartedAt) / 1000));
    focusStartedAt = now;
    return elapsed;
  };

  const collectFocus = () => {
    unsentFocusSeconds += visibleElapsedSeconds();
    const send = Math.max(0, Math.min(60, unsentFocusSeconds));
    unsentFocusSeconds -= send;
    if (focusInput) focusInput.value = String(send);
    return send;
  };

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      unsentFocusSeconds += visibleElapsedSeconds();
    } else {
      focusStartedAt = performance.now();
    }
  });

  const formatTime = (seconds) => {
    const safe = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(safe / 3600);
    const minutes = Math.floor((safe % 3600) / 60);
    const secs = safe % 60;
    return [hours, minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
  };

  const currentRemaining = () => {
    const elapsed = Math.floor((performance.now() - syncStartedAt) / 1000);
    return Math.max(0, remainingSeconds - elapsed);
  };

  const renderTimer = () => {
    if (!timer) return;
    const remaining = currentRemaining();
    timer.textContent = formatTime(remaining);
    root.classList.toggle("is-time-low", remaining <= 300);
    if (remaining <= 0) handleTimeout();
  };

  const responsePayload = () => {
    if (!form) return {};
    if (questionType === "mcq" || questionType === "msq") {
      const selected = Array.from(form.querySelectorAll('input[name="option_ids"]:checked'))
        .map((input) => input.value);
      return { selected_option_ids: selected };
    }
    if (questionType === "numerical" || questionType === "fill_blank" || questionType === "true_false") {
      const checked = form.querySelector('input[name="answer_value"]:checked');
      const input = checked || form.querySelector('[name="answer_value"]');
      return { value: input ? input.value : "" };
    }
    if (questionType === "short_subjective" || questionType === "long_subjective") {
      const input = form.querySelector('[name="answer_text"]');
      return { text: input ? input.value : "" };
    }
    return {};
  };

  const postJson = async (url, payload, keepalive = false) => {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(payload),
      credentials: "same-origin",
      keepalive
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || "Request failed");
    }
    return response.json();
  };

  const setSaveState = (text, pending = false) => {
    if (!saveStatus) return;
    saveStatus.textContent = text;
    saveStatus.classList.toggle("is-pending", pending);
  };

  const autosave = async ({ silent = false, keepalive = false } = {}) => {
    if (!autosaveUrl || timeoutHandled) return null;
    if (!silent) setSaveState("Saving…", true);
    const payload = {
      response: responsePayload(),
      focus_seconds_delta: collectFocus()
    };
    try {
      const result = await postJson(autosaveUrl, payload, keepalive);
      if (result.status && result.status !== "active") {
        window.location.assign(summaryUrl);
        return result;
      }
      if (!silent) setSaveState("Saved to ANVAYA");
      return result;
    } catch (_error) {
      if (!silent) setSaveState("Autosave pending — use Save & Next");
      return null;
    }
  };

  const queueAutosave = () => {
    if (autosaveTimer) window.clearTimeout(autosaveTimer);
    autosaveTimer = window.setTimeout(() => {
      autosaveInFlight = autosave().finally(() => {
        autosaveInFlight = null;
      });
    }, 900);
  };

  if (form) {
    form.querySelectorAll("input, textarea").forEach((input) => {
      if (input.type === "hidden") return;
      input.addEventListener(input.tagName === "TEXTAREA" || input.type === "text" ? "input" : "change", queueAutosave);
    });

    form.addEventListener("submit", () => {
      if (autosaveTimer) window.clearTimeout(autosaveTimer);
      if (focusInput) focusInput.value = String(collectFocus());
      setSaveState("Saving response…", true);
    });
  }

  document.querySelectorAll("[data-runner-nav]").forEach((link) => {
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      const target = link.href;
      if (autosaveTimer) window.clearTimeout(autosaveTimer);
      if (autosaveInFlight) await autosaveInFlight;
      await autosave({ silent: true });
      window.location.assign(target);
    });
  });

  const heartbeat = async ({ keepalive = false } = {}) => {
    if (!heartbeatUrl || timeoutHandled) return;
    try {
      const result = await postJson(
        heartbeatUrl,
        {
          session_question_id: questionId,
          focus_seconds_delta: collectFocus()
        },
        keepalive
      );
      if (result.status !== "active") {
        window.location.assign(summaryUrl);
        return;
      }
      remainingSeconds = Math.max(0, Number(result.remaining_seconds || 0));
      syncStartedAt = performance.now();
      renderTimer();
    } catch (_error) {
      // Keep the local monotonic countdown running; the next server write re-enforces expiry.
    }
  };

  const handleTimeout = async () => {
    if (timeoutHandled) return;
    timeoutHandled = true;
    setSaveState("Checking server time…", true);
    try {
      const result = await postJson(
        heartbeatUrl,
        {
          session_question_id: questionId,
          focus_seconds_delta: collectFocus()
        }
      );
      if (result.status === "active") {
        remainingSeconds = Math.max(0, Number(result.remaining_seconds || 0));
        syncStartedAt = performance.now();
        timeoutHandled = false;
        setSaveState("Saved to ANVAYA");
        renderTimer();
        return;
      }
    } catch (_error) {
      timeoutHandled = false;
      setSaveState("Server check pending — timer will retry");
      return;
    }
    window.location.assign(summaryUrl);
  };

  if (submitForm) {
    submitForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!window.confirm("Submit the test now? You cannot continue this timed session after submission.")) {
        return;
      }
      setSaveState("Saving and submitting…", true);
      if (autosaveTimer) window.clearTimeout(autosaveTimer);
      if (autosaveInFlight) await autosaveInFlight;
      await autosave({ silent: true });
      await heartbeat();
      try {
        await postJson(submitUrl, { reason: "user" });
      } catch (_error) {
        setSaveState("Submission failed — try again");
        return;
      }
      window.location.assign(summaryUrl);
    });
  }

  window.addEventListener("beforeunload", () => {
    if (timeoutHandled) return;
    const focusDelta = collectFocus();
    if (heartbeatUrl && focusDelta > 0) {
      postJson(
        heartbeatUrl,
        {
          session_question_id: questionId,
          focus_seconds_delta: focusDelta
        },
        true
      ).catch(() => {});
    }
  });

  renderTimer();
  window.setInterval(renderTimer, 1000);
  window.setInterval(() => heartbeat(), 30000);
})();
