(function () {
  "use strict";
  const input = document.getElementById("knowledge-query");
  const box = document.getElementById("knowledge-suggestions");
  if (!input || !box) return;
  let timer = null;
  let controller = null;

  function clear() {
    box.hidden = true;
    box.replaceChildren();
  }

  function render(items) {
    box.replaceChildren();
    if (!Array.isArray(items) || items.length === 0) {
      clear();
      return;
    }
    items.forEach(function (item) {
      const a = document.createElement(item.open_target ? "a" : "button");
      a.className = "knowledge-suggestion";
      if (item.open_target) {
        a.href = item.open_target;
      } else {
        a.type = "button";
        a.addEventListener("click", function () {
          input.value = item.value || item.label || "";
          input.form.requestSubmit();
        });
      }
      const strong = document.createElement("strong");
      strong.textContent = item.label || "";
      const small = document.createElement("span");
      small.textContent = item.subtitle || "";
      a.append(strong, small);
      box.appendChild(a);
    });
    box.hidden = false;
  }

  input.addEventListener("input", function () {
    window.clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) {
      clear();
      return;
    }
    timer = window.setTimeout(function () {
      if (controller) controller.abort();
      controller = new AbortController();
      const base = input.dataset.suggestUrl || "/api/search/suggest";
      fetch(base + "?q=" + encodeURIComponent(q), {
        credentials: "same-origin",
        signal: controller.signal
      }).then(function (r) {
        if (!r.ok) throw new Error("suggest failed");
        return r.json();
      }).then(function (payload) {
        render(payload.results || []);
      }).catch(function () {});
    }, 200);
  });

  document.addEventListener("click", function (event) {
    if (!box.contains(event.target) && event.target !== input) clear();
  });
})();
