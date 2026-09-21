(() => {
  const form = document.getElementById("tutor-chat-form");
  const input = document.getElementById("agent-question");
  const button = document.getElementById("tutor-send-button");
  const conversation = document.getElementById("tutor-conversation");

  if (conversation) {
    requestAnimationFrame(() => {
      conversation.scrollTop = conversation.scrollHeight;
    });
  }

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
