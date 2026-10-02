(() => {
  "use strict";
  const dialog = document.getElementById("coding-helper-dialog");
  if (!dialog) return;
  const opener = document.getElementById("coding-helper-open");
  const form = document.getElementById("coding-helper-form");
  const action = document.getElementById("coding-helper-action");
  const status = document.getElementById("coding-helper-status");
  const send = document.getElementById("coding-helper-send");
  const answer = document.getElementById("coding-helper-answer");
  const answerSection = document.getElementById("coding-helper-answer-section");
  let busy = false;
  opener.addEventListener("click", () => dialog.showModal());
  document.getElementById("coding-helper-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => opener.focus());
  // Keep the app-shell Escape shortcut from changing the stored sidebar choice.
  dialog.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); dialog.close(); }
  });
  const updateMode = () => {
    const full = document.getElementById("coding-full-solution");
    if (full) {
      full.hidden = !["pseudocode", "debug", "explain_code"].includes(action.value);
      if (full.hidden) full.querySelector("input").checked = false;
    }
    const hint = document.getElementById("coding-hint-level");
    if (hint) hint.hidden = action.value !== "hint";
  };
  action.addEventListener("change", updateMode);
  updateMode();
  document.getElementById("coding-helper-rebuild").addEventListener("click", () => {
    action.value = "rebuild"; updateMode(); form.elements.namedItem("attempt").focus();
    status.textContent = "Close the explanation and describe what you can rebuild. Then choose Get help.";
    answerSection.hidden = true;
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy) return;
    busy = true; send.disabled = true;
    status.textContent = "Preparing a learning step… Your assessment timer is still running.";
    const data = new FormData(form);
    const payload = Object.fromEntries(["action", "topic", "message", "code", "error", "attempt"].map(key => [key, String(data.get(key) || "")]));
    payload.include_question = data.has("include_question");
    payload.full_solution = data.has("full_solution");
    payload.hint_level = Number(data.get("hint_level") || 1);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 55000);
    try {
      const response = await fetch(form.getAttribute("action"), {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: {"Content-Type": "application/json", "Accept": "application/json"},
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok || typeof result.reply !== "string") throw new Error(result.error || "Coding help is unavailable. Try the Operations Map.");
      answer.textContent = result.reply; // Provider prose is text, never HTML or executable code.
      answerSection.hidden = false;
      status.textContent = "Read the step, try it, then explain what changed.";
    } catch (error) {
      status.textContent = error.name === "AbortError" ? "The request timed out. Your code is still here; retry or use the Operations Map." : "Help unavailable. Your code is still here. " + error.message;
    } finally {
      window.clearTimeout(timeout); busy = false; send.disabled = false;
    }
  });
  const search = document.getElementById("coding-map-search");
  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    let count = 0;
    dialog.querySelectorAll(".coding-operation-card").forEach(card => {
      card.hidden = !card.dataset.search.includes(query);
      if (!card.hidden) count++;
    });
    dialog.querySelectorAll(".coding-map-category").forEach(category => {
      category.hidden = !Array.from(category.querySelectorAll(".coding-operation-card")).some(card => !card.hidden);
      if (query && !category.hidden) category.open = true;
    });
    document.getElementById("coding-map-status").textContent = `${count} matching operation${count === 1 ? "" : "s"}`;
  });
})();
