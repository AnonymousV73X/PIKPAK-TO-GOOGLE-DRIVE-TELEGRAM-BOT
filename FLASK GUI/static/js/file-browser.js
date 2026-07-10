/* Generic file/folder browser modal.
   Modes:
   - "select"  : checkboxes on every row, used to pick exact files/folders to transfer
                 (source = PikPak). Confirms with the list of chosen relative paths.
   - "view"    : read-only browsing of source or destination storage, no picking.
   - "pickdir" : local filesystem folder picker (used to set the local-storage
                 destination path). Only directories are shown/navigable.
   Backed by /api/browse/source, /api/browse/dest, /api/browse/fs.

   Performance:
   - All listings are cached client-side (Map keyed by endpoint+path).
   - On revisit the cached result renders instantly; a background refresh runs
     silently and patches in any new items without losing scroll position or
     checkbox state. A tiny "↻ Refreshed" badge appears if anything changed.
   - Cache is scoped to the current openFileBrowser() call (cleared on close).
*/
(function () {
  let overlay = null;
  let state = null;

  // ── Per-session directory cache ─────────────────────────────────────────────
  // key: `${endpoint}::${path}` → { items: [...], ts: Date.now() }
  const dirCache = new Map();
  const STALE_MS = 60_000; // background-refresh after 60 s

  function cacheKey(path) {
    const ep = state.mode === "pickdir"
      ? "fs"
      : state.remote === "source" ? "source" : "dest";
    return `${ep}::${path || ""}`;
  }

  // ── Overlay DOM ─────────────────────────────────────────────────────────────
  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "cmodal-overlay fb-overlay";
    overlay.innerHTML = `
      <div class="fb-modal" role="dialog" aria-modal="true">
        <div class="fb-header">
          <div class="fb-title" id="fbTitle">Browse</div>
          <div class="fb-header-right">
            <span class="fb-stale-badge" id="fbStaleBadge" title="Refreshed in background"></span>
            <button class="fb-close" id="fbClose" aria-label="Close">&times;</button>
          </div>
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
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(null); });
    return overlay;
  }

  function close(result) {
    overlay.classList.remove("open");
    dirCache.clear();
    if (state && state.resolve) state.resolve(result);
    state = null;
  }

  // ── Utilities ────────────────────────────────────────────────────────────────
  function fmtSize(n) {
    if (!n && n !== 0) return "";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
  }

  // ── Fetch (with cache) ───────────────────────────────────────────────────────
  async function fetchListing(path, { skipCache = false } = {}) {
    const key = cacheKey(path);
    if (!skipCache && dirCache.has(key)) {
      return { ...dirCache.get(key), fromCache: true };
    }

    let data;
    if (state.mode === "pickdir") {
      const res = await fetch(`/api/browse/fs?path=${encodeURIComponent(path || "")}`);
      data = await res.json();
      if (data.error) return { error: data.error };
      data = {
        currentPath: data.path,
        parent: data.parent,
        items: (data.items || []).map((i) => ({ name: i.name, path: i.path, isDir: true })),
      };
    } else {
      const endpoint = state.remote === "source" ? "/api/browse/source" : "/api/browse/dest";
      const res = await fetch(`${endpoint}?path=${encodeURIComponent(path || "")}`);
      data = await res.json();
      if (data.error) return { error: data.error };
      const items = (data.items || []).map((i) => ({
        name: i.Name, path: i.Path, isDir: !!i.IsDir, size: i.Size,
      }));
      items.sort((a, b) => a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1);
      data = { currentPath: path || "", items };
    }

    dirCache.set(key, { ...data, ts: Date.now() });
    return data;
  }

  // ── Breadcrumbs ──────────────────────────────────────────────────────────────
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

  // ── Selection counter ────────────────────────────────────────────────────────
  function updateSelCount() {
    const el = overlay.querySelector("#fbSelCount");
    if (state.mode !== "select") { el.textContent = ""; return; }
    const n = state.selected.size;
    el.textContent = n === 0
      ? "No files/folders selected — will default to all videos"
      : `${n} item(s) selected`;
  }

  // ── Build a single row element ───────────────────────────────────────────────
  function buildRow(item) {
    const row = document.createElement("div");
    row.className = "fb-row" + (item.isDir ? " fb-row-dir" : "");
    row.dataset.path = item.path;

    const checked = state.mode === "select" && state.selected.has(item.path);

    if (state.mode === "select") {
      // Custom styled checkbox
      const label = document.createElement("label");
      label.className = "fb-cb-wrap";
      label.innerHTML = `
        <input type="checkbox" class="fb-checkbox-native"${checked ? " checked" : ""}>
        <span class="fb-cb-box">
          <svg class="fb-cb-check" viewBox="0 0 12 9" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M1 4L4.5 7.5L11 1" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>`;
      const nativeCb = label.querySelector(".fb-checkbox-native");
      nativeCb.addEventListener("click", (e) => {
        e.stopPropagation();
        nativeCb.checked ? state.selected.add(item.path) : state.selected.delete(item.path);
        updateSelCount();
      });
      row.appendChild(label);
    }

    const icon = document.createElement("span");
    icon.className = "fb-row-icon";
    icon.textContent = item.isDir ? "📁" : "🎬";

    const name = document.createElement("span");
    name.className = "fb-row-name";
    name.textContent = item.name;

    const size = document.createElement("span");
    size.className = "fb-row-size";
    size.textContent = item.isDir ? "" : fmtSize(item.size);

    row.append(icon, name, size);

    row.addEventListener("click", (e) => {
      if (e.target.closest(".fb-cb-wrap")) return;
      if (item.isDir) {
        navigate(item.path);
      } else if (state.mode === "select") {
        const cb = row.querySelector(".fb-checkbox-native");
        if (cb) {
          cb.checked = !cb.checked;
          cb.checked ? state.selected.add(item.path) : state.selected.delete(item.path);
          updateSelCount();
        }
      }
    });

    return row;
  }

  // ── Render listing (with stale-while-revalidate) ─────────────────────────────
  async function navigate(path) {
    state.path = path || "";
    const list = overlay.querySelector("#fbList");
    const badge = overlay.querySelector("#fbStaleBadge");
    badge.textContent = "";

    const key = cacheKey(state.path);
    const cached = dirCache.get(key);

    // ── Instant render from cache ──
    if (cached) {
      renderCrumbs(state.mode === "pickdir" ? cached.currentPath : state.path);
      if (state.mode === "pickdir") state.currentFsPath = cached.currentPath;
      renderItems(list, cached.items);
      updateSelCount();

      // Background refresh if stale
      const age = Date.now() - (cached.ts || 0);
      if (age > STALE_MS) {
        fetchListing(state.path, { skipCache: true }).then((fresh) => {
          if (!fresh || fresh.error || state?.path !== path) return;
          const oldPaths = new Set(cached.items.map((i) => i.path));
          const newItems = fresh.items.filter((i) => !oldPaths.has(i.path));
          if (newItems.length) {
            // Append new items without re-rendering the whole list
            newItems.forEach((item) => list.appendChild(buildRow(item)));
            badge.textContent = `↻ +${newItems.length} new`;
            setTimeout(() => { if (badge) badge.textContent = ""; }, 3000);
          } else {
            badge.textContent = "↻";
            setTimeout(() => { if (badge) badge.textContent = ""; }, 1500);
          }
        });
      }
      return;
    }

    // ── First load — show spinner ──
    list.innerHTML = '<div class="fb-loading"><span class="fb-spinner"></span> Loading…</div>';
    const data = await fetchListing(state.path);
    if (data.error) {
      list.innerHTML = `<div class="fb-error">Could not load: ${escapeHtml(data.error)}</div>`;
      return;
    }
    renderCrumbs(state.mode === "pickdir" ? data.currentPath : state.path);
    if (state.mode === "pickdir") state.currentFsPath = data.currentPath;
    renderItems(list, data.items);
    updateSelCount();
  }

  function renderItems(list, items) {
    if (!items.length) {
      list.innerHTML = '<div class="fb-empty">Empty folder.</div>';
      return;
    }
    list.innerHTML = "";
    items.forEach((item) => list.appendChild(buildRow(item)));
  }

  // ── Public API ───────────────────────────────────────────────────────────────
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
    return new Promise((resolve) => { state.resolve = resolve; });
  };
})();
