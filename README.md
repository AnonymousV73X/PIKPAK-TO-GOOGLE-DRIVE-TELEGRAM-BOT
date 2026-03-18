# 🛸 PikPak → Google Drive Ultra Bot

Transfer your PikPak videos to Google Drive at max speed — directly from Telegram. No server setup, no GUI. Paste a config, hit upload.

---

## ✨ What it does

- **One-command transfer** — `/upload` scans your PikPak, finds all videos, and syncs them to a new Google Drive folder automatically
- **File picker** — `/pick` lets you browse your PikPak, select individual files or a batch, and transfer only what you want
- **WebDAV bridge engine** — rclone serves PikPak as a local WebDAV server, then copies to GDrive. Fastest confirmed method with rclone v1.64+
- **Smart speed watchdog with backoff** — monitors upload speed every second. If it drops below 1 MB/s, the bot kills the connection and starts a fresh session. Each session is allowed progressively longer before the watchdog fires (60s → 90s → 120s … capped at 300s), preventing premature reconnects on large files
- **Session cap + rclone fallback** — after 10 WebDAV sessions, the bot automatically switches to a direct `rclone copy PIKKY: → GDRIVE:` fallback for any remaining files before giving up. If the fallback also fails, a clear message tells you exactly how many files made it and prompts `/sendfiles`
- **Auto-reconnect with GDrive verification** — after each reconnect, the bot queries GDrive to confirm which files actually landed. Only missing files are retried
- **GDrive rate limit handling** — detects `rateLimitExceeded` and waits 90 seconds for the quota window to reset before retrying
- **Fatal error detection** — immediately stops and alerts on `storageQuotaExceeded`, expired credentials, and auth errors
- **Live progress card** — real-time upload/download speeds, per-file progress bars, file count, reconnect counter, and current filename. Updates every 15 seconds in-place. If the card is deleted (e.g. by sending `/start`), the bot spawns a fresh one automatically
- **Send to Telegram with live progress** — `/sendfiles` downloads from GDrive and sends files to Telegram with per-file progress bars for both the download phase (← GDrive) and upload phase (→ Telegram), showing speed, bytes transferred, and elapsed time
- **Inline keyboard navigation** — every command is accessible from the home menu via inline buttons. All sub-panels (guide, settings, drive stats, history, etc.) edit in-place and include a 🔙 Go Back button. No dead ends
- **Multi-user** — each user gets their own rclone binary, config, and transfer session
- **2 GB uploads** — optional local Bot API server removes Telegram's 50 MB limit
- **Runs anywhere** — VPS, home server, or Google Colab

---

## 📋 Commands

| Command | Description |
|---|---|
| `/config` | Save your rclone config (text or .conf file) |
| `/upload` | Start PikPak → GDrive transfer (all videos) |
| `/pick` | Browse PikPak and select specific files to transfer |
| `/stop` | Kill transfer instantly |
| `/status` | Pin a fresh live transfer card |
| `/drive` | Google Drive storage stats |
| `/drivvy` | List all files in GDrive |
| `/pikky` | PikPak storage + video list |
| `/sendfiles` | Download GDrive files → Telegram |
| `/settings` | Toggle video vs document send mode |
| `/localapi` | Set up local API for 2 GB uploads |
| `/history` | View past transfer records |
| `/guide` | Full setup guide |

All commands also have inline button equivalents on the `/start` home screen.

---

## 🚀 Quick Start

### Step 1 — Get a bot token
1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the steps
3. Copy the token you receive

### Step 2 — Set your token

Open `bot.py` and replace the token near the top:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

### Step 3 — Run the bot
```bash
python bot.py
```
Or on Colab:
```python
!python bot.py
```

Everything else — rclone, the SQLite database, config files — is handled automatically on first run.

### Step 4 — Set up rclone config

You need a rclone config with two remotes:

| Remote name | Service |
|---|---|
| `PIKKY` | PikPak |
| `GDRIVE` | Google Drive |

**Option A — Terminal:**
```bash
curl https://rclone.org/install.sh | sudo bash
rclone config
```

Add PikPak:
```
name> PIKKY
Storage> pikpak
username> your@email.com
password> yourpassword
```

Add Google Drive:
```
name> GDRIVE
Storage> drive
scope> 1
Auto config> y
```

Export your config:
```bash
rclone config file     # shows the path
cat ~/.config/rclone/rclone.conf
```

**Option B — No terminal:**
Use [rclone.dev](https://rclone.dev) in your browser to build the config visually, then export it.

Then send `/config` to your bot and paste the config text (or upload the `.conf` file directly).

### Step 5 — Transfer
```
/upload
```
The bot scans PikPak, shows a preview of found videos, and starts syncing to a new auto-named folder in your Google Drive root.

Or use `/pick` to browse and select only the files you want.

---

## 📦 Dependencies

| Package | How it's handled |
|---|---|
| `pyTelegramBotAPI` | Auto-installed on first run |
| `rclone` | Auto-downloaded per user to `~/.local/bin/` (v1.64+ required) |
| `ffmpeg` | Optional — used for video thumbnails in `/sendfiles` |
| `sqlite3` | Built into Python — no install needed |

**Python 3.10+ required.**

---

## 🔧 Transfer Engine

The bot uses a **WebDAV bridge** architecture:

```
PikPak ──► rclone serve webdav (localhost:18765) ──► rclone copy ──► Google Drive
```

**Why WebDAV?** Direct `rclone copy PIKKY: GDRIVE:` hits PikPak's token-refresh bugs and stalls mid-transfer. Serving PikPak as a local WebDAV server lets rclone handle auth internally — consistently fast and reliable.

**Key rclone settings:**
- `--transfers 2` · `--checkers 1` — conservative to avoid GDrive API rate limits
- `--size-only` — skips per-file hash checks (one cheap list pass vs. individual stat calls)
- `--drive-pacer-min-sleep 200ms` · `--tpslimit 3` — enforces pacing between GDrive API calls
- `--drive-chunk-size 64M` — smaller chunks reduce wasted bytes on quota errors

**Speed watchdog with progressive backoff:**
Monitors bytes/second every 1 second. If upload speed stays below **1 MB/s**, the bot triggers a reconnect. Each session is allowed progressively more time before the watchdog fires:

| Session | Watchdog fires after |
|---|---|
| 1 | 60s of low speed |
| 2 | 90s |
| 3 | 120s |
| … | +30s each |
| 10 | 300s (cap) |

After **10 sessions**, the bot stops WebDAV and falls back to a direct rclone copy for the remaining files.

> **Note on network stats:** The live card shows raw network throughput. Because the WebDAV bridge routes traffic through your machine (PikPak → machine → GDrive), bytes displayed will be approximately **2× the actual file data**. This is expected.

---

## 🗂 File Picker (`/pick`)

The `/pick` command (also accessible from the home inline menu) lets you browse your entire PikPak file tree and select exactly which files to transfer:

1. Bot scans PikPak and shows a paginated list (10 files per page)
2. Tap any file to toggle ✅ / ◻️
3. Navigate pages with Prev / Next
4. Tap **Transfer N file(s)** to start — only selected files are transferred to a new GDrive folder

---

## 📤 Send Files Progress

The `/sendfiles` progress card shows two distinct phases for each file:

**Download phase (GDrive → local):**
```
🔹 ←  [▰▰▰▰▰▰▱▱▱▱▱▱]  52%

🔹 Download · 48.2 MB/s  ←  GDrive

🔹 842.3 MB / 1.6 GB  ·  18s elapsed
```

**Upload phase (local → Telegram):**
```
🔹 →  [▰▰▰▰▰▰▰▰▱▱▱▱]  68%

🔹 Upload · 12.3 MB/s  →  Telegram

🔹 1.1 GB / 1.6 GB  ·  1m 32s elapsed
```

When all files are done, the progress card is deleted and a clean completion summary is sent as a new message:

```
Transfer Complete
All files sent successfully.

━━━━━━━━━━━━━━━━━━
Sent       →  4
Skipped  →  0  (too large)
Failed     →  0
Total       →  4 files
━━━━━━━━━━━━━━━━━━
GD: Xenaxy147-20260318_045241
```

---

## 🖥 2 GB Upload Limit (Local Bot API)

By default Telegram limits file uploads to 50 MB. To unlock 2 GB:

1. Send `/localapi` → tap **⬇️ Download binary**
2. Paste this direct download link:
   ```
   https://drive.google.com/uc?export=download&id=1ti94G9SFsLec2zMn08RoQ5EhgGVJoDiA&confirm=t
   ```
3. Get API credentials from [my.telegram.org](https://my.telegram.org) → **API development tools**
4. Send `/localapi` → **🔑 Enter credentials** → paste your `api_id` and `api_hash`

The local server starts automatically and persists across restarts.

---

## ☁️ Running on Google Colab

```python
!git clone https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT
%cd PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT
!python bot.py
```

Set your `BOT_TOKEN` before running. Colab's high-bandwidth network makes transfers fast.

---

## 🛡 Common Errors

| Error | Fix |
|---|---|
| `rateLimitExceeded` | Bot auto-waits 90s and retries. If persistent, your GDrive API quota is exhausted — wait and retry |
| `storageQuotaExceeded` | Your Google Drive is full. Free up space at [drive.google.com](https://drive.google.com) then `/upload` again |
| `captcha_invalid` | Log into PikPak in a browser on the same network as your bot, then retry `/upload` |
| Credentials expired | Re-run `rclone config` to refresh your GDRIVE token, then `/config` again |
| Transfer loops / stuck | Bot now caps at 10 sessions and falls back to direct copy. If both fail, use `/sendfiles` to retrieve what's already on GDrive |
| "message to edit not found" | Fixed — the bot now auto-spawns a fresh status card if the previous one was deleted |

---

## 📁 File Structure

```
bot.py                       # ← the entire bot, single file
.bot.lock                    # process lock (auto-created, auto-deleted)
tg_api_data/                 # local Bot API server data (if used)
~/.pikpak_gdrive_bot.db      # SQLite database (users, transfers, settings)
~/.local/bin/rclone_*        # per-user rclone binaries (auto-downloaded)
~/.config/rclone/            # per-user rclone configs (auto-written)
/tmp/rclone_webdav_*.log     # WebDAV server logs (auto-cleaned)
/tmp/gdrive_send_*/          # temporary download cache for /sendfiles
```

---

## .gitignore

```
.bot.lock
tg_api_data/
telegram-bot-api
*.db
__pycache__/
*.pyc
/tmp/
```

---

## ⚠️ Notes

- Remote names must be exactly `PIKKY` and `GDRIVE` (case-sensitive)
- `/upload` transfers all video files (`mp4`, `mkv`, `avi`, `mov`, and 13 other formats). Use `/pick` to transfer specific files regardless of extension
- Each transfer creates a new uniquely-named folder in your Google Drive root
- The bot token in this repo is a placeholder — replace it before running
- Keep your `tg_api_id` and `tg_api_hash` private — they are tied to your Telegram account
- rclone v1.64 or newer is required (auto-downloaded if not present or outdated)
- The bot uses a deduplication guard on outgoing messages — sending `/start` repeatedly will not flood the chat

---

## 📜 License

MIT — do whatever you want with it.
