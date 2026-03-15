# 🛸 PikPak → Google Drive Ultra Bot

> Transfer all your PikPak videos to Google Drive at max speed — directly from Telegram. No server setup, no GUI. Just paste a config and hit upload.

---

## ✨ What it does

- **One command transfer** — `/upload` scans your PikPak, finds all videos, and syncs them to a new Google Drive folder automatically
- **Live progress card** — real-time upload/download speeds read from the OS network interface, with a byte-accurate progress bar
- **Smart message editing** — status cards edit in-place instead of flooding your chat
- **Send to Telegram** — after transfer, `/sendfiles` downloads files from GDrive and sends them here with thumbnails
- **Multi-user** — each user gets their own rclone binary, config, and transfer session
- **2 GB uploads** — optional local Bot API server removes Telegram's 50 MB limit
- **Runs anywhere** — VPS, home server, or even a Google Colab cell

---

## 📋 Commands

| Command | Description |
|---|---|
| `/config` | Save your rclone config (text or `.conf` file) |
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

Open `pikpak_gdrive_bot.py` and replace the token on **line 12**:

```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

### Step 3 — Run the bot

```bash
python pikpak_gdrive_bot.py
```

> Everything else — `rclone`, the SQLite database, config files — is handled automatically on first run.

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

The bot scans PikPak, shows a preview of found videos, and starts syncing to a new auto-named folder in your Google Drive.

---

## 📦 Dependencies

| Package | How it's handled |
|---|---|
| `pyTelegramBotAPI` | Auto-installed on first run |
| `rclone` | Auto-downloaded per user to `~/.local/bin/` |
| `ffmpeg` | Optional — used for video thumbnails in `/sendfiles` |
| `sqlite3` | Built into Python — no install needed |

**Python 3.10+** required.

---

## 🖥 2 GB Upload Limit (Local Bot API)

By default Telegram limits file uploads to **50 MB**. To unlock **2 GB**:

1. Send `/localapi` → tap **⬇️ Download binary from URL**
2. Paste this link:
```
https://drive.google.com/uc?export=download&id=1ti94G9SFsLec2zMn08RoQ5EhgGVJoDiA&confirm=t
```
3. Get API credentials from [my.telegram.org](https://my.telegram.org) → API development tools
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

## 🔧 Transfer Engine

```
4 parallel transfers · 8 checkers · checksum verify · 64 MB chunks
retries: 10 · low-level retries: 20 · timeout: 60s
```

rclone `sync` is used — files already in the destination are skipped automatically.

---

## 🛡 Fixing PikPak Captcha Errors

If you see `captcha_invalid` or `result:review`:

1. **Log into PikPak** in a browser on the **same network** as your bot, then retry `/upload`
2. **Recreate the PIKKY remote** — run `rclone config`, overwrite PIKKY, re-paste with `/config`
3. **Community bypass forks** — search GitHub for `rclone pikpak captcha bypass`

---

## 📁 File Structure

```
pikpak_gdrive_bot.py     # ← the entire bot, single file
.bot.lock                # process lock (auto-created, auto-deleted)
tg_api_data/             # local Bot API server data (if used)
~/.pikpak_gdrive_bot.db  # SQLite database (users, transfers, settings)
~/.local/bin/rclone_*    # per-user rclone binaries (auto-downloaded)
~/.config/rclone/        # per-user rclone configs (auto-written)
```

---

## .gitignore

```gitignore
.bot.lock
tg_api_data/
telegram-bot-api
*.db
__pycache__/
*.pyc
```

---

## ⚠️ Notes

- Remote names must be exactly `PIKKY` and `GDRIVE` (case-sensitive)
- The bot only transfers **video files** (`mp4`, `mkv`, `avi`, `mov`, and 15 other formats)
- Each transfer creates a new uniquely-named folder in your Google Drive root
- The bot token in this repo is a placeholder — replace it before running
- Keep your `tg_api_id` and `tg_api_hash` private — they are tied to your Telegram account

---

## 📜 License

MIT — do whatever you want with it.
