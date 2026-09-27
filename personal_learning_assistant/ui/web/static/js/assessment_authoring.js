(() => {
  "use strict";

  const promptSource = document.getElementById("assessment-resolved-prompt");
  const previewDialog = document.getElementById("assessment-prompt-preview");
  const editorDialog = document.getElementById("assessment-prompt-editor");

  const setCopyStatus = (message) => {
    document.querySelectorAll("[data-copy-status]").forEach((node) => {
      node.textContent = message;
    });
    window.clearTimeout(setCopyStatus._timer);
    setCopyStatus._timer = window.setTimeout(() => {
      document.querySelectorAll("[data-copy-status]").forEach((node) => {
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

  const copyPrompt = async () => {
    const text = promptSource ? promptSource.value : "";
    if (!text.trim()) {
      setCopyStatus("Prompt is unavailable.");
      return;
    }
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else if (!legacyCopy(text)) {
        throw new Error("copy failed");
      }
      setCopyStatus("Prompt copied.");
    } catch (_error) {
      setCopyStatus("Copy failed — open the prompt and copy manually.");
    }
  };

  document.querySelectorAll("[data-copy-prompt]").forEach((button) => {
    button.addEventListener("click", copyPrompt);
  });

  document.querySelectorAll("[data-open-prompt-preview]").forEach((button) => {
    button.addEventListener("click", () => {
      if (previewDialog && typeof previewDialog.showModal === "function") {
        previewDialog.showModal();
      }
    });
  });

  document.querySelectorAll("[data-open-prompt-editor]").forEach((button) => {
    button.addEventListener("click", () => {
      if (previewDialog && previewDialog.open) {
        previewDialog.close();
      }
      if (editorDialog && typeof editorDialog.showModal === "function") {
        editorDialog.showModal();
      }
    });
  });

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.closeDialog);
      if (dialog && dialog.open) {
        dialog.close();
      }
    });
  });

  [previewDialog, editorDialog].forEach((dialog) => {
    if (!dialog) return;
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  });
})();
