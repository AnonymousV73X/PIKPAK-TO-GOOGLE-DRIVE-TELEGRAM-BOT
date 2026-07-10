(function () {
  let current = 1;
  const total = 5;
  const panels = document.querySelectorAll(".step-panel");
  const dots = document.querySelectorAll(".wizard-step-dot");
  const backBtn = document.getElementById("backBtn");
  const nextBtn = document.getElementById("nextBtn");

  // Step 1 is purely informational, so it's already satisfied.
  const stepDone = { 1: true, 2: false, 3: false, 4: false, 5: false };

  function destStatusText(ok, dest) {
    if (ok)
      return dest === "gdrive"
        ? "✓ Google Drive config looks complete"
        : dest === "webdav"
          ? "✓ WebDAV details look complete"
          : "✓ Local folder chosen";
    return "Fill in the fields above to continue";
  }

  function checkStep3() {
    const val = document.getElementById("pikpakConfig").value.trim();
    const ok = /\[PIKKY\]/i.test(val) && val.length > 10;
    stepDone[3] = ok;
    const statusEl = document.getElementById("pikpakStatus");
    if (statusEl) {
      statusEl.className =
        "status-line " +
        (val.length === 0 ? "" : ok ? "status-ok" : "status-fail");
      statusEl.textContent =
        val.length === 0
          ? ""
          : ok
            ? "✓ Config block looks valid"
            : "✗ This doesn't look like a [PIKKY] block — paste the exact section from rclone.conf";
    }
    render();
  }

  function checkStep4() {
    const dest = document.querySelector('input[name="dest"]:checked').value;
    let ok = false;
    if (dest === "gdrive") {
      ok = document.getElementById("gdriveConfig").value.trim().length > 10;
    } else if (dest === "webdav") {
      ok =
        document.getElementById("webdavUrl").value.trim().length > 0 &&
        document.getElementById("webdavUser").value.trim().length > 0 &&
        document.getElementById("webdavPass").value.trim().length > 0;
    } else {
      ok = document.getElementById("localPath").value.trim().length > 0;
    }
    stepDone[4] = ok;
    const statusEl = document.getElementById("destStatus");
    if (statusEl) {
      statusEl.className =
        "status-line " + (ok ? "status-ok" : "status-pending");
      statusEl.textContent = destStatusText(ok, dest);
    }
    render();
  }

  function render() {
    panels.forEach((p) =>
      p.classList.toggle("active", Number(p.dataset.step) === current),
    );
    dots.forEach((d) => {
      const n = Number(d.dataset.dot);
      d.classList.toggle("done", !!stepDone[n]);
      d.classList.toggle("current", n === current && !stepDone[n]);
    });
    backBtn.style.visibility = current === 1 ? "hidden" : "visible";
    nextBtn.textContent = current === total ? "Finish" : "Continue";
    nextBtn.disabled = !stepDone[current];
  }

  backBtn.addEventListener("click", () => {
    if (current > 1) {
      current--;
      render();
    }
  });

  nextBtn.addEventListener("click", async () => {
    if (!stepDone[current]) return;
    if (current === total) {
      await finishSetup();
      return;
    }
    current++;
    render();
  });

  // Suggest the next profile name (default -> alpha -> bravo -> ...) so adding
  // a second/third PikPak account to dodge its transfer limit is a one-click flow.
  (async () => {
    try {
      const res = await fetch("/api/profile/next_name");
      const data = await res.json();
      const nameInput = document.getElementById("profileName");
      if (data.name && nameInput) {
        nameInput.value = data.name;
        nameInput.placeholder = data.name;
      }
    } catch (e) { /* keep default */ }
  })();

  document.getElementById("pikpakConfig").addEventListener("input", checkStep3);
  document.getElementById("gdriveConfig").addEventListener("input", checkStep4);
  document.getElementById("webdavUrl").addEventListener("input", checkStep4);
  document.getElementById("webdavUser").addEventListener("input", checkStep4);
  document.getElementById("webdavPass").addEventListener("input", checkStep4);

  // Click-to-copy chips
  document.querySelectorAll(".code-chip[data-copy]").forEach((chip) => {
    chip.addEventListener("click", async () => {
      const text = chip.dataset.copy;
      try {
        await navigator.clipboard.writeText(text);
      } catch (e) {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      chip.classList.add("copied");
      const icon = chip.querySelector(".copy-ico");
      const prevIcon = icon ? icon.textContent : "";
      if (icon) icon.textContent = "✓";
      setTimeout(() => {
        chip.classList.remove("copied");
        if (icon) icon.textContent = prevIcon;
      }, 1200);
    });
  });

  // Destination toggle
  document.querySelectorAll(".option-card[data-dest]").forEach((card) => {
    card.addEventListener("click", () => {
      document
        .querySelectorAll(".option-card[data-dest]")
        .forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      card.querySelector("input").checked = true;
      const dest = card.dataset.dest;
      document.getElementById("gdriveFields").style.display =
        dest === "gdrive" ? "block" : "none";
      document.getElementById("webdavFields").style.display =
        dest === "webdav" ? "block" : "none";
      document.getElementById("localFields").style.display =
        dest === "local" ? "block" : "none";
      checkStep4();
    });
  });

  const chooseLocalFolderBtn = document.getElementById("chooseLocalFolderBtn");
  if (chooseLocalFolderBtn) {
    chooseLocalFolderBtn.addEventListener("click", async () => {
      const result = await window.openFileBrowser({
        mode: "pickdir",
        title: "Choose a local destination folder",
      });
      if (result && result.path) {
        document.getElementById("localPath").value = result.path;
        document.getElementById("localPathDisplay").textContent = result.path;
        checkStep4();
      }
    });
  }

  // Install rclone
  const installBtn = document.getElementById("installBtn");
  const installLog = document.getElementById("installLog");
  const installStatus = document.getElementById("installStatus");
  if (installBtn) {
    installBtn.addEventListener("click", async () => {
      installBtn.disabled = true;
      installLog.style.display = "block";
      installLog.textContent = "Installing…";
      installStatus.className = "status-line status-pending";
      installStatus.textContent = "Working…";
      try {
        const res = await fetch("/api/rclone/install", { method: "POST" });
        const data = await res.json();
        installLog.textContent = (data.logs || []).join("\n");
        if (data.ok) {
          installStatus.className = "status-line status-ok";
          installStatus.textContent = "✓ rclone is ready";
          stepDone[2] = true;
          render();
        } else {
          installStatus.className = "status-line status-fail";
          installStatus.textContent =
            "✗ Install failed — check your network settings and try again";
          installBtn.disabled = false;
        }
      } catch (e) {
        installStatus.className = "status-line status-fail";
        installStatus.textContent =
          "✗ Install failed — check your network settings and try again";
        installBtn.disabled = false;
      }
    });
  }

  function buildConfigText() {
    const pikpak = document.getElementById("pikpakConfig").value.trim();
    const dest = document.querySelector('input[name="dest"]:checked').value;
    let destConfig = "";
    if (dest === "gdrive") {
      destConfig = document.getElementById("gdriveConfig").value.trim();
    } else if (dest === "webdav") {
      const url = document.getElementById("webdavUrl").value.trim();
      const user = document.getElementById("webdavUser").value.trim();
      const pass = document.getElementById("webdavPass").value.trim();
      destConfig = `[WEBDAV]\ntype = webdav\nurl = ${url}\nvendor = other\nuser = ${user}\npass = ${pass}`;
    }
    // local storage has no rclone remote — nothing to append
    const config = destConfig ? `${pikpak}\n\n${destConfig}\n` : `${pikpak}\n`;
    return { config, dest };
  }

  const verifyBtn = document.getElementById("verifyBtn");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", async () => {
      verifyBtn.disabled = true;
      const resultsEl = document.getElementById("verifyResults");
      resultsEl.innerHTML =
        '<div class="status-line status-pending">Testing connections…</div>';
      const { config, dest } = buildConfigText();
      const name =
        document.getElementById("profileName").value.trim() || "default";
      try {
        const res = await fetch("/api/profile/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            rclone_config: config,
            destination: dest,
            local_destination_path: document.getElementById("localPath").value.trim(),
          }),
        });
        const data = await res.json();
        resultsEl.innerHTML = Object.entries(data)
          .map(
            ([remote, r]) =>
              `<div class="status-line ${r.ok ? "status-ok" : "status-fail"}">${r.ok ? "✓" : "✗"} ${remote}${r.error ? ": " + escapeHtml(r.error) : ""}</div>`,
          )
          .join("");
        stepDone[5] = Object.values(data).every((r) => r.ok);
        render();
      } catch (e) {
        resultsEl.innerHTML =
          '<div class="status-line status-fail">✗ Could not reach the server</div>';
        stepDone[5] = false;
        render();
      } finally {
        verifyBtn.disabled = false;
      }
    });
  }

  async function finishSetup() {
    nextBtn.disabled = true;
    const { config, dest } = buildConfigText();
    const name =
      document.getElementById("profileName").value.trim() || "default";
    const webdavUrl = document.getElementById("webdavUrl").value.trim();
    const webdavUser = document.getElementById("webdavUser").value.trim();
    const webdavPass = document.getElementById("webdavPass").value.trim();
    const localPath = document.getElementById("localPath").value.trim();
    try {
      await fetch("/api/profile/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          rclone_config: config,
          default_destination: dest,
          webdav_url: webdavUrl,
          webdav_user: webdavUser,
          webdav_pass: webdavPass,
          local_destination_path: localPath,
        }),
      });
      window.location.href = "/";
    } catch (e) {
      nextBtn.disabled = false;
    }
  }

  render();
})();
