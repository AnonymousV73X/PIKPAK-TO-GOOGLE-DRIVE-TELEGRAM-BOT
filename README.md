# 🛸 PikPak → Google Drive Ultra Bot
Transfer all your PikPak videos to Google Drive at max speed — directly from Telegram. No server setup, no GUI. Just paste a config and hit upload.

---

## ✨ What it does

- **One command transfer** — `/upload` scans your PikPak, finds all videos, and syncs them to a new Google Drive folder automatically
- **WebDAV bridge engine** — rclone serves PikPak as a local WebDAV server, then copies to GDrive. Fastest confirmed method with rclone v1.64+
- **Smart speed watchdog** — monitors upload speed every second. If it drops below 1 MB/s for 20 consecutive seconds (PikPak session throttling), the bot automatically kills the connection and starts a fresh WebDAV session
- **Auto-reconnect with GDrive verification** — after each reconnect, the bot queries GDrive to confirm which files actually landed. Only missing files are retried. Up to 20 reconnects per transfer
- **GDrive rate limit handling** — detects `rateLimitExceeded` and waits 90 seconds for the quota window to reset before retrying
- **Fatal error detection** — immediately stops and alerts on `storageQuotaExceeded`, expired credentials, and auth errors instead of looping forever
- **Live progress card** — real-time upload/download speeds, file count, reconnect counter, and current filename. Updates every 15 seconds in-place
- **Send to Telegram** — after transfer, `/sendfiles` downloads files from GDrive and sends them here with thumbnails
- **Multi-user** — each user gets their own rclone binary, config, and transfer session
- **2 GB uploads** — optional local Bot API server removes Telegram's 50 MB limit
- **Runs anywhere** — VPS, home server, or Google Colab

---

## 📋 Commands

| Command | Description |
|---|---|
| `/config` | Save your rclone config (text or .conf file) |
| `/upload` | Start PikPak → GDrive transfer |
| `/stop` | Kill transfer instantly |
| `/status` | Pin a fresh live network stats card |
| `/drive` | Google Drive storage stats |
| `/drivvy` | List all files in GDrive |
| `/pikky` | PikPak storage + video list |
| `/sendfiles` | Download GDrive files → Telegram |
| `/settings` | Toggle video vs document send mode |
| `/localapi` | Set up local API for 2 GB uploads |
| `/history` | View past transfer records |
| `/guide` | Full setup guide |

---

## 🚀 Quick Start

### Step 1 — Get a bot token
1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the steps
3. Copy the token you receive

### Step 2 — Set your token
Open `main.py` and replace the token near the top:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

### Step 3 — Run the bot
```bash
python main.py
```
Or on Colab:
```python
!python main.py
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

Export:
```bash
cat ~/.config/rclone/rclone.conf
```

**Option B — No terminal:** Use [rclone.dev](https://rclone.dev) in your browser to build the config visually, then export it.

Then send `/config` to your bot and paste the config text.

### Step 5 — Transfer
```
/upload
```
The bot scans PikPak, shows a preview of found videos, and starts syncing to a new auto-named folder in your Google Drive root.

---

## 📦 Dependencies

| Package | How it's handled |
|---|---|
| `pyTelegramBotAPI` | Auto-installed on first run |
| `rclone` | Auto-downloaded per user to `~/.local/bin/` (requires v1.64+) |
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

**Key settings:**
- `--transfers 2` · `--checkers 1` — conservative to avoid GDrive API rate limits
- `--size-only` — skips per-file hash checks (one cheap list pass vs. individual stat calls)
- `--drive-pacer-min-sleep 200ms` · `--tpslimit 3` — enforces pacing between GDrive API calls
- `--drive-chunk-size 64M` — smaller chunks reduce wasted bytes if a quota error interrupts

**Speed watchdog:** Monitors bytes/second every 1 second. If upload speed stays below **1 MB/s for 20 seconds**, the bot triggers a reconnect — kills both rclone copy and the WebDAV server, queries GDrive to confirm completed files, then starts a fresh session for the remaining files only.

> **Note on network stats:** The live card shows raw network throughput. Because the WebDAV bridge routes traffic through your machine (PikPak → machine → GDrive), total bytes displayed will be approximately **2× the actual file data**. This is expected and normal.

---

## 🖥 2 GB Upload Limit (Local Bot API)

By default Telegram limits file uploads to 50 MB. To unlock 2 GB:

1. Send `/localapi` → tap **⬇️ Download binary from URL**
2. Paste this link:
   ```
   https://drive.google.com/uc?export=download&id=1ti94G9SFsLec2zMn08RoQ5EhgGVJoDiA&confirm=t
   ```
3. Get API credentials from [my.telegram.org](https://my.telegram.org) → **API development tools**
4. Send `/localapi` → **🔑 Enter credentials** → paste your `api_id` and `api_hash`

The local server starts automatically on the next bot restart.

---

## ☁️ Running on Google Colab

The bot runs fine in a Colab cell with no modifications:

```python
!git clone https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT
%cd PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT
!python main.py
```

Set your `BOT_TOKEN` before running. Use Colab's high-bandwidth network for fast transfers.

---

## 🛡 Common Errors

| Error | Fix |
|---|---|
| `rateLimitExceeded` | Bot auto-waits 90s and retries. If persistent, your GDrive API quota is exhausted — wait and retry |
| `storageQuotaExceeded` | Your Google Drive is full. Free up space at [drive.google.com](https://drive.google.com) then `/upload` again |
| `captcha_invalid` | Log into PikPak in a browser on the same network as your bot, then retry `/upload` |
| Credentials expired | Re-run `rclone config` to refresh your GDRIVE token, then `/config` again |
| Transfer stuck reconnecting | Check `/pikky` to confirm PikPak is reachable. If PikPak returns empty files, your session may need a browser login |

---

## 📁 File Structure

```
main.py                      # ← the entire bot, single file
.bot.lock                    # process lock (auto-created, auto-deleted)
tg_api_data/                 # local Bot API server data (if used)
~/.pikpak_gdrive_bot.db      # SQLite database (users, transfers, settings)
~/.local/bin/rclone_*        # per-user rclone binaries (auto-downloaded)
~/.config/rclone/            # per-user rclone configs (auto-written)
/tmp/rclone_webdav_*.log     # WebDAV server logs (auto-cleaned)
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
- The bot only transfers video files (`mp4`, `mkv`, `avi`, `mov`, and 13 other formats)
- Each transfer creates a new uniquely-named folder in your Google Drive root
- The bot token in this repo is a placeholder — replace it before running
- Keep your `tg_api_id` and `tg_api_hash` private — they are tied to your Telegram account
- rclone v1.64 or newer is required (auto-downloaded if not present or outdated)

---

## 📜 License

MIT — do whatever you want with it.
