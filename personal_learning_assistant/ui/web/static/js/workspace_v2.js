/* Progressive view controls only. Academic data stays in the existing form flows. */
(() => {
  if (!document.body.classList.contains('workspace-v2')) return;
  document.body.classList.add('workspace-enhanced');
  const focusButton = document.querySelector('[data-workspace-focus]');
  const sidebar = document.getElementById('app-sidebar');
  const navigationToggle = document.getElementById('nav-toggle');
  const setFocus = (focused) => {
    if (!focusButton) return;
    document.body.classList.toggle('workspace-focus', focused);
    if (sidebar) sidebar.inert = focused || (window.innerWidth <= 860
      ? !document.body.classList.contains('nav-open')
      : document.body.classList.contains('sidebar-collapsed'));
    if (navigationToggle) {
      const expanded = !focused && (window.innerWidth > 860
        ? !document.body.classList.contains('sidebar-collapsed')
        : document.body.classList.contains('nav-open'));
      navigationToggle.setAttribute('aria-expanded', String(expanded));
      navigationToggle.setAttribute('aria-label', focused ? 'Exit focus and show navigation' : expanded ? 'Hide navigation' : 'Show navigation');
    }
    focusButton.setAttribute('aria-pressed', String(focused));
    focusButton.textContent = focused ? 'Exit focus' : 'Focus reading';
  };
  if (focusButton) {
    focusButton.hidden = false;
    focusButton.addEventListener('click', () => setFocus(focusButton.getAttribute('aria-pressed') !== 'true'));
  }
  navigationToggle?.addEventListener('click', event => {
    if (!document.body.classList.contains('workspace-focus')) return;
    setFocus(false);
    if (window.innerWidth > 860) {
      document.body.classList.remove('sidebar-collapsed');
      if (sidebar) sidebar.inert = false;
      navigationToggle.setAttribute('aria-expanded', 'true');
      navigationToggle.setAttribute('aria-label', 'Hide navigation');
      event.stopImmediatePropagation();
    }
  }, true);
  const drawer = document.getElementById('notes-study-tools-drawer');
  const launcher = document.getElementById('notes-study-tools-launcher');
  if (drawer && launcher) {
    const toolbar = document.querySelector('.ws-reader-toolbar');
    if (toolbar) {
      toolbar.append(launcher);
      // A toolbar button has no draggable screen position. Stop the legacy drag
      // gesture here while retaining its existing click/save/close handlers.
      launcher.addEventListener('pointerdown', event => event.stopImmediatePropagation(), true);
    }
    const tabs = [...drawer.querySelectorAll('[data-study-tab]')];
    const syncTabs = () => tabs.forEach(tab => {
      tab.tabIndex = tab.getAttribute('aria-selected') === 'true' ? 0 : -1;
    });
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', syncTabs);
      tab.addEventListener('keydown', event => {
        let target;
        if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
        if (event.key === 'ArrowLeft') target = tabs[(index - 1 + tabs.length) % tabs.length];
        if (event.key === 'Home') target = tabs[0];
        if (event.key === 'End') target = tabs[tabs.length - 1];
        if (!target) return;
        event.preventDefault();
        target.click(); target.focus(); syncTabs();
      });
    });
    // Existing reader script owns open/close and panel selection. Observe it instead of
    // registering a competing click handler or replacing its persisted draft state.
    new MutationObserver(() => {
      syncTabs();
      if (drawer.classList.contains('is-open') && document.activeElement === launcher) {
        requestAnimationFrame(() => {
          if (drawer.classList.contains('is-open') && document.activeElement === launcher) {
            (tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || drawer.querySelector('button'))?.focus();
          }
        });
      }
    }).observe(drawer, {attributes:true, attributeFilter:['class']});
    syncTabs();
  }
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (document.body.classList.contains('workspace-focus') && !drawer?.classList.contains('is-open')) {
      setFocus(false); focusButton.focus();
    }
  });
  // Native anchors to a disclosure also work with JavaScript disabled (:target CSS).
  document.querySelectorAll('a[href="#new-resource"]').forEach(link => {
    link.addEventListener('click', () => {
      const disclosure = document.getElementById('new-resource');
      if (disclosure) disclosure.open = true;
    });
  });
})();
