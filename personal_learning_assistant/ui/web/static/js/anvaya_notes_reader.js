(() => {
  const launcher = document.getElementById("notes-study-tools-launcher");
  const drawer = document.getElementById("notes-study-tools-drawer");
  const close = document.getElementById("notes-study-tools-close");
  if (!launcher || !drawer || !close) return;

  const setOpen = (open) => {
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
    setOpen(!drawer.classList.contains("is-open"));
  });
  close.addEventListener("click", () => setOpen(false));

  const tabs = drawer.querySelectorAll("[data-study-tab]");
  const panels = drawer.querySelectorAll("[data-study-panel]");
  const selectTab = (button) => {
    tabs.forEach((tab) => {
      const active = tab === button;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    panels.forEach((panel) => {
      const active = panel.dataset.studyPanel === button.dataset.studyTab;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  };
  tabs.forEach((button) => {
    button.addEventListener("click", () => selectTab(button));
  });

  const key = launcher.dataset.positionKey || "anvaya.notes.studyTools.position";
  const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
  const place = (left, top) => {
    const width = launcher.offsetWidth || 120;
    const height = launcher.offsetHeight || 42;
    launcher.style.left = clamp(left, 8, Math.max(8, window.innerWidth - width - 8)) + "px";
    launcher.style.top = clamp(top, 8, Math.max(8, window.innerHeight - height - 8)) + "px";
    launcher.style.right = "auto";
    launcher.style.bottom = "auto";
  };

  try {
    const saved = JSON.parse(localStorage.getItem(key) || "null");
    if (saved) requestAnimationFrame(() => place(saved.left, saved.top));
  } catch (_error) {}

  let drag = null;
  launcher.addEventListener("pointerdown", (event) => {
    const rect = launcher.getBoundingClientRect();
    drag = {id:event.pointerId,x:event.clientX,y:event.clientY,left:rect.left,top:rect.top,moved:false};
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
      try { localStorage.setItem(key, JSON.stringify({left:rect.left,top:rect.top})); } catch (_error) {}
    }
    drag = null;
  });
  launcher.addEventListener("pointercancel", () => { drag = null; });
  window.addEventListener("resize", () => {
    if (launcher.style.left) {
      const rect = launcher.getBoundingClientRect();
      place(rect.left, rect.top);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer.classList.contains("is-open")) setOpen(false);
  });
  const params = new URLSearchParams(window.location.search);
  const selectedTab = Array.from(tabs).find((tab) => tab.dataset.studyTab === params.get("study_tab"));
  if (selectedTab) selectTab(selectedTab);
  setOpen(params.get("study_tools") === "1");
})();
