(() => {
  const globalSearch = document.getElementById("global-study-search");
  if (globalSearch) {
    globalSearch.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const query = globalSearch.value.trim();
      if (!query) return;
      const target = globalSearch.dataset.searchUrl || "/knowledge";
      window.location.assign(`${target}?q=${encodeURIComponent(query)}`);
    });
  }

  const toggle = document.getElementById("nav-toggle");
  const sidebar = document.getElementById("app-sidebar");
  const backdrop = document.getElementById("nav-backdrop");
  if (!toggle || !sidebar || !backdrop) return;

  const desktop = () => window.innerWidth > 860;
  const storageKey = "anvaya.sidebar.collapsed";

  const setMobileOpen = (open) => {
    document.body.classList.toggle("nav-open", open);
    sidebar.inert = !open;
    backdrop.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
  };

  const setDesktopCollapsed = (collapsed, persist = true) => {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    sidebar.inert = collapsed;
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.setAttribute("aria-label", collapsed ? "Show navigation" : "Hide navigation");
    backdrop.hidden = true;
    if (persist) {
      try {
        localStorage.setItem(storageKey, collapsed ? "1" : "0");
      } catch (_error) {
        // Local preference is optional.
      }
    }
  };

  const restoreDesktopPreference = () => {
    if (!desktop()) return;
    let collapsed = false;
    try {
      collapsed = localStorage.getItem(storageKey) === "1";
    } catch (_error) {
      collapsed = false;
    }
    setDesktopCollapsed(collapsed, false);
  };

  toggle.addEventListener("click", () => {
    if (desktop()) {
      setDesktopCollapsed(!document.body.classList.contains("sidebar-collapsed"));
      return;
    }
    setMobileOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  backdrop.addEventListener("click", () => setMobileOpen(false));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (document.querySelector(".notes-study-tools-drawer.is-open")) return;
    if (desktop()) {
      if (document.body.classList.contains("sidebar-collapsed")) {
        setDesktopCollapsed(false);
        toggle.focus();
      }
    } else if (document.body.classList.contains("nav-open")) {
      setMobileOpen(false);
      toggle.focus();
    }
  });

  sidebar.querySelectorAll("a[href]").forEach((link) => {
    link.addEventListener("click", () => {
      if (!desktop()) setMobileOpen(false);
    });
  });

  let lastDesktop = desktop();
  window.addEventListener("resize", () => {
    const nowDesktop = desktop();
    if (nowDesktop === lastDesktop) return;
    lastDesktop = nowDesktop;
    if (nowDesktop) {
      document.body.classList.remove("nav-open");
      restoreDesktopPreference();
    } else {
      document.body.classList.remove("sidebar-collapsed");
      setMobileOpen(false);
    }
  });

  if (desktop()) restoreDesktopPreference();
  else setMobileOpen(false);
})();
