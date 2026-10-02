/* Coding Helper never reads or changes the assessment answer form. */
(function (root) {
  "use strict";
  function parseReply(reply) {
    const blocks = [];
    let lines = [], fence = null;
    const flush = () => {
      if (lines.length) blocks.push({kind: fence || "text", text: lines.join("\n")});
      lines = [];
    };
    for (const line of String(reply).slice(0, 16000).split(/\r?\n/)) {
      if (/^\s*```/.test(line)) {
        flush();
        fence = fence ? null : (/^\s*```(?:output|text)\s*$/.test(line) ? "output" : "code");
      } else if (!fence && (/^#{1,3}\s+/.test(line) || /^(Explanation|Code|Output|Hint|Steps|Remember|Common mistake|Try this yourself|Viva question):?$/i.test(line))) {
        flush(); blocks.push({kind:"heading", text:line.replace(/^#{1,3}\s+/, "").replace(/:$/, "")});
      } else if (!fence && !line.trim()) { flush(); }
      else { lines.push(line); }
    }
    flush();
    return blocks;
  }
  function createConversation() {
    let generation = 0, token = "";
    return {
      get token() { return token; },
      start() { return ++generation; },
      isCurrent(ticket) { return ticket === generation; },
      finish(ticket, next) { if (ticket !== generation) return false; token = next; return true; },
      cancel() { generation++; },
      reset() { generation++; token = ""; }
    };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {parseReply, createConversation};
  if (typeof document === "undefined") return;
  const dialog = document.getElementById("coding-helper-dialog");
  if (!dialog) return;
  const byId = id => document.getElementById(id);
  const opener = byId("coding-helper-open"), form = byId("coding-helper-form");
  const action = byId("coding-helper-action"), status = byId("coding-helper-status");
  const send = byId("coding-helper-send"), answer = byId("coding-helper-answer");
  const answerSection = byId("coding-helper-answer-section");
  const conversation = createConversation();
  let busy = false, controller = null;
  const field = name => form.elements.namedItem(name);
  function cancelPending() {
    conversation.cancel();
    if (controller) controller.abort();
    controller = null; busy = false; send.disabled = false;
    form.setAttribute("aria-busy", "false");
  }
  function clearContext() {
    cancelPending(); conversation.reset(); answer.replaceChildren(); answerSection.hidden = true;
    byId("coding-context-status").textContent = "New context. Only this question's follow-ups are remembered.";
  }
  function updateMode() {
    const option = action.selectedOptions[0];
    byId("coding-mode-guidance").textContent = option.dataset.guidance;
    const full = byId("coding-full-solution");
    if (full) {
      full.hidden = option.dataset.allowsSolution !== "true";
      if (full.hidden && field("full_solution").checked) { field("full_solution").checked = false; clearContext(); }
    }
    if (byId("coding-hint-level")) byId("coding-hint-level").hidden = action.value !== "hint";
    if (byId("coding-explanation-depth")) byId("coding-explanation-depth").hidden = action.value !== "explain_code";
  }
  opener.addEventListener("click", () => dialog.showModal());
  function closeHelper() {
    if (busy) status.textContent = "Request cancelled. Your inputs are still here.";
    cancelPending(); // Invalidate immediately; the native close event is queued.
    dialog.close();
  }
  byId("coding-helper-close").addEventListener("click", closeHelper);
  dialog.addEventListener("close", () => {
    if (busy) status.textContent = "Request cancelled. Your inputs are still here.";
    cancelPending(); opener.focus();
  });
  dialog.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeHelper(); }
  });
  action.addEventListener("change", () => { cancelPending(); updateMode(); });
  for (const name of ["include_question", "full_solution"]) {
    if (field(name)) field(name).addEventListener("change", clearContext);
  }
  byId("coding-helper-reset").addEventListener("click", () => {
    clearContext(); form.reset(); updateMode(); status.textContent = "Helper reset. Your assessment is unchanged."; action.focus();
  });
  byId("coding-helper-rebuild").addEventListener("click", () => {
    action.value = "rebuild"; updateMode(); field("attempt").value = ""; field("attempt").focus();
    status.textContent = "Describe what you can rebuild without copying. Then choose Get help.";
    answerSection.hidden = true;
  });
  updateMode();

  async function copyText(text, button) {
    const label = button.textContent;
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
      window.setTimeout(() => { button.textContent = label; }, 1800);
    } catch (_) { status.textContent = "Copy unavailable. Select the code and copy it manually."; }
  }
  function renderReply(reply) {
    answer.replaceChildren();
    for (const block of parseReply(reply)) {
      const node = document.createElement(block.kind === "heading" ? "h4" : block.kind === "text" ? "p" : "pre");
      node.textContent = block.text; // Never provider HTML, Markdown links or images.
      if (block.kind === "code" || block.kind === "output") {
        const section = document.createElement("section"); section.className = "coding-response-block";
        const label = document.createElement("span"); label.textContent = block.kind === "code" ? "Code · run in Colab" : "Predicted output · not executed";
        section.append(label, node);
        if (block.kind === "code") {
          const button = document.createElement("button"); button.type = "button";
          button.className = "button button-secondary compact-button"; button.textContent = "Copy code";
          button.addEventListener("click", () => copyText(block.text, button)); section.append(button);
        }
        answer.append(section);
      } else { answer.append(node); }
    }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy) return;
    busy = true; send.disabled = true; form.setAttribute("aria-busy", "true");
    const ticket = conversation.start();
    status.textContent = "Preparing a learning step… Your assessment timer is still running.";
    const data = new FormData(form);
    const payload = Object.fromEntries(["action", "topic", "message", "code", "error", "attempt", "card_id"].map(key => [key, String(data.get(key) || "")]));
    payload.explanation_depth = String(data.get("explanation_depth") || "overview");
    payload.include_question = data.has("include_question"); payload.full_solution = data.has("full_solution");
    payload.hint_level = Number(data.get("hint_level") || 1); payload.context_token = conversation.token;
    // Restricted exams never send a card override or arbitrary explanation depth.
    if (dialog.dataset.policy !== "full") { delete payload.card_id; payload.explanation_depth = "overview"; }
    const requestController = new AbortController(); controller = requestController;
    const timeout = window.setTimeout(() => requestController.abort(), 55000);
    answerSection.hidden = true;
    try {
      const response = await fetch(form.getAttribute("action"), {
        method:"POST", credentials:"same-origin", signal:requestController.signal,
        headers:{"Content-Type":"application/json", "Accept":"application/json"}, body:JSON.stringify(payload)
      });
      const result = await response.json();
      if (!conversation.isCurrent(ticket)) return;
      if (!response.ok || typeof result.reply !== "string" || typeof result.context_token !== "string") {
        const message = result.error || "Coding help is unavailable. Try the Operations Map.";
        if (result.reset_context) {
          clearContext();
          status.textContent = "Help unavailable. Your inputs are still here. " + message;
          return;
        }
        throw new Error(message);
      }
      if (!conversation.finish(ticket, result.context_token)) return;
      renderReply(result.reply); answerSection.hidden = false;
      status.textContent = "Read the step, try it, then explain what changed.";
      byId("coding-context-status").textContent = result.context_token ? "Up to 3 recent exchanges on this question · expires after 15 minutes." : "General concept help · no conversation history.";
    } catch (error) {
      if (!conversation.isCurrent(ticket)) return;
      status.textContent = error.name === "AbortError" ? "The request timed out. Your code is still here; retry or use the Operations Map." : "Help unavailable. Your inputs are still here. " + error.message;
    } finally {
      window.clearTimeout(timeout);
      if (conversation.isCurrent(ticket)) { controller = null; busy = false; send.disabled = false; form.setAttribute("aria-busy", "false"); }
    }
  });
  const search = byId("coding-map-search"), categorySelect = byId("coding-map-category");
  const filterCards = () => {
    const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let count = 0;
    dialog.querySelectorAll(".coding-operation-card").forEach(card => {
      card.hidden = (categorySelect.value && card.dataset.category !== categorySelect.value) || !words.every(word => card.dataset.search.includes(word));
      if (!card.hidden) count++;
    });
    dialog.querySelectorAll(".coding-map-category").forEach(category => {
      category.hidden = !Array.from(category.querySelectorAll(".coding-operation-card")).some(card => !card.hidden);
      if (words.length && !category.hidden) category.open = true;
    });
    byId("coding-map-status").textContent = `${count} matching operation${count === 1 ? "" : "s"}`;
  };
  search.addEventListener("input", filterCards); categorySelect.addEventListener("change", filterCards);
  dialog.querySelectorAll(".coding-copy").forEach(button => button.addEventListener("click", () => copyText(button.previousElementSibling.textContent, button)));
  dialog.querySelectorAll(".coding-use-card").forEach(button => button.addEventListener("click", () => {
    const card = button.closest(".coding-operation-card");
    clearContext();
    action.value = "memory";
    field("topic").value = dialog.dataset.policy === "full" ? card.dataset.cardName : card.dataset.cardId;
    if (field("card_id")) field("card_id").value = card.dataset.cardId;
    updateMode(); action.focus(); form.scrollIntoView({block:"start"});
    status.textContent = "Operation selected. Choose Get help, then explain it in your own words.";
  }));
  if (field("card_id")) field("topic").addEventListener("input", () => { field("card_id").value = ""; });
})(typeof globalThis !== "undefined" ? globalThis : this);
