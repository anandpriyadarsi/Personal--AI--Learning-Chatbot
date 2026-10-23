(() => {
  document.querySelectorAll("[data-card-template-picker]").forEach((picker) => {
    const tabs = Array.from(picker.querySelectorAll("[data-card-family-tab]"));
    const panels = Array.from(picker.querySelectorAll("[data-card-family-panel]"));

    const showFamily = (family) => {
      tabs.forEach((tab) => {
        const active = tab.dataset.cardFamilyTab === family;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.cardFamilyPanel === family);
      });
    };

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => showFamily(tab.dataset.cardFamilyTab));
    });

    picker.querySelectorAll('input[name="card_style"]').forEach((input) => {
      input.addEventListener("change", () => {
        picker.querySelectorAll(".anvaya-card-template-option").forEach((option) => {
          option.classList.toggle(
            "is-selected",
            option.contains(input) && input.checked
          );
        });
      });
      if (input.checked) {
        input.closest(".anvaya-card-template-option")?.classList.add("is-selected");
      }
    });
  });
})();
