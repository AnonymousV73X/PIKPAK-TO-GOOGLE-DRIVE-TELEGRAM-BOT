"""
╔══════════════════════════════════════════════════════════════╗
║   PikPak → Google Drive  ·  ULTRA BOT  ·  REMASTERED v3.0    ║
║   Multi-user · Real-time stats · Smart message editing       ║
║   Transfer logic from v1 (proven, fast) + v2 UI/features     ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import subprocess
import sys
import time
import threading
import re
import random
import urllib.request
import zipfile
import stat
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
from contextlib import contextmanager
import html
import signal
import socket


# * ─── Package Bootstrap ────────────────────────────────────────────────────────


def install_package(package):
    subprocess.call(
        [sys.executable, "-m", "pip", "uninstall", "-y", "telebot"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import_name = "telebot" if package == "pyTelegramBotAPI" else package
    try:
        __import__(import_name)
    except ImportError:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--break-system-packages",
                package,
            ],
            stdout=subprocess.DEVNULL,
        )
        import importlib

        importlib.invalidate_caches()


install_package("pyTelegramBotAPI")

import telebot
from telebot.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)


#! ─── Visual Constants ─────────────────────────────────────────────────────────

BAR_FULL = 14
BAR_MINI = 10
BAR_DL = 12
FILLED = "▰"
EMPTY = "▱"


def make_bar(filled: int, width: int) -> str:
    filled = max(0, min(filled, width))
    return FILLED * filled + EMPTY * (width - filled)


def pct_bar(pct: int, width: int = BAR_FULL) -> str:
    return make_bar(int(width * pct / 100), width)


DIVIDER = "━" * 18
DIVIDER_SM = "━" * 18


# $ ─── Local API Binary Discovery ───────────────────────────────────────────────


def _find_local_api_bin() -> str:
    BINARY = "telegram-bot-api"
    roots = []
    try:
        roots.append(os.path.dirname(os.path.abspath(__file__)))
    except:
        pass
    roots += [
        os.getcwd(),
        "/content",
        "/content/drive/MyDrive",
        os.path.expanduser("~"),
        os.path.expanduser("~/bin"),
        os.path.expanduser("~/.local/bin"),
        "/opt",
        "/opt/bin",
        "/srv",
        "/app",
        "/usr/local/bin",
        "/tmp",
    ]
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if p:
            roots.append(p)

    seen, unique = set(), []
    for r in roots:
        if r and r not in seen and os.path.isdir(r):
            seen.add(r)
            unique.append(r)

    for root in unique:
        direct = os.path.join(root, BINARY)
        if os.path.isfile(direct):
            return direct

    SKIP = {
        "proc",
        "sys",
        "dev",
        "run",
        "snap",
        "boot",
        "lib",
        "lib64",
        "lib32",
        "usr",
        "bin",
        "sbin",
        "etc",
        "var",
        "lost+found",
        "__pycache__",
        ".git",
        "node_modules",
    }
    crawled = set()
    for root in unique + ["/"]:
        root = os.path.realpath(root)
        if root in crawled:
            continue
        crawled.add(root)
        try:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [
                    d for d in dirnames if d not in SKIP and not d.startswith(".")
                ]
                if BINARY in filenames:
                    return os.path.join(dirpath, BINARY)
        except PermissionError:
            continue
    return os.path.join(os.getcwd(), BINARY)


SCRIPT_DIR = os.getcwd()
LOCAL_API_BIN = _find_local_api_bin()
LOCAL_API_PORT = 8081
LOCAL_API_PROC = None


def _local_api_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", LOCAL_API_PORT), timeout=1):
            return True
    except OSError:
        return False


def _probe_binary_flags(binary: str) -> dict:
    result = {
        "api_id_flag": None,
        "api_hash_flag": None,
        "has_local": False,
        "has_http_port": False,
        "has_dir": False,
        "has_verbosity": False,
        "raw_help": "",
    }
    try:
        probe = subprocess.run(
            [binary, "--help"], capture_output=True, text=True, timeout=8
        )
        raw = probe.stdout + probe.stderr
        result["raw_help"] = raw
    except:
        return result

    result["api_id_flag"] = (
        "--telegram-api-id"
        if "--telegram-api-id" in raw
        else ("--api-id" if "--api-id" in raw else None)
    )
    result["api_hash_flag"] = (
        "--telegram-api-hash"
        if "--telegram-api-hash" in raw
        else ("--api-hash" if "--api-hash" in raw else None)
    )
    result["has_local"] = "--local" in raw
    result["has_http_port"] = "--http-port" in raw
    result["has_dir"] = "--dir" in raw
    result["has_verbosity"] = "--verbosity" in raw
    return result


def start_local_api(bot_token: str, api_id: str = "1", api_hash: str = "x") -> bool:
    global LOCAL_API_PROC
    if _local_api_running():
        return True
    if not os.path.isfile(LOCAL_API_BIN):
        return False
    try:
        st = os.stat(LOCAL_API_BIN)
        os.chmod(LOCAL_API_BIN, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except:
        pass

    api_work_dir = os.path.join(SCRIPT_DIR, "tg_api_data")
    os.makedirs(api_work_dir, exist_ok=True)
    log_file = os.path.join(api_work_dir, "server.log")
    flags = _probe_binary_flags(LOCAL_API_BIN)
    cmd = [LOCAL_API_BIN]
    if flags["api_id_flag"]:
        cmd.append(f"{flags['api_id_flag']}={api_id}")
    if flags["api_hash_flag"]:
        cmd.append(f"{flags['api_hash_flag']}={api_hash}")
    if flags["has_local"]:
        cmd.append("--local")
    cmd.append(f"--http-port={LOCAL_API_PORT}")
    if flags["has_dir"]:
        cmd.append(f"--dir={api_work_dir}")
    if flags["has_verbosity"]:
        cmd.append("--verbosity=2")

    try:
        log_fd = open(log_file, "w")
        LOCAL_API_PROC = subprocess.Popen(
            cmd, stdout=log_fd, stderr=log_fd, preexec_fn=os.setsid
        )
        for i in range(30):
            time.sleep(0.5)
            if LOCAL_API_PROC.poll() is not None:
                LOCAL_API_PROC = None
                return False
            if _local_api_running():
                print(f"✓ Local Bot API running on :{LOCAL_API_PORT}")
                return True
        try:
            LOCAL_API_PROC.kill()
        except:
            pass
        LOCAL_API_PROC = None
        return False
    except Exception as e:
        print(f"⚠️ Local API start error: {e}")
        LOCAL_API_PROC = None
        return False


def stop_local_api():
    global LOCAL_API_PROC
    if LOCAL_API_PROC:
        try:
            os.killpg(os.getpgid(LOCAL_API_PROC.pid), signal.SIGTERM)
        except:
            pass
        LOCAL_API_PROC = None


# ? ══════════════════════════════════════════════════════════════
# ?  ★  CONFIGURATION  —  edit this before running  ★
# ? ══════════════════════════════════════════════════════════════

BOT_TOKEN = "YOUR TOKEN HERE"

# ? ══════════════════════════════════════════════════════════════


def make_bot(use_local: bool) -> telebot.TeleBot:
    import telebot.apihelper as _ah

    # Always reset to official API first — prevents poisoned URL from previous run
    _ah.API_URL = "https://api.telegram.org/bot{0}/{1}"
    if not use_local:
        return telebot.TeleBot(BOT_TOKEN, num_threads=8)
    _ah.API_URL = f"http://127.0.0.1:{LOCAL_API_PORT}/bot{{0}}/{{1}}"
    b = telebot.TeleBot(BOT_TOKEN, num_threads=8)
    try:
        b.get_me()
        return b
    except Exception:
        # Local API unreachable — fully fall back to official API
        _ah.API_URL = "https://api.telegram.org/bot{0}/{1}"
        return telebot.TeleBot(BOT_TOKEN, num_threads=8)


# . ─── Database ─────────────────────────────────────────────────────────────────

DB_PATH = os.path.expanduser("~/.pikpak_gdrive_bot.db")


def _dt_adapter(val):
    return val.isoformat() if isinstance(val, datetime) else str(val)


def _dt_converter(val):
    try:
        return datetime.fromisoformat(val.decode())
    except:
        return val.decode()


sqlite3.register_adapter(datetime, _dt_adapter)
sqlite3.register_converter("TIMESTAMP", _dt_converter)


@contextmanager
def get_db():
    conn = sqlite3.connect(
        DB_PATH, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            config      TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transfers (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            INTEGER,
            status             TEXT,
            start_time         TIMESTAMP,
            end_time           TIMESTAMP,
            destination_folder TEXT,
            files_count        INTEGER DEFAULT 0,
            total_size         TEXT    DEFAULT 'Unknown',
            transferred_size   TEXT    DEFAULT '0 B',
            speed              TEXT    DEFAULT '0 B/s',
            error_message      TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id  INTEGER PRIMARY KEY,
            send_as  TEXT DEFAULT 'video',
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS user_messages (
            user_id     INTEGER,
            msg_type    TEXT,
            chat_id     INTEGER,
            message_id  INTEGER,
            PRIMARY KEY (user_id, msg_type)
        );
        """
        )
        for sql in [
            "ALTER TABLE user_settings ADD COLUMN tg_api_id   TEXT DEFAULT NULL",
            "ALTER TABLE user_settings ADD COLUMN tg_api_hash TEXT DEFAULT NULL",
        ]:
            try:
                conn.execute(sql)
            except:
                pass
        conn.commit()


init_db()


def _boot_local_api() -> bool:
    if not os.path.isfile(LOCAL_API_BIN):
        return False
    # If server survived a previous run and is already up, just use it
    if _local_api_running():
        print("✓ Local Bot API already running, reusing.")
        return True
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT tg_api_id, tg_api_hash FROM user_settings "
                "WHERE tg_api_id IS NOT NULL AND tg_api_hash IS NOT NULL LIMIT 1"
            ).fetchone()
        if row:
            return start_local_api(
                BOT_TOKEN, api_id=row["tg_api_id"], api_hash=row["tg_api_hash"]
            )
        return False
    except Exception:
        return False


_using_local_api = _boot_local_api()
bot = make_bot(_using_local_api)


def MAX_SEND_BYTES() -> int:
    return 2 * 1024**3 if _using_local_api else 49 * 1024**2


# - ─── Message Store ────────────────────────────────────────────────────────────


class MsgStore:
    _lock = threading.Lock()

    @staticmethod
    def save(user_id: int, msg_type: str, chat_id: int, message_id: int):
        with MsgStore._lock:
            with get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO user_messages (user_id, msg_type, chat_id, message_id) VALUES (?,?,?,?)",
                    (user_id, msg_type, chat_id, message_id),
                )
                conn.commit()

    @staticmethod
    def get(user_id: int, msg_type: str):
        with get_db() as conn:
            row = conn.execute(
                "SELECT chat_id, message_id FROM user_messages WHERE user_id=? AND msg_type=?",
                (user_id, msg_type),
            ).fetchone()
            return (row["chat_id"], row["message_id"]) if row else (None, None)

    @staticmethod
    def clear(user_id: int, msg_type: str):
        with get_db() as conn:
            conn.execute(
                "DELETE FROM user_messages WHERE user_id=? AND msg_type=?",
                (user_id, msg_type),
            )
            conn.commit()

    @staticmethod
    def delete_msg(user_id: int, msg_type: str):
        chat_id, msg_id = MsgStore.get(user_id, msg_type)
        if chat_id and msg_id:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
            MsgStore.clear(user_id, msg_type)


# * ─── User Manager ─────────────────────────────────────────────────────────────


class UserManager:
    @staticmethod
    def get_user(user_id):
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def save_user(user_id, username, first_name, config):
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (user_id, username, first_name, config) VALUES (?,?,?,?)",
                (user_id, username, first_name, config),
            )
            conn.commit()

    @staticmethod
    def get_config(user_id):
        u = UserManager.get_user(user_id)
        return u["config"] if u and u["config"] else None

    @staticmethod
    def exists(user_id):
        with get_db() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM users WHERE user_id=?", (user_id,)
                ).fetchone()
                is not None
            )

    @staticmethod
    def save_transfer(
        user_id,
        status,
        start_time,
        end_time,
        destination_folder,
        files_count,
        total_size,
        transferred_size,
        speed,
        error_message,
    ):
        with get_db() as conn:
            conn.execute(
                """INSERT INTO transfers
                   (user_id,status,start_time,end_time,destination_folder,
                    files_count,total_size,transferred_size,speed,error_message)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    user_id,
                    status,
                    start_time,
                    end_time,
                    destination_folder,
                    files_count,
                    total_size,
                    transferred_size,
                    speed,
                    error_message,
                ),
            )
            conn.commit()

    @staticmethod
    def get_transfers(user_id, limit=10):
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM transfers WHERE user_id=? ORDER BY start_time DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_settings(user_id) -> dict:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM user_settings WHERE user_id=?", (user_id,)
            ).fetchone()
            return dict(row) if row else {"user_id": user_id, "send_as": "video"}

    @staticmethod
    def set_setting(user_id, key: str, value: str):
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,)
            )
            conn.execute(
                f"UPDATE user_settings SET {key}=? WHERE user_id=?", (value, user_id)
            )
            conn.commit()

    @staticmethod
    def get_api_credentials(user_id):
        s = UserManager.get_settings(user_id)
        return s.get("tg_api_id"), s.get("tg_api_hash")

    @staticmethod
    def save_api_credentials(user_id, api_id: str, api_hash: str):
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,)
            )
            conn.execute(
                "UPDATE user_settings SET tg_api_id=?, tg_api_hash=? WHERE user_id=?",
                (api_id.strip(), api_hash.strip(), user_id),
            )
            conn.commit()


# . ─── Utilities ────────────────────────────────────────────────────────────────


def generate_alien_name():
    prefixes = [
        "Zor",
        "Xen",
        "Qua",
        "Vor",
        "Kly",
        "Sor",
        "Tyr",
        "Neb",
        "Gal",
        "Cos",
        "Andro",
        "Nebu",
        "Puls",
        "Quas",
        "Supern",
        "Epsil",
        "Centa",
        "Proxim",
        "Anta",
        "Betel",
        "Rigel",
        "Alde",
        "Arctu",
        "Spic",
        "Poll",
        "Fomal",
        "Deneb",
        "Regul",
        "Cast",
        "Bella",
        "Mira",
        "Alta",
        "Algo",
        "Capel",
        "Canop",
    ]
    suffixes = [
        "blax",
        "dor",
        "gon",
        "thar",
        "zon",
        "nax",
        "tar",
        "vax",
        "rox",
        "lax",
        "meda",
        "ula",
        "axy",
        "ion",
        "us",
        "ar",
        "ix",
        "um",
        "ra",
        "is",
        "nova",
        "ius",
        "on",
        "os",
        "a",
        "or",
    ]
    name = f"{random.choice(prefixes)}{random.choice(suffixes)}"
    if random.random() > 0.7:
        name += str(random.randint(1, 999))
    return name


def strip_ansi(text: str) -> str:
    return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)


def safe_escape(text) -> str:
    return html.escape(str(text)) if text else ""


def fmt_size(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%b %d %Y · %I:%M %p")


VIDEO_EXTS = [
    "mp4",
    "mkv",
    "avi",
    "mov",
    "wmv",
    "flv",
    "webm",
    "mpg",
    "mpeg",
    "m4v",
    "3gp",
    "ts",
    "m2ts",
    "vob",
    "rmvb",
    "rm",
]


# * ─── Safe Send / Edit helpers ─────────────────────────────────────────────────


def send_msg(chat_id, text, parse_mode="HTML", reply_markup=None, reply_to=None):
    import telebot.apihelper as _ah

    text = str(text)

    def _attempt():
        if len(text) <= 4000:
            kwargs = dict(chat_id=chat_id, text=text, parse_mode=parse_mode)
            if reply_markup:
                kwargs["reply_markup"] = reply_markup
            if reply_to:
                kwargs["reply_to_message_id"] = reply_to
            return bot.send_message(**kwargs)
        # Chunked send for long messages
        chunks, buf = [], ""
        for line in text.split("\n"):
            if len(buf) + len(line) + 1 > 4000:
                if buf:
                    chunks.append(buf)
                buf = line
            else:
                buf = (buf + "\n" + line) if buf else line
        if buf:
            chunks.append(buf)
        sent = None
        for i, chunk in enumerate(chunks):
            markup = reply_markup if i == len(chunks) - 1 else None
            header = f"<b>({i+1}/{len(chunks)})</b>\n" if i > 0 else ""
            kwargs = dict(chat_id=chat_id, text=header + chunk, parse_mode=parse_mode)
            if markup:
                kwargs["reply_markup"] = markup
            if reply_to and i == 0:
                kwargs["reply_to_message_id"] = reply_to
            try:
                sent = bot.send_message(**kwargs)
            except Exception as e:
                print(f"[send_msg chunk {i+1}] {e}")
            time.sleep(0.3)
        return sent

    try:
        return _attempt()
    except Exception as e:
        err_str = str(e).lower()
        if _using_local_api and (
            "connection refused" in err_str or "max retries" in err_str
        ):
            # Local API is down — transparently fall back to official API for this one call
            print(f"[send_msg] local API unreachable, falling back to official API")
            old_url = _ah.API_URL
            _ah.API_URL = "https://api.telegram.org/bot{0}/{1}"
            try:
                return _attempt()
            except Exception as e2:
                print(f"[send_msg fallback] {e2}")
                return None
            finally:
                _ah.API_URL = old_url  # always restore
        print(f"[send_msg] {e}")
        return None


def edit_msg(chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
    import telebot.apihelper as _ah

    text = str(text)[:4000]

    def _attempt():
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        return True

    try:
        return _attempt()
    except Exception as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            return True
        if _using_local_api and (
            "connection refused" in err_str or "max retries" in err_str
        ):
            print(f"[edit_msg] local API unreachable, falling back to official API")
            old_url = _ah.API_URL
            _ah.API_URL = "https://api.telegram.org/bot{0}/{1}"
            try:
                return _attempt()
            except Exception as e2:
                s2 = str(e2).lower()
                if "message is not modified" in s2:
                    return True
                print(f"[edit_msg fallback] {e2}")
                return False
            finally:
                _ah.API_URL = old_url
        print(f"[edit_msg] {e}")
        return False


def delete_msg(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass


def smart_send_or_edit(
    user_id: int,
    msg_type: str,
    chat_id: int,
    text: str,
    reply_markup=None,
    parse_mode="HTML",
) -> int | None:
    old_chat, old_mid = MsgStore.get(user_id, msg_type)
    if old_chat and old_mid:
        ok = edit_msg(
            old_chat, old_mid, text, parse_mode=parse_mode, reply_markup=reply_markup
        )
        if ok:
            return old_mid
        MsgStore.clear(user_id, msg_type)

    sent = send_msg(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    if sent:
        MsgStore.save(user_id, msg_type, chat_id, sent.message_id)
        return sent.message_id
    return None


#! ─── Network Monitor ──────────────────────────────────────────────────────────


class NetworkMonitor:
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.previous_stats = {}
        self.start_time = None
        self.total_uploaded = 0.0
        self.total_downloaded = 0.0
        self.current_upload_speed = 0.0
        self.current_download_speed = 0.0
        self.last_update_time = None
        self._lock = threading.Lock()

    def _get_net_stats(self) -> dict:
        try:
            with open("/proc/net/dev") as f:
                lines = f.readlines()
            stats = {}
            for line in lines[2:]:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                vals = data.split()
                if len(vals) >= 16:
                    stats[iface.strip()] = {"rx": int(vals[0]), "tx": int(vals[8])}
            return stats
        except:
            return {}

    @staticmethod
    def _fmt_size(n: float) -> str:
        for u in ["B", "KB", "MB", "GB", "TB"]:
            if n < 1024:
                return f"{n:.2f} {u}"
            n /= 1024
        return f"{n:.2f} PB"

    @staticmethod
    def _fmt_speed(bps: float) -> str:
        return NetworkMonitor._fmt_size(bps) + "/s"

    def _calc_speeds(self, current: dict, elapsed: float):
        if not self.previous_stats or elapsed == 0:
            return 0.0, 0.0
        rx_diff = tx_diff = 0
        for iface, v in current.items():
            if iface in self.previous_stats:
                rd = v["rx"] - self.previous_stats[iface]["rx"]
                td = v["tx"] - self.previous_stats[iface]["tx"]
                if rd > 0:
                    rx_diff += rd
                if td > 0:
                    tx_diff += td
        return rx_diff / elapsed, tx_diff / elapsed

    def _loop(self, interval=1.0):
        self.start_time = datetime.now()
        self.previous_stats = self._get_net_stats()
        while self.monitoring:
            time.sleep(interval)
            current = self._get_net_stats()
            if not current:
                continue
            now = datetime.now()
            elapsed = (now - self.last_update_time).total_seconds()
            dl, ul = self._calc_speeds(current, elapsed)
            with self._lock:
                self.current_download_speed = dl
                self.current_upload_speed = ul
                self.total_downloaded += dl * elapsed
                self.total_uploaded += ul * elapsed
            self.previous_stats = current
            self.last_update_time = now

    def start(self, interval=1.0):
        if self.monitoring:
            return
        self.monitoring = True
        self.last_update_time = datetime.now()
        self.total_uploaded = self.total_downloaded = 0.0
        self.current_upload_speed = self.current_download_speed = 0.0
        self.monitor_thread = threading.Thread(
            target=self._loop, args=(interval,), daemon=True
        )
        self.monitor_thread.start()

    def stop(self):
        self.monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)

    def get_stats(self) -> dict:
        with self._lock:
            elapsed = (
                str(datetime.now() - self.start_time).split(".")[0]
                if self.start_time
                else "00:00:00"
            )
            is_active = (
                self.current_upload_speed > 1024 or self.current_download_speed > 1024
            )
            return {
                "upload_speed": self._fmt_speed(self.current_upload_speed),
                "download_speed": self._fmt_speed(self.current_download_speed),
                "total_uploaded": self._fmt_size(self.total_uploaded),
                "total_downloaded": self._fmt_size(self.total_downloaded),
                "elapsed": elapsed,
                "status": "🟢 ACTIVE" if is_active else "🟡 IDLE",
                "upload_bps": self.current_upload_speed,
            }


# * ─── Transfer Manager ────────────────────────────────────────────────────────


class TransferManager:
    def __init__(self, user_id: int, chat_id: int):
        self.user_id = user_id
        self.chat_id = chat_id
        self.transfer_in_progress = False
        self.stop_requested = False
        self.transfer_process = None
        self.process_lock = threading.Lock()
        self._kill_evt = threading.Event()
        self.network_monitor = NetworkMonitor()
        self.logs: list[str] = []
        self.status_msg_id = None
        self.status_lock = threading.Lock()
        self.start_time = None
        self.destination_folder = None
        self.video_files: list[str] = []
        self.total_size_str = "Unknown"
        self.total_size_bytes = 0
        self.files_done = 0
        self.transfer_attempt = 0
        self.reconnect_count = 0  # how many WebDAV reconnects happened
        self.current_file_name = ""  # file currently transferring
        self.config = UserManager.get_config(user_id)
        self.rclone_path = os.path.expanduser(f"~/.local/bin/rclone_{user_id}")
        self.config_file = os.path.expanduser(f"~/.config/rclone/user_{user_id}.conf")
        if not self.config:
            raise ValueError("No config found. Use /config first.")

    # ── helpers ────────────────────────────────────────────────────────────────

    def _log(self, level, msg):
        icons = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERR": "❌", "HEAD": "🚀"}
        entry = f"{icons.get(level,'▪️')} {msg}"
        print(entry)
        self.logs.append(entry)

    def info(self, m):
        self._log("INFO", m)

    def ok(self, m):
        self._log("OK", m)

    def warn(self, m):
        self._log("WARN", m)

    def err(self, m):
        self._log("ERR", m)

    def head(self, m):
        self._log("HEAD", m)

    def _edit(self, text, markup=None):
        if not self.status_msg_id:
            return
        edit_msg(
            self.chat_id,
            self.status_msg_id,
            str(text)[:4000],
            parse_mode="HTML",
            reply_markup=markup,
        )

    def _stop_kb(self):
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton(
                "⏹  Stop Transfer", callback_data=f"stop_{self.user_id}"
            )
        )
        return kb

    def _live_kb(self):
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{self.user_id}"),
            InlineKeyboardButton("⏹  Stop", callback_data=f"stop_{self.user_id}"),
        )
        return kb

    def render_status(self, phase="transferring") -> str:
        elapsed = (
            str(datetime.now() - self.start_time).split(".")[0]
            if self.start_time
            else "—"
        )
        if phase == "scanning":
            return "\n".join(
                [
                    "🔭 <b>Scanning PikPak…</b>",
                    "",
                    "📡  Listing all files…",
                    f"⏱   Elapsed : <b>{elapsed}</b>",
                ]
            )[:4000]

        ns = self.network_monitor.get_stats()
        total_files = len(self.video_files)
        done_files = self.files_done

        if total_files > 0 and done_files > 0:
            pct = min(int(done_files / total_files * 100), 100)
        else:
            pct = 0

        # ── Progress bar ──────────────────────────────────────────────────
        bar = pct_bar(pct, BAR_FULL)

        # ── Current file (trimmed nicely) ─────────────────────────────────
        cf = self.current_file_name
        if cf:
            # strip leading folder path, keep just the filename
            cf_display = os.path.basename(cf) if "/" in cf or "\\" in cf else cf
            cf_display = cf_display[-55:] if len(cf_display) > 55 else cf_display
            current_line = f"\n📄  <i>{safe_escape(cf_display)}</i>"
        else:
            current_line = ""

        # ── Reconnect badge ───────────────────────────────────────────────
        rc_badge = (
            f"  🔁 <b>{self.reconnect_count}</b> reconnects"
            if self.reconnect_count > 0
            else ""
        )

        # ── Speed indicator emoji ─────────────────────────────────────────
        up_bps = ns["upload_bps"]
        if up_bps >= 10 * 1024 * 1024:
            spd_icon = "🚀"
        elif up_bps >= 3 * 1024 * 1024:
            spd_icon = "⚡"
        elif up_bps >= 512 * 1024:
            spd_icon = "🟡"
        else:
            spd_icon = "🔴"

        lines = [
            "🍀 <b>BELOW IS YOU LIVE TRANSFER 🍀</b>",
            "",
            f"<code>[{bar}]</code>  <b>{pct}%</b>",
            "",
            f"💾  <b>{done_files}/{total_files}</b> files",
            "",
            DIVIDER_SM,
            f"{spd_icon}  <b>{ns['upload_speed']}</b>\t→\tGDrive",
            DIVIDER_SM,
            f"🔹  <b>{ns['download_speed']}</b>\t←\tPikPak",
            DIVIDER_SM,
            f"⏱️  <b>{ns['elapsed']}</b>{rc_badge}",
            DIVIDER_SM,
            "",
            f"💾  <b>{self.total_size_str}</b>  in  <b>{total_files}</b> video{'s' if total_files != 1 else ''}",
            "",
            f"📂  <code>{safe_escape((self.destination_folder or '…')[-45:])}</code>",
        ]
        return "\n".join(lines)[:4000]

    # ── rclone install ─────────────────────────────────────────────────────────

    def _install_rclone(self) -> bool:
        url = "https://downloads.rclone.org/rclone-current-linux-amd64.zip"
        tmp = f"/tmp/rclone_install_{self.user_id}"
        zip_p = os.path.join(tmp, "rclone.zip")
        bin_dir = os.path.dirname(self.rclone_path)

        def _get_version(path: str):
            try:
                r = subprocess.run(
                    [path, "version"], capture_output=True, text=True, timeout=10
                )
                import re as _re

                m = _re.search(r"rclone v(\d+)\.(\d+)", r.stdout + r.stderr)
                if m:
                    return int(m.group(1)), int(m.group(2))
            except Exception:
                pass
            return (0, 0)

        def _install_fresh() -> bool:
            self.info("Downloading rclone…")
            self._edit("⏳ <b>Setup</b>\n\nDownloading latest rclone…")
            try:
                os.makedirs(tmp, exist_ok=True)
                os.makedirs(bin_dir, exist_ok=True)
                urllib.request.urlretrieve(url, zip_p)
                with zipfile.ZipFile(zip_p, "r") as z:
                    z.extractall(tmp)
                dirs = [
                    d
                    for d in os.listdir(tmp)
                    if os.path.isdir(os.path.join(tmp, d)) and d.startswith("rclone-")
                ]
                if not dirs:
                    self.err("Extracted rclone dir not found.")
                    return False
                binary = os.path.join(tmp, dirs[0], "rclone")
                shutil.copy2(binary, self.rclone_path)
                os.chmod(
                    self.rclone_path,
                    stat.S_IRWXU
                    | stat.S_IRGRP
                    | stat.S_IXGRP
                    | stat.S_IROTH
                    | stat.S_IXOTH,
                )
                shutil.rmtree(tmp, ignore_errors=True)
                return True
            except Exception as e:
                self.err(f"rclone install failed: {e}")
                shutil.rmtree(tmp, ignore_errors=True)
                return False

        if os.path.exists(self.rclone_path) and os.access(self.rclone_path, os.X_OK):
            ver = _get_version(self.rclone_path)
            ver_str = f"v{ver[0]}.{ver[1]}"
            if ver >= (1, 64):
                self.ok(f"rclone {ver_str} ready ✓")
                return True
            else:
                self.warn(f"rclone {ver_str} too old, updating…")
                if not _install_fresh():
                    return False
        elif not _install_fresh():
            return False

        ver = _get_version(self.rclone_path)
        ver_str = f"v{ver[0]}.{ver[1]}"
        if ver == (0, 0):
            self.err("rclone version check failed after install.")
            return False
        self.ok(f"rclone {ver_str} installed ✓")
        return True

    def _write_config(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w") as f:
            f.write(self.config)
        self.ok("Config written.")

    def _run_cmd(self, command: str, timeout: int = 300):
        try:
            r = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "timeout"
        except Exception as e:
            return False, "", str(e)

    # ── verify remotes ────────────────────────────────────────────────────────

    def _verify_remotes(self) -> bool:
        self.info("Verifying PIKKY and GDRIVE…")
        for remote in ["PIKKY", "GDRIVE"]:
            self._edit(
                f"🔌 <b>Checking connections…</b>\n\n{DIVIDER_SM}\nChecking <code>{remote}</code>…"
            )
            ok, _, err = self._run_cmd(
                f"{self.rclone_path} --config {self.config_file} lsd {remote}:"
            )
            if not ok:
                self.err(f"{remote} failed: {err}")
                return False
            self.ok(f"{remote} connection verified.")
        return True

    # ── scan videos ───────────────────────────────────────────────────────────

    def _scan_videos(self) -> bool:
        self.info("Scanning PikPak…")
        self._edit(self.render_status("scanning"), self._stop_kb())

        ok, out, err = self._run_cmd(
            f"{self.rclone_path} --config {self.config_file} lsf PIKKY: --recursive",
            timeout=300,
        )
        if not ok:
            self.err(f"List failed: {err}")
            return False

        all_files = [f for f in out.split("\n") if f.strip()]
        self.video_files = [
            f for f in all_files if f.rsplit(".", 1)[-1].lower() in VIDEO_EXTS
        ]
        if not self.video_files:
            self.warn("No videos found.")
            return False

        filter_rules = ["+ */"] + [f"+ *.{ext}" for ext in VIDEO_EXTS] + ["- .*", "- *"]
        filter_str = " ".join([f'--filter "{r}"' for r in filter_rules])
        ok2, out2, _ = self._run_cmd(
            f"{self.rclone_path} --config {self.config_file} "
            f"size PIKKY: --fast-list {filter_str}",
            timeout=180,
        )
        if ok2:
            for line in out2.split("\n"):
                if line.startswith("Total size:"):
                    self.total_size_str = line.split(":", 1)[1].strip()
                    self.total_size_bytes = self._parse_size_bytes(self.total_size_str)
                    break

        preview = "\n".join(
            f"  🎬 <code>{safe_escape(f)}</code>" for f in self.video_files[:7]
        )
        more = (
            f"\n  <i>…and {len(self.video_files)-7} more</i>"
            if len(self.video_files) > 7
            else ""
        )
        self._edit(
            f"✅ <b>Scan Complete!</b>\n\n"
            f"{DIVIDER_SM}\n"
            f"📹  Videos found  <b>{len(self.video_files)}</b>\n"
            f"💾  Total size    <b>{self.total_size_str}</b>\n"
            f"{DIVIDER_SM}\n\n"
            f"<b>Preview:</b>\n{preview}{more}\n\n"
            f"⚡ Starting transfer in 3 seconds…",
            self._stop_kb(),
        )
        time.sleep(3)
        return True

    @staticmethod
    def _parse_size_bytes(size_str: str) -> int:
        if not size_str:
            return 0
        m = re.search(r"\((\d[\d\s,]*)\s*Byte", size_str, re.IGNORECASE)
        if m:
            return int(re.sub(r"[\s,]", "", m.group(1)))
        m = re.search(
            r"([\d.]+)\s*(B|KB|KiB|MB|MiB|GB|GiB|TB|TiB)", size_str, re.IGNORECASE
        )
        if m:
            val = float(m.group(1))
            unit = m.group(2).upper()
            mult = {
                "B": 1,
                "KB": 1000,
                "KIB": 1024,
                "MB": 1000**2,
                "MIB": 1024**2,
                "GB": 1000**3,
                "GIB": 1024**3,
                "TB": 1000**4,
                "TIB": 1024**4,
            }
            return int(val * mult.get(unit, 1))
        m = re.search(r"\d+", size_str)
        return int(m.group()) if m else 0

    def _kill_process(self, process):
        if process is None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception:
            try:
                process.terminate()
            except Exception:
                pass
        for _ in range(50):
            if process.poll() is not None:
                return
            time.sleep(0.1)
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # ★  CORE TRANSFER ENGINE
    #
    #  Strategy: WebDAV bridge per-batch, with speed watchdog.
    #
    #  PikPak throttles persistent WebDAV sessions — after completing
    #  file N, the session slows to near-zero for file N+1.
    #  Fix: monitor upload speed every second. If speed stays below
    #  SPEED_THRESHOLD_BPS for SLOW_TRIGGER_SECS consecutive seconds,
    #  we treat it as throttling:
    #    1. Kill rclone copy + WebDAV server
    #    2. Check GDRIVE dest to see which files landed successfully
    #    3. Build a filter excluding completed files
    #    4. Restart a fresh WebDAV session and rclone copy
    #  This resets the PikPak session token and restores full speed.
    #  Repeats until all files are confirmed on GDrive.
    # ══════════════════════════════════════════════════════════════════════════

    _WEBDAV_PORT = 18765
    _MAX_RECONNECTS = 20  # absolute ceiling on reconnect attempts
    _SPEED_THRESHOLD = 1024 * 1024  # 1 MB/s  — below this = throttled
    _SLOW_TRIGGER_SECS = 20  # seconds below threshold before reconnect
    _WEBDAV_READY_SECS = 20  # seconds to wait for WebDAV to come up

    def _kill_port(self):
        try:
            subprocess.run(
                ["fuser", "-k", str(self._WEBDAV_PORT) + "/tcp"],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass
        time.sleep(1)

    def _start_webdav(self) -> "subprocess.Popen | None":
        """Kill any existing WebDAV on the port, start a fresh one.
        Returns the process handle, or None on failure."""
        self._kill_port()

        log_path = f"/tmp/rclone_webdav_{self.user_id}.log"
        serve_cmd = [
            self.rclone_path,
            "--config",
            self.config_file,
            "serve",
            "webdav",
            "PIKKY:",
            "--addr",
            f"127.0.0.1:{self._WEBDAV_PORT}",
            "--read-only",
            "--no-modtime",
            "--log-level",
            "ERROR",  # quieter — we only care about fatal errors
        ]
        try:
            lfd = open(log_path, "w")
            proc = subprocess.Popen(
                serve_cmd, stdout=lfd, stderr=lfd, start_new_session=True
            )
        except Exception as e:
            self.err(f"WebDAV Popen failed: {e}")
            return None

        # Wait for server to be ready
        deadline = time.monotonic() + self._WEBDAV_READY_SECS
        while time.monotonic() < deadline:
            if self._kill_evt.is_set() or self.stop_requested:
                self._kill_process(proc)
                return None
            if proc.poll() is not None:
                self.warn("WebDAV process died immediately")
                return None
            try:
                import urllib.request as _ur

                _ur.urlopen(f"http://127.0.0.1:{self._WEBDAV_PORT}", timeout=1)
                return proc  # ready
            except Exception:
                time.sleep(0.5)

        self.warn("WebDAV did not become ready in time")
        self._kill_process(proc)
        return None

    def _gdrive_list_done(self) -> set:
        """Return set of full relative paths AND basenames confirmed on GDrive destination."""
        try:
            r = subprocess.run(
                [
                    self.rclone_path,
                    "--config",
                    self.config_file,
                    "lsf",
                    f"GDRIVE:{self.destination_folder}",
                    "--recursive",
                    "--files-only",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if r.returncode == 0:
                paths = set()
                for f in r.stdout.split("\n"):
                    f = f.strip()
                    if f:
                        paths.add(f)  # full: "My Pack/video.mp4"
                        paths.add(os.path.basename(f))  # bare: "video.mp4"
                return paths
        except Exception as e:
            self.warn(f"GDrive list failed: {e}")
        return set()

    def _build_filter_args(self, remaining: list) -> list:
        """Build rclone filter args that include only the given remaining files."""
        args = ["--filter", "+ */"]
        for f in remaining:
            basename = os.path.basename(f)
            args += ["--filter", f"+ **/{basename}"]
            args += ["--filter", f"+ {basename}"]
        args += ["--filter", "- *"]
        return args

    def _start_copy_proc(
        self, filter_args: list
    ) -> "tuple[subprocess.Popen | None, list, threading.Thread | None]":
        """Spawn rclone copy WEBDAV_* → GDRIVE:dest with given filters.
        Returns (proc, stderr_lines_list, reader_thread)."""

        webdav_remote = f"PIKPAKDAV_{self.user_id}"
        copy_cmd = [
            self.rclone_path,
            "--config",
            self.config_file,
            "copy",
            f"{webdav_remote}:",
            f"GDRIVE:{self.destination_folder}",
            "--transfers",
            "2",
            "--checkers",
            "1",  # 1 checker = far fewer GDrive API list calls
            # --no-traverse + --ignore-existing removed:
            # Together they cause rclone to stat every destination file individually
            # (one API call per file) which instantly blows GDrive's 1000 req/100s quota.
            # Instead we rely on our own _gdrive_list_done() check between sessions
            # and pass --size-only so rclone uses a single cheap list pass.
            "--size-only",  # skip hash checks — size match = done
            "--drive-chunk-size",
            "64M",  # smaller chunks = fewer bytes wasted on quota errors
            "--drive-acknowledge-abuse",
            "--drive-pacer-min-sleep",
            "200ms",  # enforce gap between every GDrive API call
            "--drive-pacer-burst",
            "5",  # allow 5 rapid calls max then pace
            "--tpslimit",
            "3",  # hard cap: 3 API transactions/sec
            "--tpslimit-burst",
            "5",
            "--buffer-size",
            "64M",
            "--use-mmap",
            "--retries",
            "1",
            "--low-level-retries",
            "3",
            "--timeout",
            "120s",
            "--contimeout",
            "30s",
            "--log-level",
            "INFO",
        ] + filter_args

        stderr_lines: list[str] = []

        try:
            proc = subprocess.Popen(
                copy_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except Exception as e:
            self.err(f"Copy proc start failed: {e}")
            return None, stderr_lines, None

        _tf_re = re.compile(r"Transferred:\s+(\d+)\s*/\s*(\d+),\s*\d+%")
        _fn_re = re.compile(r"(?:Copying|Transferring)[\s:]+(.+?)(?:\s*:|\s*$)")

        def _reader(p=proc, buf=stderr_lines, mgr=self):
            try:
                for raw in p.stderr:
                    line = raw.decode(errors="replace").rstrip()
                    if not line:
                        continue
                    buf.append(line)
                    # parse completed file count — never let it go backwards
                    m = _tf_re.search(line)
                    if m:
                        n = int(m.group(1))
                        if n > mgr.files_done:
                            mgr.files_done = n
                    # track current filename for UI
                    fn = _fn_re.search(line)
                    if fn:
                        mgr.current_file_name = fn.group(1).strip()
            except Exception:
                pass

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        return proc, stderr_lines, t

    def _ensure_webdav_remote_in_config(self):
        """Append the local WebDAV remote to config file if not already there."""
        webdav_remote = f"PIKPAKDAV_{self.user_id}"
        try:
            cfg_text = open(self.config_file).read()
        except Exception:
            cfg_text = ""
        if f"[{webdav_remote}]" not in cfg_text:
            entry = (
                f"\n[{webdav_remote}]\n"
                f"type = webdav\n"
                f"url = http://127.0.0.1:{self._WEBDAV_PORT}\n"
                f"vendor = other\n"
                f"pacer_min_sleep = 0\n"
            )
            with open(self.config_file, "a") as cf:
                cf.write(entry)

    def _do_transfer(self) -> bool:
        """
        Main transfer loop.

        Uses a WebDAV bridge (PIKKY → local WebDAV → GDrive).
        A speed watchdog monitors upload throughput every second.
        If speed drops below 1 MB/s for 5 consecutive seconds:
          - Kill rclone + WebDAV
          - Query GDrive to find which files completed
          - Restart with a fresh WebDAV session, skipping done files
        Continues until all scanned video files are on GDrive.
        """
        self._kill_evt.clear()
        self.reconnect_count = 0

        self._ensure_webdav_remote_in_config()

        # Full list of files we need to transfer
        remaining = list(self.video_files)  # files still to transfer
        done_basenames: set[str] = set()  # confirmed on GDrive

        for reconnect_idx in range(self._MAX_RECONNECTS + 1):
            if self._kill_evt.is_set() or self.stop_requested:
                return False

            if not remaining:
                self.ok("All files confirmed on GDrive ✓")
                self.files_done = len(self.video_files)
                return True

            # ── Start fresh WebDAV bridge ─────────────────────────────────
            self._edit(
                f"🔌 <b>{'Reconnecting' if reconnect_idx > 0 else 'Connecting'} WebDAV…</b>\n\n"
                f"{DIVIDER_SM}\n"
                f"📡  Session <b>#{reconnect_idx + 1}</b>  ·  "
                f"{len(remaining)}/{len(self.video_files)} files remaining",
                self._stop_kb(),
            )

            webdav_proc = self._start_webdav()
            if webdav_proc is None:
                self.warn(f"WebDAV start failed on session {reconnect_idx + 1}")
                # wait a bit and retry
                for _ in range(10):
                    if self._kill_evt.is_set() or self.stop_requested:
                        return False
                    time.sleep(1)
                continue

            self.ok(f"WebDAV session #{reconnect_idx + 1} ready")

            # ── Build filter for remaining files only ─────────────────────
            filter_args = self._build_filter_args(remaining)

            # ── Start rclone copy ─────────────────────────────────────────
            copy_proc, stderr_lines, err_thr = self._start_copy_proc(filter_args)
            if copy_proc is None:
                self._kill_process(webdav_proc)
                return False

            with self.process_lock:
                self.transfer_process = copy_proc

            # ── Speed watchdog loop ───────────────────────────────────────
            slow_seconds = 0  # consecutive seconds below threshold
            last_up_bytes = self.network_monitor.total_uploaded
            reconnect_now = False

            while True:
                if self._kill_evt.is_set() or self.stop_requested:
                    self._kill_process(copy_proc)
                    self._kill_process(webdav_proc)
                    if err_thr:
                        err_thr.join(timeout=2)
                    with self.process_lock:
                        self.transfer_process = None
                    return False

                # Check if rclone finished
                if copy_proc.poll() is not None:
                    break

                time.sleep(1)

                cur_up = self.network_monitor.total_uploaded
                delta = cur_up - last_up_bytes
                last_up_bytes = cur_up

                # Speed in B/s over this 1-second window
                speed_bps = delta  # delta bytes over ~1 second

                if speed_bps < self._SPEED_THRESHOLD:
                    slow_seconds += 1
                else:
                    slow_seconds = 0  # reset — speed is fine

                if slow_seconds >= self._SLOW_TRIGGER_SECS:
                    self.warn(
                        f"Speed {fmt_size(speed_bps)}/s < 1 MB/s for "
                        f"{self._SLOW_TRIGGER_SECS}s — triggering reconnect"
                    )
                    reconnect_now = True
                    self._kill_process(copy_proc)
                    break

            # ── rclone exited (finished or killed) ────────────────────────
            if err_thr:
                err_thr.join(timeout=5)
            rc = copy_proc.returncode if copy_proc.poll() is not None else -1

            with self.process_lock:
                self.transfer_process = None

            # Give rclone a moment to flush, then kill WebDAV
            time.sleep(2)
            self._kill_process(webdav_proc)

            # ── Check GDrive to find what actually completed ───────────────
            self.info("Checking GDrive for completed files…")
            gd_done = self._gdrive_list_done()
            done_basenames |= gd_done

            # Update files_done counter for UI — never go backwards
            confirmed = sum(
                1
                for f in self.video_files
                if f in done_basenames or os.path.basename(f) in done_basenames
            )
            if confirmed > self.files_done:
                self.files_done = confirmed

            # Rebuild remaining = files NOT yet confirmed on GDrive
            # Match against both full relative path and bare basename
            remaining = [
                f
                for f in self.video_files
                if f not in done_basenames and os.path.basename(f) not in done_basenames
            ]

            self.ok(
                f"Session {reconnect_idx + 1} done: "
                f"{confirmed}/{len(self.video_files)} on GDrive, "
                f"{len(remaining)} remaining"
            )

            # Success: all files are there
            if not remaining:
                self.files_done = len(self.video_files)
                return True

            # ── Check for fatal / unrecoverable errors ────────────────────
            err_tail = "\n".join(stderr_lines[-8:]).lower()

            FATAL_ERRORS = [
                (
                    "storagequotaexceeded",
                    "❌ <b>Google Drive Full</b>\n\nYour GDrive storage quota is exceeded.\n\n💡 Free up space at <a href='https://drive.google.com'>drive.google.com</a> then retry.",
                ),
                (
                    "invalidcredentials",
                    "❌ <b>GDrive Auth Failed</b>\n\nCredentials expired.\n\n💡 Re-run /config with a fresh rclone config.",
                ),
                (
                    "autherror",
                    "❌ <b>GDrive Auth Failed</b>\n\nCredentials expired.\n\n💡 Re-run /config with a fresh rclone config.",
                ),
                (
                    "tokenerror",
                    "❌ <b>GDrive Token Error</b>\n\nRe-run /config to refresh your GDrive token.",
                ),
            ]

            fatal_msg = None
            for keyword, msg in FATAL_ERRORS:
                if keyword in err_tail:
                    fatal_msg = msg
                    break

            if fatal_msg:
                self.err(f"Fatal error detected — aborting: {err_tail[-100:]}")
                self._edit(fatal_msg, None)
                return False

            # GDrive rate limit — wait 90s then retry (quota window = 100s)
            is_rate_limit = (
                "ratelimitexceeded" in err_tail
                or "rate limit" in err_tail
                or "userratelimitexceeded" in err_tail
            )
            if is_rate_limit:
                wait_secs = 90
                self.warn(f"GDrive rate limit — waiting {wait_secs}s before retry")
                self._edit(
                    f"⏳ <b>GDrive Rate Limit</b>\n\n"
                    f"{DIVIDER_SM}\n"
                    f"Google Drive API quota hit.\n"
                    f"Waiting <b>{wait_secs}s</b> for quota to reset…\n\n"
                    f"✅  Done: <b>{confirmed}/{len(self.video_files)}</b> files\n"
                    f"⏳  Remaining: <b>{len(remaining)}</b>",
                    self._stop_kb(),
                )
                self.reconnect_count += 1
                deadline = time.monotonic() + wait_secs
                while time.monotonic() < deadline:
                    if self._kill_evt.is_set() or self.stop_requested:
                        return False
                    time.sleep(0.5)
                continue

            # Natural rclone exit with rc=0 but files still missing → reconnect
            if rc == 0:
                self.warn("rclone exited 0 but files still missing — reconnecting")
                self.reconnect_count += 1
                time.sleep(3)
                continue

            # rc=5 = partial transfer — reconnect
            if rc == 5:
                self.reconnect_count += 1
                time.sleep(3)
                continue

            # Reconnect triggered by speed watchdog
            if reconnect_now:
                self.reconnect_count += 1
                self._edit(
                    f"🔁 <b>Reconnecting…</b>  (#{self.reconnect_count})\n\n"
                    f"{DIVIDER_SM}\n"
                    f"✅  Done: <b>{confirmed}/{len(self.video_files)}</b> files\n"
                    f"⏳  Remaining: <b>{len(remaining)}</b> files\n\n"
                    f"Starting fresh WebDAV session…",
                    self._stop_kb(),
                )
                time.sleep(2)
                continue

            # Any other non-zero exit — still reconnect if files remain
            self.warn(
                f"rclone rc={rc}, {len(remaining)} files still missing — reconnecting"
            )
            self.reconnect_count += 1
            raw_tail = "\n".join(stderr_lines[-4:])
            if raw_tail:
                self.warn(f"Last rclone output: {raw_tail[-200:]}")
            time.sleep(5)
            continue

        # Exhausted reconnect limit
        self.err(f"Exhausted {self._MAX_RECONNECTS} reconnect attempts.")
        return len(remaining) == 0

    def stop(self):
        self.stop_requested = True
        self.transfer_in_progress = False
        self._kill_evt.set()
        self.network_monitor.stop()

    def _status_loop(self):
        STATUS_INTERVAL = 15.0
        MAX_CONSEC_FAILS = 3
        consec_fails = 0
        while self.transfer_in_progress and not self.stop_requested:
            try:
                self._edit(self.render_status("transferring"), self._live_kb())
                consec_fails = 0
            except Exception as e:
                consec_fails += 1
                print(f"[status_loop] edit failed ({consec_fails}): {e}")
                if consec_fails >= MAX_CONSEC_FAILS:
                    return
            deadline = time.monotonic() + STATUS_INTERVAL
            while time.monotonic() < deadline:
                if not self.transfer_in_progress or self.stop_requested:
                    return
                time.sleep(0.5)

    def run(self):
        self.transfer_in_progress = True
        self.stop_requested = False
        self._kill_evt.clear()
        self.start_time = datetime.now()
        status = "failed"
        error_msg = None
        transferred_size = "Unknown"
        speed = "0 B/s"

        try:
            self.head(
                f"PikPak→GDrive | User {self.user_id} | {fmt_dt(self.start_time)}"
            )

            if not self._install_rclone():
                error_msg = "rclone install failed"
                self._edit(
                    "❌ <b>Setup Failed</b>\n\nCouldn't install rclone. Try again."
                )
                return

            self._write_config()

            if not self._verify_remotes():
                error_msg = "Remote connection failed"
                self._edit(
                    "❌ <b>Connection Failed</b>\n\n"
                    f"{DIVIDER_SM}\n"
                    "Could not connect to PIKKY or GDRIVE.\n\n"
                    "💡 Re-check your config with /config."
                )
                return

            self._edit(self.render_status("scanning"), self._stop_kb())
            if not self._scan_videos():
                if self.stop_requested:
                    status = "cancelled"
                    return
                self._edit(
                    "⚠️ <b>No Videos Found</b>\n\n"
                    f"{DIVIDER_SM}\n"
                    "PikPak doesn't have any video files in the root.\n\n"
                    "💡 Add videos to PikPak first, then /upload again."
                )
                return

            if self.stop_requested:
                status = "cancelled"
                return

            self.destination_folder = (
                f"{generate_alien_name()}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )

            self.network_monitor.start()
            threading.Thread(target=self._status_loop, daemon=True).start()

            success = self._do_transfer()
            self.transfer_in_progress = False
            self.network_monitor.stop()

            ns = self.network_monitor.get_stats()
            transferred_size = (
                self.total_size_str
                if self.total_size_str not in ("Unknown", "")
                else ns["total_uploaded"]
            )
            elapsed_secs = (
                (datetime.now() - self.network_monitor.start_time).total_seconds()
                if self.network_monitor.start_time
                else 0
            )
            active_secs = max(elapsed_secs - 10, 1)
            avg_bps = (
                self.network_monitor.total_uploaded / active_secs
                if elapsed_secs > 0
                else 0
            )
            avg_speed = NetworkMonitor._fmt_speed(avg_bps)
            speed = avg_speed

            if self.stop_requested:
                status = "cancelled"
                self._edit(
                    "⏹  <b>Transfer Cancelled</b>\n\n"
                    f"{DIVIDER_SM}\n"
                    f"📤  Uploaded   <b>{transferred_size}</b>\n"
                    f"🎬  Videos     <b>{len(self.video_files)}</b>\n"
                    f"⏱   Elapsed    <b>{ns['elapsed']}</b>\n"
                    f"{DIVIDER_SM}\n\n"
                    "Start a new one anytime with /upload"
                )
            elif success:
                status = "completed"
                duration = str(datetime.now() - self.start_time).split(".")[0]
                reconnect_note = (
                    f"\n🔁  Reconnects  <b>{self.reconnect_count}</b>"
                    if self.reconnect_count > 0
                    else ""
                )
                self._edit(
                    "🎉 <b>Transfer Complete!</b>\n\n"
                    f"{DIVIDER_SM}\n"
                    f"📤  Uploaded   <b>{transferred_size}</b>\n"
                    f"⚡  Avg Upload  <b>{avg_speed}</b>\n"
                    f"🎬  Videos     <b>{len(self.video_files)}</b>\n"
                    f"⏱   Duration   <b>{duration}</b>{reconnect_note}\n"
                    f"{DIVIDER_SM}\n\n"
                    f"📂 <code>GD:{safe_escape(self.destination_folder)}</code>\n\n"
                    "💡 Use /sendfiles to receive files in Telegram."
                )
            else:
                status = "failed"
                error_msg = "Transfer incomplete after max reconnects"
                # Surface the last meaningful log line to the user
                last_err = next(
                    (l for l in reversed(self.logs) if "❌" in l or "⚠️" in l), ""
                )
                self._edit(
                    "❌ <b>Transfer Failed</b>\n\n"
                    f"{DIVIDER_SM}\n"
                    f"📤  Uploaded   <b>{transferred_size}</b>\n"
                    f"🎬  Videos     <b>{len(self.video_files)}</b>  "
                    f"·  <b>{self.files_done}</b> completed\n"
                    f"🔁  Reconnects <b>{self.reconnect_count}</b>\n"
                    f"{DIVIDER_SM}\n\n"
                    + (
                        f"<code>{safe_escape(last_err[-200:])}</code>"
                        if last_err
                        else ""
                    )
                )

        except Exception as e:
            self.err(f"Unexpected: {e}")
            error_msg = str(e)
            self._edit(
                f"❌ <b>Unexpected Error</b>\n\n<code>{safe_escape(str(e))}</code>"
            )
        finally:
            self.transfer_in_progress = False
            try:
                self.network_monitor.stop()
            except:
                pass
            UserManager.save_transfer(
                self.user_id,
                status,
                self.start_time,
                datetime.now(),
                self.destination_folder,
                len(self.video_files),
                self.total_size_str,
                transferred_size,
                speed,
                error_msg,
            )


# ? ─── Global Transfer State ────────────────────────────────────────────────────

managers: dict[int, TransferManager] = {}


def get_rclone_path(user_id):
    return os.path.expanduser(f"~/.local/bin/rclone_{user_id}")


def get_config_file(user_id):
    return os.path.expanduser(f"~/.config/rclone/user_{user_id}.conf")


def ensure_rclone(user_id, message):
    config = UserManager.get_config(user_id)
    if not config:
        bot.reply_to(message, "❌ No config. Use /config first.", parse_mode="HTML")
        return None, None
    rclone_path = get_rclone_path(user_id)
    config_file = get_config_file(user_id)
    if not os.path.exists(rclone_path):
        try:
            tmp = TransferManager(user_id, message.chat.id)
            tmp._install_rclone()
            if not os.path.exists(rclone_path):
                bot.reply_to(message, "❌ rclone install failed.", parse_mode="HTML")
                return None, None
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}", parse_mode="HTML")
            return None, None
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w") as f:
        f.write(config)
    return rclone_path, config_file


def run_rclone(rclone_path, config_file, *args, timeout=120):
    cmd = [rclone_path, "--config", config_file] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


# . ─── Help & Guide Content ─────────────────────────────────────────────────────

GDRIVE_BINARY_LINK = "https://drive.google.com/file/d/1ti94G9SFsLec2zMn08RoQ5EhgGVJoDiA/view?usp=drivesdk"
GDRIVE_DIRECT_DL = "https://drive.google.com/uc?export=download&id=1ti94G9SFsLec2zMn08RoQ5EhgGVJoDiA&confirm=t"


def _home_text(user_id: int) -> str:
    config_ok = UserManager.get_config(user_id) is not None
    api_active = _using_local_api
    config_badge = "🟢 Config saved" if config_ok else "❌ No config — use /config"
    api_badge = (
        f"🟢 Local API active  ·  up to <b>{fmt_size(MAX_SEND_BYTES())}</b>"
        if api_active
        else f"🟡 Official API  ·  up to <b>{fmt_size(MAX_SEND_BYTES())}</b>  (→ /localapi for 2 GB)"
    )
    return (
        "🛸 <b>PikPak → GDrive Ultra Bot</b>\n"
        "<i>Transfer your PikPak videos to Google Drive at max speed.</i>\n\n"
        f"{DIVIDER}\n"
        f"{config_badge}\n"
        f"{api_badge}\n"
        f"{DIVIDER}\n\n"
        "📋 <b>QUICK START</b>\n\n"
        "  1️⃣  /config   →  paste your rclone config\n\n"
        "  2️⃣  /upload   →  start the transfer\n\n"
        "  3️⃣  /sendfiles →  receive files in Telegram\n\n"
        f"{DIVIDER}\n"
        "📌 <b>ALL COMMANDS</b>\n\n"
        "  /config      save rclone config\n"
        "  /upload      start PikPak → GDrive\n"
        "  /stop        kill transfer instantly\n"
        "  /status      live network stats\n"
        "  /drive       GDrive storage stats\n"
        "  /drivvy      list GDrive files\n"
        "  /pikky       PikPak storage + videos\n"
        "  /sendfiles   download GDrive → Telegram\n"
        "  /settings    video vs document mode\n"
        "  /localapi    2 GB upload setup\n"
        "  /history     past transfers\n"
        "  /guide       full setup guide\n\n"
        f"{DIVIDER}\n"
        "⚙️ <i>WebDAV bridge · auto-reconnect · smart speed watchdog</i>"
    )


def _guide_menu_text() -> str:
    return (
        "📖 <b>↓ Below is the FULL Setup Guide ↓</b> 📖\n\n"
        f"{DIVIDER_SM}\n"
        "↓ Pick a topic to read more ↓"
    )


GUIDE_PAGES = {
    "rclone": (
        "⚙️ <b>Step 1 — rclone Config</b>\n\n"
        f"{DIVIDER_SM}\n"
        "<b>METHOD A — Terminal</b>\n\n"
        "<code>curl https://rclone.org/install.sh | sudo bash\nrclone config</code>\n\n"
        "Add PikPak remote:\n"
        "<code>name&gt; PIKKY\nStorage&gt; pikpak\n</code>\n\n"
        "Add GDrive remote:\n"
        "<code>name&gt; GDRIVE\nStorage&gt; drive\n</code>\n\n"
        "Export:\n<code>cat ~/.config/rclone/rclone.conf</code>\n\n"
        f"{DIVIDER_SM}\n"
        "<b>METHOD B — rclone.dev (no terminal)</b>\n\n"
        "1. Go to <a href='https://rclone.dev'>rclone.dev</a>\n"
        "2. Add PikPak (<code>PIKKY</code>) + GDrive (<code>GDRIVE</code>)\n"
        "3. Export config → /config\n\n"
        "⚠️ Remote names must be <code>PIKKY</code> and <code>GDRIVE</code> exactly."
    ),
    "binary": (
        f"🖥 <b>Step 2 — Local API Binary</b>\n\n"
        f"{DIVIDER_SM}\n"
        "Unlocks <b>2 GB</b> uploads (default: 50 MB).\n\n"
        "<b>OPTION A — URL download</b>\n\n"
        "1. Send /localapi\n"
        "2. Tap ⬇️ Download binary from URL\n"
        f"3. Paste: <code>{GDRIVE_DIRECT_DL}</code>\n\n"
        "<b>OPTION B — Upload file</b>\n\n"
        f"Download from <a href='{GDRIVE_BINARY_LINK}'>Google Drive</a> → upload here via /localapi\n\n"
        f"{DIVIDER_SM}\n"
        "<b>After installing binary</b>\n\n"
        "Get credentials from <a href='https://my.telegram.org'>my.telegram.org</a>\n"
        "  → API development tools → create app\n"
        "  → copy api_id + api_hash\n"
        "  → /localapi → Enter credentials"
    ),
    "transfer": (
        "🚀 <b>Step 3 — Running Transfers</b>\n\n"
        f"{DIVIDER_SM}\n"
        "<b>START</b>\n\n"
        "  1. /config — set your config\n"
        "  2. /upload — bot scans PikPak\n"
        "  3. Live card updates every 15 s\n\n"
        f"{DIVIDER_SM}\n"
        "<b>STOP</b>\n\n"
        "Tap ⏹ Stop on the card or send /stop.\n\n"
        f"{DIVIDER_SM}\n"
        "<b>SEND TO TELEGRAM</b>\n\n"
        "Use /sendfiles → pick a folder → files arrive here.\n"
        "Use /settings to choose video or document mode.\n\n"
        f"{DIVIDER_SM}\n"
        "<b>COMMON ERRORS</b>\n\n"
        "• <b>captcha_invalid</b> — log into PikPak from same IP, wait, retry.\n"
        "• <b>GDRIVE token expired</b> — redo rclone config for GDRIVE.\n"
        "• <b>File too large</b> — set up /localapi for 2 GB limit."
    ),
    "captcha": (
        "🛡 <b>Fixing PikPak Captcha Errors</b>\n\n"
        f"{DIVIDER_SM}\n"
        "<b>FIX 1 — Manual login</b>\n\n"
        "Log into PikPak in a browser on the same network as your bot, then retry /upload.\n\n"
        "<b>FIX 2 — Recreate PIKKY</b>\n\n"
        "<code>rclone config</code> → overwrite PIKKY → /config again.\n\n"
        "<b>FIX 3 — Community fork</b>\n\n"
        "Search GitHub for <i>rclone pikpak captcha bypass</i> for community forks."
    ),
}


def _guide_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("⚙️ rclone config", callback_data=f"guide_rclone_{user_id}")
    )
    kb.row(
        InlineKeyboardButton(
            "🖥 Local API binary", callback_data=f"guide_binary_{user_id}"
        )
    )
    kb.row(
        InlineKeyboardButton(
            "🚀 Running transfers", callback_data=f"guide_transfer_{user_id}"
        )
    )
    kb.row(
        InlineKeyboardButton(
            "🛡 Fix PikPak captcha", callback_data=f"guide_captcha_{user_id}"
        )
    )
    return kb


def _back_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(
            "« Back to guide menu", callback_data=f"guide_menu_{user_id}"
        )
    )
    return kb


# * ─── /start ───────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["start", "help"])
def cmd_start(message: Message):
    user_id = message.from_user.id
    if not UserManager.exists(user_id):
        UserManager.save_user(
            user_id,
            message.from_user.username or "",
            message.from_user.first_name or "",
            None,
        )
    text = _home_text(user_id)
    kb = _guide_kb(user_id)
    MsgStore.delete_msg(user_id, "home")
    sent = send_msg(message.chat.id, text, reply_markup=kb, parse_mode="HTML")
    if sent:
        MsgStore.save(user_id, "home", message.chat.id, sent.message_id)


@bot.message_handler(commands=["guide"])
def cmd_guide(message: Message):
    user_id = message.from_user.id
    MsgStore.delete_msg(user_id, "guide")
    sent = send_msg(
        message.chat.id,
        _guide_menu_text(),
        reply_markup=_guide_kb(user_id),
        parse_mode="HTML",
    )
    if sent:
        MsgStore.save(user_id, "guide", message.chat.id, sent.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("guide_menu_"))
def cb_guide_menu(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    edit_msg(
        call.message.chat.id,
        call.message.message_id,
        _guide_menu_text(),
        reply_markup=_guide_kb(user_id),
    )
    MsgStore.save(user_id, "guide", call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("guide_") and not c.data.startswith("guide_menu_")
)
def cb_guide(call: CallbackQuery):
    parts = call.data.split("_")
    topic = parts[1]
    user_id = int(parts[2])
    text = GUIDE_PAGES.get(topic, "❓ Unknown topic.")
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    edit_msg(
        call.message.chat.id,
        call.message.message_id,
        text,
        reply_markup=_back_kb(user_id),
        parse_mode="HTML",
    )


# * ─── /config ──────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["config"])
def cmd_config(message: Message):
    MsgStore.delete_msg(message.from_user.id, "config_prompt")
    sent = send_msg(
        message.chat.id,
        "📋 <b>Send your rclone config</b>\n\n"
        f"{DIVIDER_SM}\n"
        "Paste config text or upload a <code>.conf</code> file.\n\n"
        "Required remote names:\n"
        "  🔹  PikPak       → <code>[PIKKY]</code>\n"
        "  🔹  Google Drive → <code>[GDRIVE]</code>\n\n"
        "Send /cancel to abort.",
    )
    if sent:
        MsgStore.save(
            message.from_user.id, "config_prompt", message.chat.id, sent.message_id
        )
        bot.register_next_step_handler(sent, _process_config)


def _process_config(message: Message):
    user_id = message.from_user.id
    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        MsgStore.delete_msg(user_id, "config_prompt")
        send_msg(message.chat.id, "❌ Config setup cancelled.")
        return
    try:
        if message.content_type == "text":
            config = (message.text or "").strip()
            if not config:
                sent = send_msg(
                    message.chat.id, "❌ Config is empty. Send again or /cancel."
                )
                if sent:
                    bot.register_next_step_handler(sent, _process_config)
                return
        elif message.content_type == "document":
            import urllib.request as _ur, json as _json

            fid = message.document.file_id
            r = _ur.urlopen(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={fid}",
                timeout=15,
            )
            fp = _json.loads(r.read())["result"]["file_path"]
            with _ur.urlopen(
                f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}", timeout=30
            ) as resp:
                config = resp.read().decode("utf-8").strip()
        else:
            sent = send_msg(message.chat.id, "❌ Send config as text or .conf file.")
            if sent:
                bot.register_next_step_handler(sent, _process_config)
            return

        if "[PIKKY]" not in config or "[GDRIVE]" not in config:
            sent = send_msg(
                message.chat.id,
                "⚠️ <b>Config looks wrong!</b>\n\n"
                "Must contain both <code>[PIKKY]</code> and <code>[GDRIVE]</code> sections.\n\n"
                "Send the correct one or use /guide for help.",
            )
            if sent:
                bot.register_next_step_handler(sent, _process_config)
            return

        UserManager.save_user(
            user_id,
            message.from_user.username or "",
            message.from_user.first_name or "",
            config,
        )
        MsgStore.delete_msg(user_id, "config_prompt")
        send_msg(
            message.chat.id,
            "✅ <b>Config saved!</b>\n\n"
            f"{DIVIDER_SM}\n"
            "Both remotes detected ✓\n\n"
            "Ready to go — use /upload to start transferring.",
        )
    except Exception as e:
        print(f"[_process_config] {e}")
        sent = send_msg(
            message.chat.id,
            f"❌ Error saving config: <code>{safe_escape(str(e))}</code>\n\nTry /config again.",
        )
        if sent:
            bot.register_next_step_handler(sent, _process_config)


#! ─── /upload ──────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["upload"])
def cmd_upload(message: Message):
    user_id = message.from_user.id
    if not UserManager.get_config(user_id):
        bot.reply_to(message, "❌ No config. Use /config first.", parse_mode="HTML")
        return
    if user_id in managers and managers[user_id].transfer_in_progress:
        bot.reply_to(
            message,
            "⚠️ Transfer already running.\n\nUse /status or /stop.",
            parse_mode="HTML",
        )
        return
    try:
        mgr = TransferManager(user_id, message.chat.id)
    except ValueError as e:
        bot.reply_to(message, f"❌ {e}", parse_mode="HTML")
        return

    managers[user_id] = mgr
    sent = send_msg(
        message.chat.id,
        "🚀 <b>Transfer Starting…</b>\n\n" f"{DIVIDER_SM}\n" "⏳ Initialising rclone…",
    )
    if sent:
        mgr.status_msg_id = sent.message_id
        MsgStore.save(user_id, "status", message.chat.id, sent.message_id)
    threading.Thread(target=mgr.run, daemon=True).start()


# ? ─── /stop ────────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["stop"])
def cmd_stop(message: Message):
    user_id = message.from_user.id
    mgr = managers.get(user_id)
    if not mgr or not mgr.transfer_in_progress:
        bot.reply_to(message, "⚠️ No active transfer.", parse_mode="HTML")
        return
    ns = mgr.network_monitor.get_stats()
    mgr.stop()
    bot.reply_to(
        message,
        "⏹  <b>Transfer Stopped</b>\n\n"
        f"{DIVIDER_SM}\n"
        f"📤  Uploaded   <b>{ns['total_uploaded']}</b>\n"
        f"⚡  Speed      <b>{ns['upload_speed']}</b>\n"
        f"⏱   Elapsed    <b>{ns['elapsed']}</b>",
        parse_mode="HTML",
    )


# $ ─── /status ──────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["status"])
def cmd_status(message: Message):
    user_id = message.from_user.id
    mgr = managers.get(user_id)
    if not mgr or not mgr.transfer_in_progress:
        bot.reply_to(message, "⚠️ No active transfer running.", parse_mode="HTML")
        return
    MsgStore.delete_msg(user_id, "status")
    if mgr.status_msg_id:
        delete_msg(mgr.chat_id, mgr.status_msg_id)
        mgr.status_msg_id = None
    sent = send_msg(
        message.chat.id, mgr.render_status("transferring"), reply_markup=mgr._live_kb()
    )
    if sent:
        mgr.status_msg_id = sent.message_id
        mgr.chat_id = message.chat.id
        MsgStore.save(user_id, "status", message.chat.id, sent.message_id)


# * ─── Inline callbacks ─────────────────────────────────────────────────────────


@bot.callback_query_handler(func=lambda c: c.data.startswith("refresh_"))
def cb_refresh(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    mgr = managers.get(user_id)
    if not mgr or not mgr.transfer_in_progress:
        try:
            bot.answer_callback_query(call.id, "No active transfer.", show_alert=True)
        except:
            pass
        return
    ok = edit_msg(
        call.message.chat.id,
        call.message.message_id,
        mgr.render_status("transferring"),
        reply_markup=mgr._live_kb(),
    )
    try:
        bot.answer_callback_query(
            call.id, "✅ Refreshed!" if ok else "Already up to date."
        )
    except:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("stop_"))
def cb_stop(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    mgr = managers.get(user_id)
    if not mgr or not mgr.transfer_in_progress:
        try:
            bot.answer_callback_query(call.id, "No active transfer.", show_alert=True)
        except:
            pass
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id, call.message.message_id, reply_markup=None
            )
        except:
            pass
        return
    ns = mgr.network_monitor.get_stats()
    mgr.stop()
    mgr.status_msg_id = None
    try:
        bot.answer_callback_query(call.id, "⏹  Stopped.")
    except:
        pass
    edit_msg(
        call.message.chat.id,
        call.message.message_id,
        "⏹  <b>Transfer Cancelled</b>\n\n"
        f"{DIVIDER_SM}\n"
        f"📤  Uploaded   <b>{ns['total_uploaded']}</b>\n"
        f"⚡  Speed      <b>{ns['upload_speed']}</b>\n"
        f"⏱   Elapsed    <b>{ns['elapsed']}</b>\n"
        f"{DIVIDER_SM}\n\n"
        "<i>Use /upload to start a new transfer.</i>",
        reply_markup=None,
    )


#! ─── /localapi ────────────────────────────────────────────────────────────────

_GUIDE_TEXT = (
    "📖 <b>How to get Telegram API credentials</b>\n\n"
    f"{DIVIDER_SM}\n"
    "1. Open <a href='https://my.telegram.org'>my.telegram.org</a>\n"
    "2. Log in → click <b>API development tools</b>\n"
    "3. Create any app → copy <b>api_id</b> + <b>api_hash</b>\n\n"
    "⚠️ Keep these private — they're tied to your Telegram account."
)


def _build_localapi_text_and_kb(user_id: int):
    api_id, api_hash = UserManager.get_api_credentials(user_id)

    if _using_local_api:
        status = "🟢 <b>Local API is RUNNING</b>  ·  2 GB uploads active."
    elif os.path.isfile(LOCAL_API_BIN):
        status = (
            "🟡 <b>Binary found, credentials saved</b>  ·  server not running."
            if api_id and api_hash
            else "🔴 <b>Binary found, but no credentials saved.</b>"
        )
    else:
        status = "🔴 <b>Binary not found.</b>\n\nUse the button below to download it."

    creds_line = ""
    if api_id:
        masked = ("*" * 8) + (api_hash[-4:] if api_hash else "")
        creds_line = (
            f"\n\n🔑 Saved: ID <code>{safe_escape(api_id)}</code>"
            f" · hash <code>{masked}</code>"
        )

    text = (
        "🖥 <b>Local Bot API Setup</b>\n\n"
        f"{DIVIDER_SM}\n"
        f"{status}{creds_line}\n"
        f"{DIVIDER_SM}\n\n"
        "📦  Official API : <b>50 MB</b> max\n"
        "📦  Local API    : <b>2 GB</b> max"
    )

    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(
            "📖 How to get credentials", callback_data=f"localapi_guide_{user_id}"
        )
    )
    kb.row(
        InlineKeyboardButton(
            "⬇️ Download binary from URL", callback_data=f"localapi_dlbin_{user_id}"
        )
    )
    if os.path.isfile(LOCAL_API_BIN):
        kb.row(
            InlineKeyboardButton(
                "🔑 Enter / Update credentials",
                callback_data=f"localapi_enter_{user_id}",
            )
        )
    if api_id and api_hash and os.path.isfile(LOCAL_API_BIN) and not _using_local_api:
        kb.row(
            InlineKeyboardButton(
                "▶ Start Local API now", callback_data=f"localapi_start_{user_id}"
            )
        )
    if _using_local_api:
        kb.row(
            InlineKeyboardButton(
                "🔄 Restart Local API", callback_data=f"localapi_start_{user_id}"
            )
        )
    return text, kb


@bot.message_handler(commands=["localapi"])
def cmd_localapi(message: Message):
    user_id = message.from_user.id
    text, kb = _build_localapi_text_and_kb(user_id)
    MsgStore.delete_msg(user_id, "localapi")
    sent = send_msg(message.chat.id, text, reply_markup=kb, parse_mode="HTML")
    if sent:
        MsgStore.save(user_id, "localapi", message.chat.id, sent.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("localapi_guide_"))
def cb_localapi_guide(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    back_kb = InlineKeyboardMarkup()
    back_kb.row(
        InlineKeyboardButton("« Back", callback_data=f"localapi_back_{user_id}")
    )
    edit_msg(
        call.message.chat.id,
        call.message.message_id,
        _GUIDE_TEXT,
        reply_markup=back_kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("localapi_back_"))
def cb_localapi_back(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    text, kb = _build_localapi_text_and_kb(user_id)
    edit_msg(
        call.message.chat.id,
        call.message.message_id,
        text,
        reply_markup=kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("localapi_dlbin_"))
def cb_localapi_dlbin(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    sent = send_msg(
        call.message.chat.id,
        "⬇️ <b>Download telegram-bot-api binary</b>\n\n"
        f"{DIVIDER_SM}\n"
        "Send a download URL or upload the file directly.\n\n"
        f"Known working link:\n<code>{GDRIVE_DIRECT_DL}</code>\n\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
    )
    if sent:
        bot.register_next_step_handler(sent, _localapi_dlbin_receive, user_id)


def _gdrive_direct_url(share_url: str) -> str:
    m = re.search(r"/d/([a-zA-Z0-9_-]{20,})", share_url)
    if not m:
        m = re.search(r"[?&]id=([a-zA-Z0-9_-]{20,})", share_url)
    if not m:
        return share_url
    return f"https://drive.google.com/uc?export=download&id={m.group(1)}&confirm=t"


def _download_binary(
    url: str, dest_path: str, status_msg_id: int, chat_id: int
) -> bool:
    if "drive.google.com" in url:
        url = _gdrive_direct_url(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            last_edit = 0
            os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
            with open(dest_path, "wb") as out:
                while True:
                    data = resp.read(65536)
                    if not data:
                        break
                    out.write(data)
                    downloaded += len(data)
                    now = time.time()
                    if now - last_edit >= 3 and total:
                        pct = int(100 * downloaded / total)
                        bar = make_bar(int(BAR_DL * downloaded / total), BAR_DL)
                        edit_msg(
                            chat_id,
                            status_msg_id,
                            f"⬇️ <b>Downloading binary…</b>\n\n"
                            f"<code>[{bar}]</code>  {pct}%\n"
                            f"{fmt_size(downloaded)} / {fmt_size(total)}",
                        )
                        last_edit = now
        size = os.path.getsize(dest_path)
        if size < 1024:
            os.remove(dest_path)
            return False
        st = os.stat(dest_path)
        os.chmod(dest_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return True
    except Exception as e:
        print(f"[dlbin] {e}")
        try:
            os.remove(dest_path)
        except:
            pass
        return False


def _localapi_dlbin_receive(message: Message, user_id: int):
    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        bot.reply_to(message, "❌ Cancelled.")
        return
    chat_id = message.chat.id
    dest = os.path.join(SCRIPT_DIR, "telegram-bot-api")

    if message.content_type == "document":
        status = bot.reply_to(
            message, "⬇️ <b>Downloading uploaded file…</b>", parse_mode="HTML"
        )
        try:
            import json as _json

            fid = message.document.file_id
            r = urllib.request.urlopen(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={fid}",
                timeout=15,
            )
            fp = _json.loads(r.read())["result"]["file_path"]
            ok = _download_binary(
                f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}",
                dest,
                status.message_id,
                chat_id,
            )
        except Exception as e:
            ok = False
            print(f"[dlbin upload] {e}")
        _finish_binary_download(chat_id, user_id, status.message_id, ok, dest)
        return

    url = (message.text or "").strip()
    if not url.startswith("http"):
        sent = bot.reply_to(
            message,
            "⚠️ That doesn't look like a URL.\nSend a link or upload the binary.\n\nSend /cancel to abort.",
            parse_mode="HTML",
        )
        bot.register_next_step_handler(sent, _localapi_dlbin_receive, user_id)
        return

    status = bot.reply_to(message, "⬇️ <b>Starting download…</b>", parse_mode="HTML")
    threading.Thread(
        target=lambda: _finish_binary_download(
            chat_id,
            user_id,
            status.message_id,
            _download_binary(url, dest, status.message_id, chat_id),
            dest,
        ),
        daemon=True,
    ).start()


def _finish_binary_download(chat_id, user_id, status_msg_id, ok, dest):
    global LOCAL_API_BIN
    if not ok:
        edit_msg(
            chat_id,
            status_msg_id,
            "❌ <b>Download failed.</b>\n\nCheck the link and try again via /localapi.",
        )
        return
    LOCAL_API_BIN = dest
    size = os.path.getsize(dest)
    edit_msg(
        chat_id,
        status_msg_id,
        f"✅ <b>Binary downloaded!</b>\n\n"
        f"📁  <code>{safe_escape(dest)}</code>\n"
        f"💾  {fmt_size(size)}\n\n"
        "Use /localapi to enter credentials and start the server.",
    )
    api_id, api_hash = UserManager.get_api_credentials(user_id)
    if api_id and api_hash:
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton(
                "▶ Start Local API now", callback_data=f"localapi_start_{user_id}"
            )
        )
        send_msg(
            chat_id, "🔑 Credentials already saved. Start the server?", reply_markup=kb
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith("localapi_enter_"))
def cb_localapi_enter(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    sent = send_msg(
        call.message.chat.id,
        "🔑 <b>Step 1 of 2 — API ID</b>\n\n"
        "Send your <b>API ID</b> (numbers only).\n\nSend /cancel to abort.",
    )
    if sent:
        bot.register_next_step_handler(sent, _localapi_step1_api_id, user_id)


def _localapi_step1_api_id(message: Message, user_id: int):
    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        bot.reply_to(message, "❌ Cancelled.")
        return
    raw = "".join((message.text or "").split())
    if not raw.isdigit():
        sent = bot.reply_to(
            message,
            f"⚠️ API ID must be numbers only.\nGot: <code>{safe_escape(raw[:50])}</code>\n\nTry again or /cancel.",
            parse_mode="HTML",
        )
        bot.register_next_step_handler(sent, _localapi_step1_api_id, user_id)
        return
    sent = bot.reply_to(
        message,
        f"✅ API ID: <code>{safe_escape(raw)}</code>\n\n"
        "🔑 <b>Step 2 of 2 — API Hash</b>\n\n"
        "Send your <b>API Hash</b> (32-char hex).\n\nSend /cancel to abort.",
        parse_mode="HTML",
    )
    bot.register_next_step_handler(sent, _localapi_step2_api_hash, user_id, raw)


def _localapi_step2_api_hash(message: Message, user_id: int, api_id: str):
    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        bot.reply_to(message, "❌ Cancelled.")
        return
    raw = "".join((message.text or "").split()).lower()
    if not re.fullmatch(r"[0-9a-f]{32}", raw):
        sent = bot.reply_to(
            message,
            f"⚠️ Hash must be 32 hex chars.\nGot: <code>{safe_escape(raw[:50])}</code> ({len(raw)} chars)\n\nTry again or /cancel.",
            parse_mode="HTML",
        )
        bot.register_next_step_handler(sent, _localapi_step2_api_hash, user_id, api_id)
        return
    UserManager.save_api_credentials(user_id, api_id, raw)
    bot.reply_to(
        message,
        f"✅ <b>Credentials saved!</b>\n\n"
        f"🔑 ID    <code>{safe_escape(api_id)}</code>\n"
        f"🔑 Hash  <code>{'*'*24}{raw[-8:]}</code>\n\n▶ Starting local API…",
        parse_mode="HTML",
    )
    threading.Thread(
        target=_restart_local_api_with_creds,
        args=(message.chat.id, user_id, api_id, raw),
        daemon=True,
    ).start()


def _restart_local_api_with_creds(chat_id, user_id, api_id, api_hash):
    global _using_local_api
    import telebot.apihelper as _ah

    stop_local_api()
    time.sleep(1)
    success = start_local_api(BOT_TOKEN, api_id=api_id, api_hash=api_hash)
    if success:
        _ah.API_URL = f"http://127.0.0.1:{LOCAL_API_PORT}/bot{{0}}/{{1}}"
        _using_local_api = True
        send_msg(
            chat_id,
            f"🎉 <b>Local Bot API is RUNNING!</b>\n\n"
            f"{DIVIDER_SM}\n"
            f"📦  Upload limit  <b>2 GB</b>\n"
            f"🖥   Server port   <code>{LOCAL_API_PORT}</code>\n\n"
            "Use /sendfiles to receive large video files.",
        )
    else:
        # Ensure we're fully back on official API if local failed
        _ah.API_URL = "https://api.telegram.org/bot{0}/{1}"
        _using_local_api = False
        log_file = os.path.join(SCRIPT_DIR, "tg_api_data", "server.log")
        try:
            tail = open(log_file).read()[-600:].strip()
        except Exception:
            tail = "(no log)"
        send_msg(
            chat_id,
            "❌ <b>Local API failed to start.</b>\n\n"
            f"<b>Log:</b>\n<pre>{safe_escape(tail[-400:])}</pre>\n\nUse /localapi to retry.",
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith("localapi_start_"))
def cb_localapi_start(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])
    try:
        bot.answer_callback_query(call.id, "▶ Starting…")
    except:
        pass
    api_id, api_hash = UserManager.get_api_credentials(user_id)
    if not api_id or not api_hash:
        send_msg(
            call.message.chat.id,
            "❌ No credentials. Use /localapi → Enter credentials first.",
        )
        return
    send_msg(call.message.chat.id, "⏳ Starting local Bot API server…")
    threading.Thread(
        target=_restart_local_api_with_creds,
        args=(call.message.chat.id, user_id, api_id, api_hash),
        daemon=True,
    ).start()


# $ ─── /settings ────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["settings"])
def cmd_settings(message: Message):
    user_id = message.from_user.id
    send_as = UserManager.get_settings(user_id).get("send_as", "video")
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(
            f"{'🟢 ' if send_as=='video'    else ''}🎬 Video",
            callback_data=f"set_sendas_{user_id}_video",
        ),
        InlineKeyboardButton(
            f"{'🟢 ' if send_as=='document' else ''}📄 Document",
            callback_data=f"set_sendas_{user_id}_document",
        ),
    )
    text = (
        "⚙️ <b>Settings</b>\n\n"
        f"{DIVIDER_SM}\n"
        f"📡  API mode  <b>{'Local (up to 2 GB)' if _using_local_api else 'Official (up to 50 MB)'}</b>\n\n"
        "<b>Send files as:</b>\n\n"
        "🎬  <b>Video</b>    — inline player, thumbnails\n"
        "📄  <b>Document</b> — raw file, no re-encoding\n\n"
        f"<b>Current:</b>  <code>{send_as}</code>"
    )
    MsgStore.delete_msg(user_id, "settings")
    sent = send_msg(message.chat.id, text, reply_markup=kb)
    if sent:
        MsgStore.save(user_id, "settings", message.chat.id, sent.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("set_sendas_"))
def cb_set_sendas(call: CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    value = parts[3]
    UserManager.set_setting(user_id, "send_as", value)
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(
            f"{'🟢 ' if value=='video'    else ''}🎬 Video",
            callback_data=f"set_sendas_{user_id}_video",
        ),
        InlineKeyboardButton(
            f"{'🟢 ' if value=='document' else ''}📄 Document",
            callback_data=f"set_sendas_{user_id}_document",
        ),
    )
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id, reply_markup=kb
        )
    except:
        pass
    try:
        bot.answer_callback_query(
            call.id, f"🟢 {'🎬 Video' if value=='video' else '📄 Document'}"
        )
    except:
        pass


# * ─── /drive ───────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["drive"])
def cmd_drive(message: Message):
    user_id = message.from_user.id
    rclone, cfg = ensure_rclone(user_id, message)
    if not rclone:
        return
    smart_send_or_edit(user_id, "drive", message.chat.id, "🔍 Fetching GDrive stats…")
    ok, out, err = run_rclone(rclone, cfg, "about", "GDRIVE:")
    if not ok:
        smart_send_or_edit(
            user_id, "drive", message.chat.id, f"❌ Failed: {safe_escape(err)}"
        )
        return
    total = used = free = trash = "Unknown"
    for line in out.split("\n"):
        if line.startswith("Total:"):
            total = line.split(":", 1)[1].strip()
        elif line.startswith("Used:"):
            used = line.split(":", 1)[1].strip()
        elif line.startswith("Free:"):
            free = line.split(":", 1)[1].strip()
        elif line.startswith("Trashed:"):
            trash = line.split(":", 1)[1].strip()
    smart_send_or_edit(
        user_id,
        "drive",
        message.chat.id,
        "💾 <b>Google Drive Storage</b>\n\n"
        f"{DIVIDER_SM}\n"
        f"🔵  Total    <b>{total}</b>\n"
        f"🟠  Used     <b>{used}</b>\n"
        f"🟢  Free     <b>{free}</b>\n"
        f"🗑   Trashed  <b>{trash}</b>",
    )


# . ─── /drivvy ──────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["drivvy"])
def cmd_drivvy(message: Message):
    user_id = message.from_user.id
    rclone, cfg = ensure_rclone(user_id, message)
    if not rclone:
        return
    MsgStore.delete_msg(user_id, "drivvy")
    loading = send_msg(message.chat.id, "📁 Listing GDrive contents…")
    ok, out, err = run_rclone(
        rclone, cfg, "lsf", "GDRIVE:", "--recursive", "--files-only", timeout=300
    )
    if not ok:
        if loading:
            edit_msg(
                message.chat.id, loading.message_id, f"❌ Failed: {safe_escape(err)}"
            )
        return
    files = [f for f in out.split("\n") if f.strip()]
    if not files:
        if loading:
            edit_msg(message.chat.id, loading.message_id, "📁 GDrive is empty.")
        return
    file_lines = [f"📄 <code>{safe_escape(f)}</code>" for f in files]
    total = len(file_lines)
    pages, current_lines, current_len = [], [], 0
    for line in file_lines:
        if current_len + len(line) + 1 > 3800:
            pages.append(current_lines)
            current_lines = [line]
            current_len = len(line)
        else:
            current_lines.append(line)
            current_len += len(line) + 1
    if current_lines:
        pages.append(current_lines)
    total_parts = len(pages)
    for i, page_lines in enumerate(pages):
        part_num = i + 1
        header = f"📁 <b>GDrive Contents</b>  ({part_num}/{total_parts})  <i>{total} files</i>\n\n"
        body = "\n".join(page_lines)
        if i == 0 and loading:
            edit_msg(message.chat.id, loading.message_id, header + body)
        else:
            send_msg(message.chat.id, header + body)
        time.sleep(0.5)


#! ─── /pikky ───────────────────────────────────────────────────────────────────


@bot.message_handler(commands=["pikky"])
def cmd_pikky(message: Message):
    user_id = message.from_user.id
    rclone, cfg = ensure_rclone(user_id, message)
    if not rclone:
        return
    MsgStore.delete_msg(user_id, "pikky")
    loading = send_msg(message.chat.id, "🔍 Fetching PikPak info…")
    ok, out, err = run_rclone(rclone, cfg, "about", "PIKKY:")
    if ok:
        total = used = free = "Unknown"
        for line in out.split("\n"):
            if line.startswith("Total:"):
                total = line.split(":", 1)[1].strip()
            elif line.startswith("Used:"):
                used = line.split(":", 1)[1].strip()
            elif line.startswith("Free:"):
                free = line.split(":", 1)[1].strip()
        storage_text = (
            f"📊 <b>PikPak Storage</b>\n\n{DIVIDER_SM}\n"
            f"🔵  Total  <b>{total}</b>\n"
            f"🟠  Used   <b>{used}</b>\n"
            f"🟢  Free   <b>{free}</b>"
        )
    else:
        storage_text = f"⚠️ Storage unavailable: {safe_escape(err)}"
    ok2, out2, _ = run_rclone(
        rclone, cfg, "lsf", "PIKKY:", "--recursive", "--files-only", timeout=300
    )
    if ok2:
        all_files = [f for f in out2.split("\n") if f.strip()]
        videos = [f for f in all_files if f.rsplit(".", 1)[-1].lower() in VIDEO_EXTS]
        if videos:
            preview_lines = [f"🎬 <code>{safe_escape(v)}</code>" for v in videos[:8]]
            preview = "\n".join(preview_lines)
            more = f"\n<i>…and {len(videos)-8} more</i>" if len(videos) > 8 else ""
            video_text = f"\n\n🎬 <b>Videos: {len(videos)} found</b>\n\n{preview}{more}"
        else:
            video_text = "\n\n🎬 No video files found."
    else:
        video_text = "\n\n⚠️ Could not list files."
    result = storage_text + video_text
    if loading:
        edit_msg(message.chat.id, loading.message_id, result)
    else:
        send_msg(message.chat.id, result)


# - ─── /sendfiles ───────────────────────────────────────────────────────────────


@bot.message_handler(commands=["sendfiles"])
def cmd_sendfiles(message: Message):
    user_id = message.from_user.id
    rclone, cfg = ensure_rclone(user_id, message)
    if not rclone:
        return
    transfers = UserManager.get_transfers(user_id, limit=5)
    completed = [
        t for t in transfers if t["status"] == "completed" and t["destination_folder"]
    ]
    if not completed:
        bot.reply_to(
            message,
            "⚠️ No completed transfers found.\n\nRun /upload first.",
            parse_mode="HTML",
        )
        return
    kb = InlineKeyboardMarkup()
    for t in completed[:5]:
        folder = t["destination_folder"]
        label = f"📁 {folder[:35]}…" if len(folder) > 35 else f"📁 {folder}"
        kb.row(InlineKeyboardButton(label, callback_data=f"senddir_{user_id}_{folder}"))
    send_as = UserManager.get_settings(user_id).get("send_as", "video")
    limit_str = fmt_size(MAX_SEND_BYTES())
    bot.reply_to(
        message,
        f"📤 <b>Send GDrive Files to Telegram</b>\n\n"
        f"{DIVIDER_SM}\n"
        f"📡  API mode  <b>{'Local' if _using_local_api else 'Official'}</b>\n"
        f"📦  Max size  <b>{limit_str}</b> per file\n"
        f"📬  Send as   <b>{send_as}</b>  (change: /settings)\n"
        f"{DIVIDER_SM}\n\n"
        "Select a transfer folder ↓",
        parse_mode="HTML",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("senddir_"))
def cb_senddir(call: CallbackQuery):
    parts = call.data.split("_", 2)
    user_id = int(parts[1])
    folder = parts[2]
    bot.answer_callback_query(call.id, "⏳ Listing files…")
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔍 Listing <code>GDRIVE:{safe_escape(folder)}</code>…",
            parse_mode="HTML",
        )
    except:
        pass
    rclone = get_rclone_path(user_id)
    cfg = get_config_file(user_id)
    if not os.path.exists(rclone) or not os.path.exists(cfg):
        send_msg(call.message.chat.id, "❌ rclone not ready. Run /upload first.")
        return
    ok, out, err = run_rclone(
        rclone,
        cfg,
        "lsf",
        f"GDRIVE:{folder}",
        "--recursive",
        "--files-only",
        timeout=120,
    )
    if not ok:
        send_msg(call.message.chat.id, f"❌ Failed to list: {safe_escape(err)}")
        return
    files = [f for f in out.split("\n") if f.strip()]
    if not files:
        send_msg(call.message.chat.id, "📁 No files found in this folder.")
        return
    send_as = UserManager.get_settings(user_id).get("send_as", "video")
    limit_str = fmt_size(MAX_SEND_BYTES())
    status_msg = send_msg(
        call.message.chat.id,
        f"📦 <b>Starting file transfer…</b>\n\n"
        f"📁  {len(files)} file(s) from <code>GDRIVE:{safe_escape(folder)}</code>\n"
        f"📬  Sending as  <b>{send_as}</b>\n"
        f"📦  Size limit  <b>{limit_str}</b> per file",
    )
    if status_msg:
        threading.Thread(
            target=_send_files_worker,
            args=(
                call.message.chat.id,
                user_id,
                folder,
                files,
                rclone,
                cfg,
                send_as,
                status_msg.message_id,
            ),
            daemon=True,
        ).start()


def _ffmpeg_available() -> bool:
    try:
        return (
            subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, timeout=5
            ).returncode
            == 0
        )
    except:
        return False


def _probe_duration(video_path: str) -> float:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return float(r.stdout.strip())
    except:
        return 0.0


def _secs_to_ts(secs: float) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _generate_thumbnail(video_path: str, thumb_path: str) -> bool:
    duration = _probe_duration(video_path)
    candidates = ([duration * 0.20, duration * 0.10] if duration > 0 else []) + [
        30.0,
        5.0,
        1.0,
    ]
    candidates = [c for c in candidates if duration == 0 or c < duration] or [1.0]
    seen, unique_c = set(), []
    for c in candidates:
        key = round(c, 1)
        if key not in seen:
            seen.add(key)
            unique_c.append(c)
    for seek in unique_c:
        ts = _secs_to_ts(seek)
        try:
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    ts,
                    "-i",
                    video_path,
                    "-vf",
                    "thumbnail=24,scale=320:-2",
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    thumb_path,
                ],
                capture_output=True,
                timeout=90,
            )
            if (
                r.returncode == 0
                and os.path.exists(thumb_path)
                and os.path.getsize(thumb_path) > 512
            ):
                return True
            try:
                os.remove(thumb_path)
            except:
                pass
        except:
            pass
    return False


def _send_files_worker(
    chat_id, user_id, folder, files, rclone, cfg, send_as, status_msg_id
):
    tmp_dir = f"/tmp/gdrive_send_{user_id}_{int(time.time())}"
    os.makedirs(tmp_dir, exist_ok=True)
    sent_count = failed_count = skipped_count = 0
    total = len(files)
    has_ffmpeg = _ffmpeg_available()

    def _status(phase, filename="", extra=""):
        done = sent_count + failed_count + skipped_count
        bar = make_bar(int(BAR_DL * done / total) if total else 0, BAR_DL)
        pct = int(100 * done / total) if total else 0
        lines = [
            f"📦 <b>Sending Files</b>  <code>[{bar}]</code>  {pct}%",
            "",
            f"📁  Progress  <b>{done}/{total}</b>   ✅ {sent_count}  ⏭ {skipped_count}  ❌ {failed_count}",
        ]
        if filename:
            lines += ["", f"<b>{phase}</b>  <code>{safe_escape(filename)}</code>"]
        if extra:
            lines.append(extra)
        edit_msg(chat_id, status_msg_id, "\n".join(lines))

    for i, filename in enumerate(files, 1):
        if not filename.strip():
            continue
        _status("⬇️ Downloading", filename)
        remote_path = f"GDRIVE:{folder}/{filename}"
        local_path = os.path.join(tmp_dir, os.path.basename(filename))
        ok_dl, _, err_dl = run_rclone(
            rclone, cfg, "copyto", remote_path, local_path, timeout=3600
        )
        if not ok_dl:
            failed_count += 1
            _status(
                "❌ Download failed", filename, f"<i>{safe_escape(err_dl[:120])}</i>"
            )
            time.sleep(2)
            continue
        try:
            file_size = os.path.getsize(local_path)
        except:
            file_size = 0
        if file_size > MAX_SEND_BYTES():
            skipped_count += 1
            _status(
                "⏭ Skipped — too large",
                filename,
                f"<i>{fmt_size(file_size)} > {fmt_size(MAX_SEND_BYTES())} limit</i>",
            )
            try:
                os.remove(local_path)
            except:
                pass
            time.sleep(1)
            continue
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        is_video = ext in VIDEO_EXTS
        use_video = send_as == "video" and is_video
        thumb_path = None
        duration = 0
        if is_video and has_ffmpeg:
            _status("🎞️ Generating thumbnail", filename)
            thumb_path = local_path + ".thumb.jpg"
            if not _generate_thumbnail(local_path, thumb_path):
                thumb_path = None
            duration = int(_probe_duration(local_path))
        _status("📤 Uploading", filename, f"<i>{fmt_size(file_size)}</i>")
        caption = (
            f"📁 <code>{safe_escape(os.path.basename(filename))}</code>\n\n"
            f"({i}/{total})  ·  {fmt_size(file_size)}"
        )
        if not os.path.exists(local_path):
            failed_count += 1
            _status("❌ File missing", filename)
            time.sleep(1)
            continue
        _upload_done = threading.Event()
        _upload_start = time.time()

        def _spinner(fname=filename, fsize=file_size):
            spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            idx = 0
            while not _upload_done.is_set():
                elapsed = int(time.time() - _upload_start)
                m2, s2 = divmod(elapsed, 60)
                estr = f"{m2}m {s2}s" if m2 else f"{s2}s"
                done = sent_count + failed_count + skipped_count
                bar2 = make_bar(int(BAR_DL * done / total) if total else 0, BAR_DL)
                pct2 = int(100 * done / total) if total else 0
                spin = spinners[idx % len(spinners)]
                edit_msg(
                    chat_id,
                    status_msg_id,
                    f"📦 <b>Sending Files</b>  <code>[{bar2}]</code>  {pct2}%\n\n"
                    f"📁  Progress  <b>{done}/{total}</b>   🟢 {sent_count}  ⏭ {skipped_count}  ❌ {failed_count}\n\n"
                    f"{spin}  <b>Uploading</b>  <code>{safe_escape(fname)}</code>\n\n"
                    f"<i>{fmt_size(fsize)}  ·  {estr} elapsed</i>",
                )
                idx += 1
                _upload_done.wait(5)

        spinner_thread = threading.Thread(target=_spinner, daemon=True)
        spinner_thread.start()
        try:
            with open(local_path, "rb") as f:
                thumb_fh = open(thumb_path, "rb") if thumb_path else None
                try:
                    if use_video:
                        kwargs = dict(
                            chat_id=chat_id,
                            video=f,
                            caption=caption,
                            parse_mode="HTML",
                            supports_streaming=True,
                            duration=duration or None,
                            timeout=3600,
                        )
                        if thumb_fh:
                            kwargs["thumbnail"] = thumb_fh
                        try:
                            bot.send_video(**kwargs)
                        except TypeError:
                            if thumb_fh:
                                thumb_fh.seek(0)
                                kwargs.pop("thumbnail", None)
                                kwargs["thumb"] = thumb_fh
                            bot.send_video(**kwargs)
                    else:
                        kwargs = dict(
                            chat_id=chat_id,
                            document=f,
                            caption=caption,
                            parse_mode="HTML",
                            timeout=3600,
                        )
                        if thumb_fh:
                            kwargs["thumbnail"] = thumb_fh
                        try:
                            bot.send_document(**kwargs)
                        except TypeError:
                            if thumb_fh:
                                thumb_fh.seek(0)
                                kwargs.pop("thumbnail", None)
                                kwargs["thumb"] = thumb_fh
                            bot.send_document(**kwargs)
                finally:
                    if thumb_fh:
                        thumb_fh.close()
            sent_count += 1
            try:
                bot.send_sticker(
                    chat_id,
                    "CAACAgEAAxkBAAIZWWfbz7HRAAG_TpNxVjPxUAcU4tcibgACpQADHRnARCfGLhsFn5OdNgQ",
                )
            except:
                pass
        except Exception as e:
            failed_count += 1
            print(f"[upload] {filename}: {e}")
            _status("❌ Upload failed", filename, f"<i>{safe_escape(str(e)[:200])}</i>")
            time.sleep(2)
        finally:
            _upload_done.set()
            spinner_thread.join(timeout=2)
            try:
                os.remove(local_path)
            except:
                pass
            if thumb_path:
                try:
                    os.remove(thumb_path)
                except:
                    pass
        time.sleep(0.3)

    shutil.rmtree(tmp_dir, ignore_errors=True)
    edit_msg(
        chat_id,
        status_msg_id,
        f"🟢 <b>All Done!</b>\n\n"
        f"{DIVIDER_SM}\n"
        f"📤  Sent     <b>{sent_count}</b>\n"
        f"⏭   Skipped  <b>{skipped_count}</b>  (too large)\n"
        f"❌  Failed   <b>{failed_count}</b>\n"
        f"{DIVIDER_SM}\n\n"
        f"📁 <code>GDRIVE:{safe_escape(folder)}</code>",
    )


# * ─── /history ─────────────────────────────────────────────────────────────────


def _parse_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except:
        return None


@bot.message_handler(commands=["history"])
def cmd_history(message: Message):
    user_id = message.from_user.id
    transfers = UserManager.get_transfers(user_id)
    if not transfers:
        bot.reply_to(
            message,
            "📜 <b>No transfer history yet.</b>\n\nStart a transfer with /upload.",
            parse_mode="HTML",
        )
        return
    emoji_map = {"completed": "✅", "failed": "❌", "cancelled": "⏹"}
    header = f"📜 <b>Transfer History</b>\n{DIVIDER}\n"
    blocks = []
    for t in transfers:
        icon = emoji_map.get(t["status"], "❓")
        dt_s = _parse_dt(t["start_time"])
        dt_e = _parse_dt(t["end_time"])
        start = dt_s.strftime("%Y-%m-%d %H:%M") if dt_s else "—"
        end = dt_e.strftime("%H:%M") if dt_e else "—"
        dur = str(dt_e - dt_s).split(".")[0] if dt_s and dt_e else "—"
        folder = safe_escape(t["destination_folder"] or "—")
        blocks.append(
            f"{icon} <b>#{t['id']}  {t['status'].title()}</b>\n"
            f"📅  {start} → {end}  ({dur})\n"
            f"📁  Files       <b>{t['files_count'] or 0}</b>\n"
            f"💾  Total size  <b>{t['total_size'] or 'Unknown'}</b>\n"
            f"📤  Transferred <b>{t['transferred_size'] or 'Unknown'}</b>\n"
            f"⚡  Speed       <b>{t['speed'] or '—'}</b>\n"
            f"📂  Folder      <code>{folder}</code>\n"
            + (
                f"⚠️  Error       {safe_escape(t['error_message'])}\n"
                if t.get("error_message")
                else ""
            )
            + f"{DIVIDER_SM}\n"
        )
    pages, current, current_len = [], header, len(header)
    for block in blocks:
        if current_len + len(block) + 1 > 3900:
            pages.append(current)
            current = block
            current_len = len(block)
        else:
            current += "\n" + block
            current_len += len(block) + 1
    if current:
        pages.append(current)
    for i, page in enumerate(pages):
        prefix = f"<b>({i+1}/{len(pages)})</b>\n" if len(pages) > 1 and i > 0 else ""
        send_msg(message.chat.id, prefix + page, parse_mode="HTML")


# . ─── Bot Commands Menu ────────────────────────────────────────────────────────


def set_commands():
    try:
        bot.set_my_commands(
            [
                telebot.types.BotCommand("start", "🛸 Home — commands & status"),
                telebot.types.BotCommand("guide", "📖 Full setup guide"),
                telebot.types.BotCommand("config", "⚙️ Set rclone configuration"),
                telebot.types.BotCommand("upload", "🚀 Start PikPak → GDrive transfer"),
                telebot.types.BotCommand("stop", "⏹ Instantly stop transfer"),
                telebot.types.BotCommand("status", "📊 Live network status card"),
                telebot.types.BotCommand("drive", "💾 GDrive storage stats"),
                telebot.types.BotCommand("drivvy", "📁 List GDrive contents"),
                telebot.types.BotCommand("pikky", "🎬 PikPak storage & videos"),
                telebot.types.BotCommand(
                    "sendfiles", "📤 Send GDrive files to Telegram"
                ),
                telebot.types.BotCommand("settings", "⚙️ Upload type & preferences"),
                telebot.types.BotCommand(
                    "localapi", "🖥 Setup local API for 2 GB uploads"
                ),
                telebot.types.BotCommand("history", "📜 Transfer history"),
            ]
        )
        print("✓ Bot commands set.")
    except Exception as e:
        print(f"⚠️ Could not set commands: {e}")


# ? ─── Entry ────────────────────────────────────────────────────────────────────

LOCK_FILE = os.path.join(SCRIPT_DIR, ".bot.lock")


def _kill_previous_instance():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                try:
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(2)
                except ProcessLookupError:
                    pass
        except Exception as e:
            print(f"⚠️ Lock error: {e}")
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except:
        pass
    try:
        bot.delete_webhook(drop_pending_updates=True)
        print("✓ Webhook cleared, pending updates dropped.")
    except Exception as e:
        print(f"⚠️ delete_webhook: {e}")
    time.sleep(1)


def main():
    print("🛸 PikPak → GDrive Ultra Bot v3.0 starting…")
    _kill_previous_instance()
    set_commands()
    print("✓ Polling…\n")
    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=30,
            skip_pending=True,
            allowed_updates=["message", "callback_query"],
        )
    except Exception as e:
        print(f"[main] polling error: {e}")
    finally:
        stop_local_api()
        try:
            os.remove(LOCK_FILE)
        except:
            pass


if __name__ == "__main__":
    main()
