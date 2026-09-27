(() => {
  "use strict";

  const promptSource = document.getElementById("assessment-resolved-prompt");
  const previewDialog = document.getElementById("assessment-prompt-preview");
  const editorDialog = document.getElementById("assessment-prompt-editor");
  const subjectDialog = document.getElementById("assessment-subject-picker");
  const launcher = document.getElementById("assessment-alex-tools-launcher");
  const drawer = document.getElementById("assessment-alex-tools-drawer");
  const drawerClose = document.getElementById("assessment-alex-tools-close");

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
      setCopyStatus("Choose assessment type and subject first.");
      return;
    }
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else if (!legacyCopy(text)) {
        throw new Error("copy failed");
      }
      setCopyStatus("Personalized prompt copied.");
    } catch (_error) {
      setCopyStatus("Copy failed — preview the prompt and copy manually.");
    }
  };

  const openDialog = (dialog) => {
    if (dialog && typeof dialog.showModal === "function" && !dialog.open) {
      dialog.showModal();
    }
  };

  const closeDialog = (dialog) => {
    if (dialog && dialog.open) dialog.close();
  };

  document.querySelectorAll("[data-copy-prompt]").forEach((button) => {
    button.addEventListener("click", copyPrompt);
  });

  document.querySelectorAll("[data-open-prompt-preview]").forEach((button) => {
    button.addEventListener("click", () => openDialog(previewDialog));
  });

  document.querySelectorAll("[data-open-prompt-editor]").forEach((button) => {
    button.addEventListener("click", () => {
      closeDialog(previewDialog);
      openDialog(editorDialog);
    });
  });

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      closeDialog(document.getElementById(button.dataset.closeDialog));
    });
  });

  [previewDialog, editorDialog, subjectDialog].forEach((dialog) => {
    if (!dialog) return;
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

  document.querySelectorAll("[data-open-subject-picker]").forEach((button) => {
    button.addEventListener("click", () => openDialog(subjectDialog));
  });

  if (subjectDialog && subjectDialog.hasAttribute("data-auto-open-subject-picker")) {
    window.requestAnimationFrame(() => openDialog(subjectDialog));
  }

  if (launcher && drawer && drawerClose) {
    const setDrawerOpen = (open) => {
      drawer.classList.toggle("is-open", open);
      drawer.setAttribute("aria-hidden", open ? "false" : "true");
      drawer.inert = !open;
      launcher.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open && drawer.contains(document.activeElement)) launcher.focus();
    };

    launcher.addEventListener("click", () => {
      if (launcher.dataset.dragged === "1") {
        launcher.dataset.dragged = "0";
        return;
      }
      setDrawerOpen(!drawer.classList.contains("is-open"));
    });
    drawerClose.addEventListener("click", () => setDrawerOpen(false));
    document.querySelectorAll("[data-open-alex-tools]").forEach((button) => {
      button.addEventListener("click", () => setDrawerOpen(true));
    });
    drawer.querySelectorAll('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener("click", () => setDrawerOpen(false));
    });

    const key = launcher.dataset.positionKey || "anvaya.assessment.alexTools.position";
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const place = (left, top) => {
      const width = launcher.offsetWidth || 150;
      const height = launcher.offsetHeight || 44;
      launcher.style.left =
        clamp(left, 8, Math.max(8, window.innerWidth - width - 8)) + "px";
      launcher.style.top =
        clamp(top, 8, Math.max(8, window.innerHeight - height - 8)) + "px";
      launcher.style.right = "auto";
      launcher.style.bottom = "auto";
    };

    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved) window.requestAnimationFrame(() => place(saved.left, saved.top));
    } catch (_error) {}

    let drag = null;
    launcher.addEventListener("pointerdown", (event) => {
      const rect = launcher.getBoundingClientRect();
      drag = {
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        left: rect.left,
        top: rect.top,
        moved: false,
      };
      launcher.setPointerCapture(event.pointerId);
    });
    launcher.addEventListener("pointermove", (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 5) drag.moved = true;
      if (drag.moved) place(drag.left + dx, drag.top + dy);
    });
    launcher.addEventListener("pointerup", (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      if (drag.moved) {
        launcher.dataset.dragged = "1";
        const rect = launcher.getBoundingClientRect();
        try {
          localStorage.setItem(
            key,
            JSON.stringify({left: rect.left, top: rect.top})
          );
        } catch (_error) {}
      }
      drag = null;
    });
    launcher.addEventListener("pointercancel", () => {
      drag = null;
    });
    window.addEventListener("resize", () => {
      if (launcher.style.left) {
        const rect = launcher.getBoundingClientRect();
        place(rect.left, rect.top);
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && drawer.classList.contains("is-open")) {
        setDrawerOpen(false);
      }
    });
  }

  document.querySelectorAll("[data-confirm-delete]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm("Delete this rejected package from Assessment Studio history?")) {
        event.preventDefault();
      }
    });
  });
})();
