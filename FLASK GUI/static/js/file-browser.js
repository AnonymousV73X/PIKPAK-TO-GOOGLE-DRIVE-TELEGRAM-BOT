/* Generic file/folder browser modal.
   Modes:
   - "select"  : checkboxes on every row, used to pick exact files/folders to transfer
                 (source = PikPak). Confirms with the list of chosen relative paths.
   - "view"    : read-only browsing of source or destination storage, no picking.
   - "pickdir" : local filesystem folder picker (used to set the local-storage
                 destination path). Only directories are shown/navigable.
   Backed by /api/browse/source, /api/browse/dest, /api/browse/fs.
*/
(function () {
  let overlay = null;
  let state = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "cmodal-overlay fb-overlay";
    overlay.innerHTML = `
      <div class="fb-modal" role="dialog" aria-modal="true">
        <div class="fb-header">
          <div class="fb-title" id="fbTitle">Browse</div>
          <button class="fb-close" id="fbClose" aria-label="Close">&times;</button>
        </div>
        <div class="fb-breadcrumbs" id="fbCrumbs"></div>
        <div class="fb-list" id="fbList"><div class="fb-loading">Loading…</div></div>
        <div class="fb-footer">
          <div class="fb-selected-count" id="fbSelCount"></div>
          <div class="fb-footer-actions">
            <button class="btn" id="fbCancel">Cancel</button>
            <button class="btn btn-primary" id="fbConfirm">Confirm</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector("#fbClose").addEventListener("click", () => close(null));
    overlay.querySelector("#fbCancel").addEventListener("click", () => close(null));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(null);
    });
    return overlay;
  }

  function close(result) {
    overlay.classList.remove("open");
    if (state && state.resolve) state.resolve(result);
    state = null;
  }

  function fmtSize(n) {
    if (!n && n !== 0) return "";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i++;
    }
    return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
  }

  async function fetchListing(path) {
    if (state.mode === "pickdir") {
      const res = await fetch(`/api/browse/fs?path=${encodeURIComponent(path || "")}`);
      const data = await res.json();
      if (data.error) return { error: data.error };
      return {
        currentPath: data.path,
        parent: data.parent,
        items: (data.items || []).map((i) => ({ name: i.name, path: i.path, isDir: true })),
      };
    }
    const endpoint = state.remote === "source" ? "/api/browse/source" : "/api/browse/dest";
    const res = await fetch(`${endpoint}?path=${encodeURIComponent(path || "")}`);
    const data = await res.json();
    if (data.error) return { error: data.error };
    const items = (data.items || []).map((i) => ({
      name: i.Name,
      path: i.Path,
      isDir: !!i.IsDir,
      size: i.Size,
    }));
    items.sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1));
    return { currentPath: path || "", items };
  }

  function renderCrumbs(path) {
    const crumbs = overlay.querySelector("#fbCrumbs");
    const parts = (path || "").split("/").filter(Boolean);
    let acc = "";
    let html = `<span class="fb-crumb" data-path="">root</span>`;
    parts.forEach((p) => {
      acc += (acc ? "/" : "") + p;
      html += ` <span class="fb-crumb-sep">/</span> <span class="fb-crumb" data-path="${acc.replace(/"/g, "&quot;")}">${escapeHtml(p)}</span>`;
    });
    crumbs.innerHTML = html;
    crumbs.querySelectorAll(".fb-crumb").forEach((el) => {
      el.addEventListener("click", () => navigate(el.dataset.path));
    });
  }

  function updateSelCount() {
    const el = overlay.querySelector("#fbSelCount");
    if (state.mode !== "select") {
      el.textContent = "";
      return;
    }
    const n = state.selected.size;
    el.textContent = n === 0 ? "No files/folders selected — will default to all videos" : `${n} item(s) selected`;
  }

  async function navigate(path) {
    state.path = path || "";
    const list = overlay.querySelector("#fbList");
    list.innerHTML = '<div class="fb-loading">Loading…</div>';
    const data = await fetchListing(state.path);
    if (data.error) {
      list.innerHTML = `<div class="fb-error">Could not load: ${escapeHtml(data.error)}</div>`;
      return;
    }
    renderCrumbs(state.mode === "pickdir" ? data.currentPath : state.path);
    if (state.mode === "pickdir") state.currentFsPath = data.currentPath;

    if (!data.items.length) {
      list.innerHTML = '<div class="fb-empty">Empty folder.</div>';
    } else {
      list.innerHTML = "";
      data.items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "fb-row" + (item.isDir ? " fb-row-dir" : "");
        const checked = state.mode === "select" && state.selected.has(item.path);

        row.innerHTML = `
          ${state.mode === "select" ? `<input type="checkbox" class="fb-checkbox" ${checked ? "checked" : ""}>` : ""}
          <span class="fb-row-icon">${item.isDir ? "📁" : "🎬"}</span>
          <span class="fb-row-name">${escapeHtml(item.name)}</span>
          <span class="fb-row-size">${item.isDir ? "" : fmtSize(item.size)}</span>
        `;

        if (state.mode === "select") {
          const cb = row.querySelector(".fb-checkbox");
          cb.addEventListener("click", (e) => {
            e.stopPropagation();
            if (cb.checked) state.selected.add(item.path);
            else state.selected.delete(item.path);
            updateSelCount();
          });
        }

        row.addEventListener("click", (e) => {
          if (e.target.classList.contains("fb-checkbox")) return;
          if (item.isDir) {
            navigate(item.path);
          } else if (state.mode === "select") {
            const cb = row.querySelector(".fb-checkbox");
            if (cb) {
              cb.checked = !cb.checked;
              cb.dispatchEvent(new Event("click", { bubbles: false }));
            }
          }
        });

        list.appendChild(row);
      });
    }
    updateSelCount();
  }

  window.openFileBrowser = function (opts) {
    ensureOverlay();
    state = {
      mode: opts.mode || "view",
      remote: opts.remote || "source",
      path: "",
      selected: new Set(opts.initialSelected || []),
      resolve: null,
      currentFsPath: opts.startPath || "",
    };
    overlay.querySelector("#fbTitle").textContent = opts.title || "Browse";
    const confirmBtn = overlay.querySelector("#fbConfirm");
    confirmBtn.style.display = state.mode === "view" ? "none" : "inline-flex";
    confirmBtn.textContent = state.mode === "pickdir" ? "Use this folder" : "Confirm selection";
    confirmBtn.onclick = () => {
      if (state.mode === "pickdir") {
        close({ path: state.currentFsPath });
      } else {
        close({ selected: Array.from(state.selected) });
      }
    };
    overlay.classList.add("open");
    navigate(opts.startPath || "");
    return new Promise((resolve) => {
      state.resolve = resolve;
    });
  };
})();
