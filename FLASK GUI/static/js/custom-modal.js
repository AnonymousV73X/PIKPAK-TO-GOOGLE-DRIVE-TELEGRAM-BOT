/* Custom-styled alert/confirm modals to replace native window.alert/confirm,
   which can't be themed and look jarring against the rest of the UI. */
(function () {
  let overlay = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "cmodal-overlay";
    overlay.innerHTML = `
      <div class="cmodal" role="dialog" aria-modal="true">
        <div class="cmodal-icon" id="cmodalIcon"></div>
        <div class="cmodal-title" id="cmodalTitle"></div>
        <div class="cmodal-message" id="cmodalMessage"></div>
        <div class="cmodal-actions" id="cmodalActions"></div>
      </div>`;
    document.body.appendChild(overlay);
    return overlay;
  }

  function icon(kind) {
    if (kind === "danger") return "&#9888;";
    if (kind === "success") return "&#10003;";
    return "&#8505;";
  }

  function show({ title, message, kind = "info", buttons }) {
    const ov = ensureOverlay();
    ov.querySelector("#cmodalIcon").innerHTML = icon(kind);
    ov.querySelector("#cmodalIcon").className = "cmodal-icon cmodal-icon-" + kind;
    ov.querySelector("#cmodalTitle").textContent = title || "";
    ov.querySelector("#cmodalMessage").textContent = message || "";
    const actions = ov.querySelector("#cmodalActions");
    actions.innerHTML = "";

    return new Promise((resolve) => {
      buttons.forEach((b) => {
        const btn = document.createElement("button");
        btn.className = "btn " + (b.primary ? (b.danger ? "btn-danger" : "btn-primary") : "");
        btn.textContent = b.label;
        btn.addEventListener("click", () => {
          close();
          resolve(b.value);
        });
        actions.appendChild(btn);
      });
      requestAnimationFrame(() => ov.classList.add("open"));

      function onKey(e) {
        if (e.key === "Escape") {
          close();
          resolve(false);
        }
      }
      document.addEventListener("keydown", onKey, { once: true });

      function close() {
        ov.classList.remove("open");
      }
    });
  }

  window.customAlert = function (message, title = "Notice") {
    return show({
      title,
      message,
      kind: "info",
      buttons: [{ label: "OK", value: true, primary: true }],
    });
  };

  window.customConfirm = function (message, title = "Are you sure?", opts = {}) {
    return show({
      title,
      message,
      kind: opts.danger ? "danger" : "info",
      buttons: [
        { label: opts.cancelLabel || "Cancel", value: false },
        { label: opts.confirmLabel || "Confirm", value: true, primary: true, danger: opts.danger },
      ],
    });
  };
})();
