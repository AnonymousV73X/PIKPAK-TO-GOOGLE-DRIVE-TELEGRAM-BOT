/* Wraps any <select class="styled-select"> with a fully custom-styled dropdown
   (native selects can't have their open option list themed via CSS). The
   original <select> stays in the DOM — hidden but functional — so existing
   code that reads/sets .value or listens for 'change' keeps working untouched. */
(function () {
  function enhanceSelect(select) {
    if (select.dataset.enhanced) return;
    select.dataset.enhanced = "1";

    const wrap = document.createElement("div");
    wrap.className = "cselect";
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("cselect-native");
    select.tabIndex = -1;

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "cselect-trigger";
    const label = document.createElement("span");
    label.className = "cselect-label";
    const caret = document.createElement("span");
    caret.className = "cselect-caret";
    caret.setAttribute("aria-hidden", "true");
    trigger.appendChild(label);
    trigger.appendChild(caret);
    wrap.appendChild(trigger);

    const list = document.createElement("div");
    list.className = "cselect-list";
    wrap.appendChild(list);

    function buildOptions() {
      list.innerHTML = "";
      Array.from(select.options).forEach((opt) => {
        const item = document.createElement("div");
        item.className = "cselect-option" + (opt.value === select.value ? " selected" : "");
        item.textContent = opt.textContent;
        item.dataset.value = opt.value;
        item.addEventListener("click", () => {
          if (select.value !== opt.value) {
            select.value = opt.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
          }
          closeList();
        });
        list.appendChild(item);
      });
    }

    function updateTrigger() {
      const opt = select.options[select.selectedIndex];
      label.textContent = opt ? opt.textContent : "";
      list.querySelectorAll(".cselect-option").forEach((o) => {
        o.classList.toggle("selected", o.dataset.value === select.value);
      });
    }

    function openList() {
      if (select.disabled) return;
      buildOptions();
      wrap.classList.add("open");
      document.addEventListener("click", onDocClick);
    }
    function closeList() {
      wrap.classList.remove("open");
      document.removeEventListener("click", onDocClick);
    }
    function onDocClick(e) {
      if (!wrap.contains(e.target)) closeList();
    }

    trigger.addEventListener("click", () => {
      wrap.classList.contains("open") ? closeList() : openList();
    });
    trigger.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeList();
    });

    select.addEventListener("change", updateTrigger);

    buildOptions();
    updateTrigger();

    // Keep in sync if options are rebuilt dynamically (e.g. drive folder list).
    const observer = new MutationObserver(() => {
      buildOptions();
      updateTrigger();
    });
    observer.observe(select, { childList: true });
  }

  function enhanceAll(root) {
    (root || document).querySelectorAll("select.styled-select").forEach(enhanceSelect);
  }

  document.addEventListener("DOMContentLoaded", () => enhanceAll());
  window.enhanceSelects = enhanceAll;
})();
