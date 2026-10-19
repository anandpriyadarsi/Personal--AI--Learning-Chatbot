/* Progressive enhancement only: native <details> remains usable without JavaScript. */
(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const formPanel = document.querySelector(".ws-resources details#new-resource");
    if (!formPanel) return;
    const reveal = () => {
      formPanel.open = true;
      const title = formPanel.querySelector('input[name="title"]');
      if (title) title.focus({ preventScroll: true });
    };
    document.querySelectorAll('.ws-resources a[href="#new-resource"]').forEach(link => {
      link.addEventListener("click", reveal);
    });
    if (window.location.hash === "#new-resource") reveal();
    window.addEventListener("hashchange", () => {
      if (window.location.hash === "#new-resource") reveal();
    });
  });
})();
