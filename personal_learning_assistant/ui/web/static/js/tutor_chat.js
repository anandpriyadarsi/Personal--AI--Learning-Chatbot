(() => {
  const form = document.getElementById("tutor-chat-form");
  const input = document.getElementById("agent-question");
  const button = document.getElementById("tutor-send-button");
  const conversation = document.getElementById("tutor-conversation");
  const quickActions = document.querySelectorAll("[data-tutor-prompt]");

  if (conversation && conversation.children.length > 1) {
    requestAnimationFrame(() => {
      const turns = conversation.querySelectorAll(".tutor-turn");
      const last = turns[turns.length - 1];
      if (last) last.scrollIntoView({ block: "end" });
    });
  }

  quickActions.forEach((action) => {
    action.addEventListener("click", () => {
      if (!input) return;
      input.value = action.dataset.tutorPrompt || "";
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    });
  });

  if (!form || !input || !button) return;

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (input.value.trim()) form.requestSubmit();
    }
  });

  form.addEventListener("submit", () => {
    button.disabled = true;
    button.textContent = "Thinking…";
    input.setAttribute("aria-busy", "true");
  });
})();
