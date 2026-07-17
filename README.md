# PikPak to Google Drive Telegram Bot OR Web GUI ...

![Relay Dashboard](FLASK%20GUI/screenshots/dashboard.png)

> **Relay** — a self-hosted control panel that moves video files from your
> PikPak account to Google Drive (or any WebDAV-compatible cloud) using
> `rclone` under the hood. Originally a Telegram bot, now also ships with a
> full browser-based dashboard so you can drive transfers without touching
> a terminal.

The repo is organized into two main folders:

| Folder                 | What it is                                                              |
| ---------------------- | ----------------------------------------------------------------------- |
| `FLASK GUI/`           | The web GUI ("Relay"). Flask app + SQLite + rclone.    |
| `BOT/`                 | The original Telegram-bot implementation (`reference_pikky_original.py`). |

## How to launch the BOT
Navigate into the `BOT/` directory and run:
`python reference_pikky_original.py`
Make sure to add your Telegram Bot Token in the script before running.

## How to launch the FLASK GUI
Navigate into the `FLASK GUI/` directory, install requirements, and run:
`python run.py`
This README below contains more extensive documentation for the web GUI.

---

## Table of contents

1. [What it does](#what-it-does)
2. [How it works](#how-it-works)
3. [Repo layout](#repo-layout)
4. [Quick start — local machine](#quick-start--local-machine)
5. [Quick start — Google Colab](#quick-start--google-colab)
6. [The Cloudflare tunnel (Colab mode)](#the-cloudflare-tunnel-colab-mode)
7. [First-time setup (the wizard)](#first-time-setup-the-wizard)
8. [Using the dashboard](#using-the-dashboard)
9. [Profiles & PikPak transfer limits](#profiles--pikpak-transfer-limits)
10. [Configuration reference](#configuration-reference)
11. [Troubleshooting](#troubleshooting)
12. [Security notes](#security-notes)
13. [Migrating from the old Telegram bot](#migrating-from-the-old-telegram-bot)
14. [License](#license)

---

## What it does

- **Pulls video files out of PikPak** and syncs them to Google Drive (or a
  WebDAV server) using `rclone sync`.
- **Runs entirely on your machine** (or in your own Colab session) — Relay
  itself never sees your files or your credentials. They live in a local
  SQLite DB + a local `rclone.conf`.
- **Auto-installs `rclone`** the first time you set up a profile — no need
  to `apt install` or `brew install` anything.
- **Auto-installs `cloudflared`** when running in Google Colab, so the
  dashboard is reachable from your laptop's browser via a temporary
  `https://<random>.trycloudflare.com` URL.
- **Multiple PikPak accounts** as separate profiles — handy for working
  around PikPak's per-account transfer caps.
- **Live transfer log** with upload / download speed, elapsed time, and
  per-file progress.
- **Storage tools**: one-click "clear everything from this PikPak account"
  and "delete a specific folder on the drive".
- **Dark / light theme** with a custom-styled UI (including scrollbar
  styling that matches the cyan/teal accent).

## How it works

```
                       ┌────────────────────────────────────────┐
                       │              Relay (this app)          │
                       │                                        │
   Browser  ─── HTTPS ─▶  Flask  ─── subprocess ──▶  rclone    │
                       │                                        │
                       │  SQLite (~/.pikky_web/pikky.db)        │
                       │  rclone configs (~/.pikky_web/rclone/) │
                       │  rclone + cloudflared binaries         │
                       │  (~/.pikky_web/bin/)                   │
                       └────────────────────────────────────────┘
                                          │
                                          ▼
                                PikPak  ←──→  Google Drive / WebDAV
```

`rclone` does all the actual file moving — Relay is just a friendly layer
on top. Your PikPak password and Google OAuth token live in
`~/.pikky_web/rclone/<profile>.conf` and never leave the machine Relay is
running on.

In Colab, a `cloudflared` quick tunnel bridges the gap between Colab's
firewalled VM and your browser. See
[The Cloudflare tunnel (Colab mode)](#the-cloudflare-tunnel-colab-mode)
for the details.

---

## Repo layout

```
PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT/
├── README.md                        ← you are here
├── pikky-web/                       ← the web GUI
│   ├── app.py                       ← Flask routes / API
│   ├── core.py                      ← rclone wrapper, DB, transfer engine
│   ├── run.py                       ← unified launcher (local + Colab)
│   ├── cloudflare_tunnel.py         ← cloudflared quick-tunnel integration
│   ├── requirements.txt
│   ├── reference_pikky_original.py  ← legacy Telegram-bot code (kept for reference)
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/
│   │       ├── app.js               ← dashboard interactivity
│   │       ├── wizard.js            ← 5-step setup wizard
│   │       └── custom-select.js     ← themed <select> replacement
│   └── templates/
│       ├── base.html
│       ├── index.html               ← dashboard
│       ├── wizard.html              ← setup wizard
│       └── help.html
└── (any future modules — bot, CLI, etc.)
```

---

## Quick start — local machine

> Works on **Windows, macOS, and Linux**. Python 3.9+ required.

### Option A — clone with git (recommended)

```bash
git clone https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT.git
cd PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT/pikky-web

# Create a virtual env so we don't pollute system Python
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

python run.py
```

You'll see:

```
============================================================
  Relay — PikPak → Google Drive / WebDAV
  Environment : Local
  Bind        : http://127.0.0.1:5000
  Tunnel      : off
============================================================
```

Open <http://127.0.0.1:5000/> in your browser and follow the
[setup wizard](#first-time-setup-the-wizard).

### Option B — download the ZIP

1. Go to <https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT>
2. Click the green **Code** button → **Download ZIP**
3. Unzip it, then `cd` into `PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT-main/pikky-web`
4. Follow the same `python -m venv` / `pip install` / `python run.py` steps
   as Option A.

### Option C — one-liner (curl + unzip + run)

```bash
curl -L https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT/archive/refs/heads/main.zip -o relay.zip \
  && unzip -q relay.zip \
  && cd PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT-main/pikky-web \
  && python -m venv .venv && source .venv/bin/activate \
  && pip install -r requirements.txt \
  && python run.py
```

---

## Quick start — Google Colab

Colab gives you a free Linux VM with Python and a browser-based notebook.
It's perfect for running Relay when you don't want to keep your laptop on
for a long transfer.

### Step-by-step

1. Open <https://colab.research.google.com> and create a **New notebook**.

2. Paste the following into the first cell and run it
   (`Shift` + `Enter`):

   ```python
   !git clone https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT.git
   %cd PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT/pikky-web
   !pip install -r requirements.txt
   ```

3. In a **second cell**, start the app:

   ```python
   !python run.py
   ```

   After a few seconds you'll see something like this in the cell output:

   ```
   ============================================================
     Relay — PikPak → Google Drive / WebDAV
     Environment : Google Colab
     Bind        : http://0.0.0.0:5000
     Tunnel      : on (cloudflared quick tunnel)
   ============================================================
   Downloading cloudflared 2024.12.2 for linux/amd64...
   cloudflared installed: cloudflared version 2024.12.2 ...
   Starting Cloudflare quick tunnel → http://localhost:5000 ...

   ============================================================
     Public URL (share this with whoever needs the dashboard):
       https://some-random-words.trycloudflare.com
   ============================================================
   ```

4. Click that `https://...trycloudflare.com` link to open the dashboard.
   The first time, you'll be sent to the
   [setup wizard](#first-time-setup-the-wizard).

> **Important:** keep the second cell running. The tunnel stays up only as
> long as the Python process is alive — stop the cell / disconnect the
> kernel and the public URL dies.

### Why the tunnel?

Colab VMs sit behind Google's firewall. Their `127.0.0.1` is unreachable
from the outside world. Tools like `ngrok` work, but require an account.
Cloudflare's **quick tunnel** hands you a free, no-account, ephemeral HTTPS
URL that proxies back to your Colab VM. It's perfect for a personal control
panel.

See [The Cloudflare tunnel (Colab mode)](#the-cloudflare-tunnel-colab-mode)
for the full story.

---

## The Cloudflare tunnel (Colab mode)

`cloudflare_tunnel.py` does four things:

1. **Detects Colab** by checking for `google.colab` (and a couple of env
   vars as a fallback).
2. **Downloads the right `cloudflared` binary** for the host OS+arch into
   `~/.pikky_web/bin/` (next to `rclone`). It pins to a specific
   release so the download URL is reproducible.
3. **Starts a quick tunnel** with `cloudflared tunnel --no-autoupdate
   --url http://localhost:<port>` — no Cloudflare account, no DNS, no
   config file.
4. **Scans the tunnel's stderr** for the first
   `https://<random>.trycloudflare.com` URL and prints it.

The tunnel subprocess is a child of the Python process running Relay, so
it dies automatically when you stop the Colab cell. There's nothing to
clean up.

### Forcing the tunnel on / off

Two env vars override the auto-detection:

| Var             | Default           | Effect                                                  |
| --------------- | ----------------- | ------------------------------------------------------- |
| `RELAY_TUNNEL`  | `1` in Colab, else `0` | `1` forces the tunnel on (even on your laptop). `0` forces it off (even in Colab). |
| `RELAY_HOST`    | `0.0.0.0` if tunnel, else `127.0.0.1` | Interface to bind Flask to. |
| `RELAY_PORT`    | `5000`            | Port to bind Flask to.                                  |

Example — share your local Relay with a friend for an hour:

```bash
RELAY_TUNNEL=1 python run.py
```

Example — run in Colab but **without** the tunnel (e.g. you'll drive it
from `curl` in another cell):

```python
%env RELAY_TUNNEL=0
!python run.py
```

### Security implications

- The `trycloudflare.com` URL is unguessable but **unauthenticated**.
  Anyone you share it with can use the dashboard.
- For a personal transfer this is fine — the URL dies when you stop the
  cell. Don't post it in public chat rooms.
- All traffic between your browser and Cloudflare, and between Cloudflare
  and Colab, is HTTPS. The hop from Cloudflare's edge to Colab's VM is
  the only "plaintext" segment, and it's inside Google's network.
- Your PikPak / Google Drive credentials never traverse the tunnel —
  they're read from disk by `rclone`, which runs locally on the Colab VM.

---

## First-time setup (the wizard)

The first time you open the dashboard you'll be sent to `/wizard`. It's a
five-step flow:

| Step | What you do                                                        |
| ---- | ------------------------------------------------------------------ |
| 1    | Read a one-paragraph explainer of what `rclone` is.                |
| 2    | Click **Install rclone** — Relay downloads it for you.             |
| 3    | Run `rclone config` in any terminal, create a `PIKKY` remote, paste the resulting `[PIKKY]` block. |
| 4    | Choose **Google Drive** or **WebDAV** as the destination. For Drive, paste a `[GDRIVE]` block; for WebDAV, enter URL + user + pass. |
| 5    | Click **Test connection** to verify both remotes, then **Finish**. |

The wizard has click-to-copy "code chips" for every command you need to
run, so you don't have to retype anything. Step 7 of the PikPak block and
step 9 of the Google Drive block give you the exact path to
`rclone.conf` on Windows (CMD), Windows (PowerShell), and macOS/Linux.

> **Colab gotcha:** in step 2 of the wizard, "Install rclone" downloads
> the Linux rclone binary into `~/.pikky_web/bin/`. This works fine in
> Colab, but `rclone config` (steps 3 & 4) needs an **interactive TTY**
> to do the Google OAuth dance — which Colab cells don't have. The
> recommended Colab workflow is:
>
> 1. Run `rclone config` **once on your laptop**, with the same Google
>    account you'll use in Colab.
> 2. Copy the resulting `[PIKKY]` and `[GDRIVE]` blocks.
> 3. Paste them into the wizard running in Colab.
>
> PikPak doesn't need OAuth so you can also run `rclone config` inside a
> Colab cell with `!rclone config` if you've added `~/.pikky_web/bin` to
> `$PATH` — but the Google Drive OAuth flow really wants a real browser.

---

## Using the dashboard

Once a profile exists, `/` shows the dashboard:

- **Transfer relay** — visualises PikPak → Drive as an animated orbit.
  Pick the destination from the dropdown, hit **Start transfer**.
- **Live stats** — upload speed, download speed, elapsed time. Updates
  every 2 seconds.
- **PikPak storage** — total / used / free space, plus a count of video
  files found.
- **Drive storage** — same, for the destination.
- **Storage tools** — quick "delete everything from PikPak" (handy after
  a successful transfer) and "delete a specific drive folder" actions.
  Both ask for confirmation.
- **Live log** — full rclone output, colour-coded by level. The console
  auto-scrolls to the bottom.
- **Transfer history** — the last 20 transfers for this profile, with
  status / destination / file count / timestamps.

The **theme toggle** in the top-right remembers your choice across
sessions (stored in the SQLite DB).

---

## Profiles & PikPak transfer limits

PikPak caps how much a single account can pull down / transfer out per
day. Relay works around this by letting you add **multiple PikPak accounts
as separate profiles**. Each profile keeps its own:

- PikPak login (in its own rclone config file)
- Google Drive / WebDAV destination
- Transfer history
- Active transfer

Profiles are auto-named `default`, then `alpha`, `bravo`, `charlie`,
`delta`, `echo`, … (NATO phonetic alphabet) so they're easy to tell apart
at a glance. Switch between them from the **Active profile** dropdown at
the top of the dashboard.

To add another PikPak account: click **+ Add profile** (or visit `/wizard`
directly). The wizard will suggest the next NATO name automatically.

---

## Configuration reference

### Files Relay writes

| Path                                       | What                                              |
| ------------------------------------------ | ------------------------------------------------- |
| `~/.pikky_web/pikky.db`                    | SQLite DB — profiles, transfers, preferences.     |
| `~/.pikky_web/rclone/<profile>.conf`       | rclone config file per profile.                  |
| `~/.pikky_web/bin/rclone` (or `.exe`)      | rclone binary (auto-downloaded).                 |
| `~/.pikky_web/bin/cloudflared` (or `.exe`) | cloudflared binary (auto-downloaded, Colab only).|

### Environment variables

| Var              | Default                              | Purpose                              |
| ---------------- | ------------------------------------ | ------------------------------------ |
| `RELAY_HOST`     | `0.0.0.0` in Colab / tunnel mode, else `127.0.0.1` | Flask bind interface. |
| `RELAY_PORT`     | `5000`                               | Flask bind port.                     |
| `RELAY_TUNNEL`   | `1` in Colab, else `0`               | Force the Cloudflare tunnel on/off. |

### rclone transfer flags

Every transfer runs as an `rclone sync` with:

```
--transfers 4 --checkers 8 --fast-list --checksum
--drive-chunk-size 64M --buffer-size 32M
--filter "+ */"  --filter "+ *.mp4" --filter "+ *.mkv" ... --filter "- *"
```

Video extensions picked up: `mp4, mkv, avi, mov, wmv, flv, webm, mpg,
mpeg, m4v, 3gp`. Each run lands in a new
`<random-alien-name>-YYYY-MM-DD_HH-MM-SS` folder on the destination, so
nothing overwrites a previous transfer.

---

## Troubleshooting

### `rclone config` won't open a browser in Colab
Use a real laptop / desktop to run `rclone config` once, then paste the
resulting `[PIKKY]` / `[GDRIVE]` blocks into the wizard running in Colab.
See the **Colab gotcha** note in
[First-time setup](#first-time-setup-the-wizard).

### The Cloudflare tunnel URL never appears
Check the cell output — `cloudflared` writes its log there. Common
causes:

- Colab lost internet mid-download. Re-run the cell.
- The pinned `cloudflared` version is unavailable. Edit
  `CLOUDFLARED_VERSION` in `cloudflare_tunnel.py` to a newer release from
  <https://github.com/cloudflare/cloudflared/releases>.
- You're behind a corporate firewall that blocks Cloudflare's edge.
  There's no workaround other than running locally.

### "PIKKY remote failed" during a transfer
- The remote name must be exactly `PIKKY` (all caps). Same for `GDRIVE`
  and `WEBDAV`.
- The pasted config block must be complete — copy from the `[PIKKY]`
  line down to the next blank line.
- If you have multiple profiles, make sure the **Active profile**
  dropdown matches the PikPak account you actually want.

### "Transfer stalls" with no progress
Large libraries take time — rclone's `--fast-list` flag batches file
listings, so the first minute can look quiet. The live log updates every
5 seconds; if it really has hung, hit **Stop** and try again.

### Wrong destination shown
Switch it from the **Destination** dropdown on the dashboard **before**
clicking **Start transfer**. The dropdown persists per profile.

### Light theme scrollbars look off
Hard refresh the page (Ctrl+Shift+R / Cmd+Shift+R). The scrollbar styles
are in `static/css/style.css` and are cached aggressively by some
browsers.

### Port 5000 already in use (macOS)
macOS Monterey+ runs AirPlay Receiver on port 5000 by default. Either
disable it in *System Settings → General → AirDrop & Handoff*, or start
Relay on a different port:

```bash
RELAY_PORT=5050 python run.py
```

---

## Security notes

- **Your credentials never leave your machine.** PikPak password and
  Google OAuth token are stored in `~/.pikky_web/rclone/<profile>.conf`
  and read directly by `rclone`. Relay's Flask process sees them only
  long enough to write the file.
- **No Relay server exists.** This is a self-hosted app — there's no
  backend to leak your data. The only network calls are the ones `rclone`
  itself makes to PikPak / Google.
- **The Colab tunnel URL is unauthenticated.** Treat it like a temporary
  password: don't post it publicly. It dies when the cell stops.
- **SQLite DB permissions.** The DB at `~/.pikky_web/pikky.db` is
  world-readable by default on most Linux systems. If that bothers you,
  `chmod 700 ~/.pikky_web`.
- **Debug mode is off.** The original `app.py` ran Flask in debug mode;
  the new `run.py` and `app.py` both run with `debug=False` to avoid
  exposing the Werkzeug debugger.

---

## Migrating from the old Telegram bot

The legacy bot lives in `pikky-web/reference_pikky_original.py`. It's
preserved verbatim so you can:

1. **Read** how the bot structured its PikPak / Drive interactions.
2. **Copy** any custom config values (rclone flags, video extensions)
   into the new `core.py` if you'd tweaked them.
3. **Migrate profiles**: the bot stored config in `~/.pikky/` (singular).
   The web app stores it in `~/.pikky_web/` (with underscore). To
   migrate, copy your `rclone.conf` over:

   ```bash
   mkdir -p ~/.pikky_web/rclone
   cp ~/.pikky/rclone.conf ~/.pikky_web/rclone/default.conf
   ```

   Then create a profile named `default` via the wizard, pasting the
   `[PIKKY]` and `[GDRIVE]` blocks. The wizard's "Test connection" step
   will confirm everything still works.

4. **Run both** — nothing in the web app interferes with the bot. They
   use separate config dirs, separate DBs, and the bot doesn't bind any
   HTTP port.

---

## License

This project is released under the **MIT License**. See the repository
for details. `rclone` and `cloudflared` are licensed under their own
terms (MIT and Apache 2.0 respectively) — Relay simply downloads and
invokes them as separate processes.

---

### Acknowledgements

- [rclone](https://rclone.org/) — the actual engine that moves files.
- [cloudflared](https://github.com/cloudflare/cloudflared) — makes
  Colab-hosted apps reachable from the public internet for free.
- [Flask](https://flask.palletsprojects.com/) — the web framework.
- Original PikPak-Telegram bot authors — for laying the groundwork.
