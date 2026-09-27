(() => {
  "use strict";

  document.querySelectorAll("[data-confirm-reject]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm("Reject this package? No assessment will be created from it.")) event.preventDefault();
    });
  });

  const source = document.getElementById("assessment-alex-review-prompt");

  const setStatus = (message) => {
    document.querySelectorAll("[data-review-copy-status]").forEach((node) => {
      node.textContent = message;
    });
    window.clearTimeout(setStatus._timer);
    setStatus._timer = window.setTimeout(() => {
      document.querySelectorAll("[data-review-copy-status]").forEach((node) => {
        node.textContent = "";
      });
    }, 2600);
  };

  const legacyCopy = (text) => {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  };

  document.querySelectorAll("[data-copy-review-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = source ? source.value : "";
      if (!text.trim()) {
        setStatus("Alex review prompt is unavailable.");
        return;
      }
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else if (!legacyCopy(text)) {
          throw new Error("copy failed");
        }
        setStatus("Alex review prompt copied.");
      } catch (_error) {
        setStatus("Copy failed. Open the safe review prompt below to select and copy it manually.");
      }
    });
  });
})();
