import os
import re
import sys
import time
import json
import stat
import shutil
import string
import random
import sqlite3
import zipfile
import platform
import threading
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

APP_HOME = Path.home() / ".pikky_web"
APP_HOME.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_HOME / "pikky.db"
BIN_DIR = APP_HOME / "bin"
CONFIG_DIR = APP_HOME / "rclone"
BIN_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_EXTENSIONS = ["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "mpg", "mpeg", "m4v", "3gp"]

# Naming convention for auto-generated profiles (after "default"): NATO phonetic alphabet.
# Each profile gets its own isolated rclone config, so a fresh profile with its own PikPak
# login is effectively a separate PikPak account — useful for working around PikPak's
# per-account download/transfer limits.
NATO_NAMES = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
    "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey",
    "xray", "yankee", "zulu",
]

IS_WINDOWS = platform.system().lower() == "windows"
OS_NAME = "Windows" if IS_WINDOWS else ("macOS" if platform.system().lower() == "darwin" else "Linux")
ARCH = "amd64" if "64" in platform.machine() or platform.machine() in ("x86_64", "AMD64") else "386"
if "arm" in platform.machine().lower() or "aarch64" in platform.machine().lower():
    ARCH = "arm64"

RCLONE_BIN_NAME = "rclone.exe" if IS_WINDOWS else "rclone"
RCLONE_DOWNLOAD_OS = "windows" if IS_WINDOWS else ("osx" if OS_NAME == "macOS" else "linux")
RCLONE_DOWNLOAD_URL = f"https://downloads.rclone.org/rclone-current-{RCLONE_DOWNLOAD_OS}-{ARCH}.zip"


def os_report():
    return {
        "os": OS_NAME,
        "arch": ARCH,
        "python": platform.python_version(),
        "rclone_url": RCLONE_DOWNLOAD_URL,
        "bin_dir": str(BIN_DIR),
        "config_dir": str(CONFIG_DIR),
    }


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            rclone_config TEXT,
            webdav_url TEXT,
            webdav_user TEXT,
            webdav_pass TEXT,
            default_destination TEXT DEFAULT 'gdrive',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,
            status TEXT,
            destination_type TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            destination_folder TEXT,
            files_count INTEGER,
            total_size TEXT,
            error_message TEXT
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        conn.commit()


init_db()


class Preferences:
    @staticmethod
    def get(key, default=None):
        with get_db() as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    @staticmethod
    def set(key, value):
        with get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)", (key, value))
            conn.commit()


class ProfileManager:
    @staticmethod
    def list_profiles():
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get(name):
        with get_db() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE name=?", (name,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_active():
        active_name = Preferences.get("active_profile")
        if not active_name:
            profiles = ProfileManager.list_profiles()
            return profiles[0] if profiles else None
        return ProfileManager.get(active_name)

    @staticmethod
    def save(name, rclone_config=None, webdav_url=None, webdav_user=None, webdav_pass=None, default_destination="gdrive"):
        with get_db() as conn:
            existing = conn.execute("SELECT * FROM profiles WHERE name=?", (name,)).fetchone()
            if existing:
                conn.execute("""UPDATE profiles SET rclone_config=COALESCE(?, rclone_config),
                    webdav_url=COALESCE(?, webdav_url), webdav_user=COALESCE(?, webdav_user),
                    webdav_pass=COALESCE(?, webdav_pass), default_destination=? WHERE name=?""",
                    (rclone_config, webdav_url, webdav_user, webdav_pass, default_destination, name))
            else:
                conn.execute("""INSERT INTO profiles (name, rclone_config, webdav_url, webdav_user, webdav_pass, default_destination)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (name, rclone_config, webdav_url, webdav_user, webdav_pass, default_destination))
            conn.commit()
        Preferences.set("active_profile", name)

    @staticmethod
    def delete(name):
        with get_db() as conn:
            conn.execute("DELETE FROM profiles WHERE name=?", (name,))
            conn.commit()

    @staticmethod
    def next_name():
        """Suggest the next profile name: 'default' first, then the NATO alphabet."""
        existing = {p["name"] for p in ProfileManager.list_profiles()}
        if "default" not in existing:
            return "default"
        for n in NATO_NAMES:
            if n not in existing:
                return n
        i = 1
        while True:
            candidate = f"profile{i}"
            if candidate not in existing:
                return candidate
            i += 1

    @staticmethod
    def save_transfer(profile_id, status, destination_type, start_time, end_time,
                       destination_folder, files_count, total_size, error_message):
        with get_db() as conn:
            conn.execute("""INSERT INTO transfers
                (profile_id, status, destination_type, start_time, end_time, destination_folder,
                 files_count, total_size, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (profile_id, status, destination_type, start_time, end_time,
                 destination_folder, files_count, total_size, error_message))
            conn.commit()

    @staticmethod
    def get_transfers(profile_id, limit=20):
        with get_db() as conn:
            rows = conn.execute("""SELECT * FROM transfers WHERE profile_id=?
                ORDER BY start_time DESC LIMIT ?""", (profile_id, limit)).fetchall()
            return [dict(r) for r in rows]


def generate_alien_name():
    prefixes = ["Zor", "Xen", "Qua", "Vor", "Kly", "Sor", "Tyr", "Neb", "Gal", "Cos",
                "Andro", "Nebu", "Puls", "Quas", "Supern", "Epsil", "Centa", "Proxim"]
    suffixes = ["blax", "dor", "gon", "thar", "zon", "nax", "tar", "vax", "rox", "lax",
                "meda", "ula", "axy", "ion", "nova", "ius"]
    name = f"{random.choice(prefixes)}{random.choice(suffixes)}"
    if random.random() > 0.7:
        name += str(random.randint(1, 999))
    return name


def format_size(n):
    n = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


class RcloneInstaller:
    @staticmethod
    def is_installed():
        path = BIN_DIR / RCLONE_BIN_NAME
        return path.exists() and os.access(path, os.X_OK) if not IS_WINDOWS else path.exists()

    @staticmethod
    def get_path():
        return str(BIN_DIR / RCLONE_BIN_NAME)

    @staticmethod
    def install(log=print):
        rclone_path = BIN_DIR / RCLONE_BIN_NAME
        if RcloneInstaller.is_installed():
            log("rclone already installed.")
            return True, str(rclone_path)

        temp_dir = APP_HOME / "tmp_install"
        temp_dir.mkdir(parents=True, exist_ok=True)
        zip_path = temp_dir / "rclone.zip"
        try:
            log(f"Downloading rclone for {OS_NAME}/{ARCH}...")
            urllib.request.urlretrieve(RCLONE_DOWNLOAD_URL, zip_path)
            log("Extracting rclone...")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(temp_dir)

            extracted_dirs = [d for d in temp_dir.iterdir() if d.is_dir() and d.name.startswith("rclone-")]
            if not extracted_dirs:
                log("Could not find extracted rclone directory.")
                return False, None

            src_binary = extracted_dirs[0] / RCLONE_BIN_NAME
            shutil.copy2(src_binary, rclone_path)
            if not IS_WINDOWS:
                os.chmod(rclone_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            shutil.rmtree(temp_dir, ignore_errors=True)

            result = subprocess.run([str(rclone_path), "version"], capture_output=True, text=True)
            if result.returncode == 0:
                log(f"rclone installed: {result.stdout.splitlines()[0]}")
                return True, str(rclone_path)
            log("rclone installation verification failed.")
            return False, None
        except Exception as e:
            log(f"Failed to install rclone: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, None


class NetworkMonitor:
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.previous_stats = {}
        self.start_time = None
        self.last_update_time = None
        self.total_uploaded = 0
        self.total_downloaded = 0
        self.current_upload_speed = 0
        self.current_download_speed = 0

    def get_stats(self):
        if IS_WINDOWS:
            return self._get_stats_windows()
        return self._get_stats_linux()

    def _get_stats_linux(self):
        try:
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()[2:]
            stats = {}
            for line in lines:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                vals = data.split()
                if len(vals) >= 16:
                    stats[iface.strip()] = {"rx": int(vals[0]), "tx": int(vals[8])}
            return stats
        except Exception:
            return {}

    def _get_stats_windows(self):
        try:
            import psutil
            counters = psutil.net_io_counters(pernic=True)
            return {name: {"rx": c.bytes_recv, "tx": c.bytes_sent} for name, c in counters.items()}
        except Exception:
            return {}

    def _speeds(self, current, elapsed):
        if not self.previous_stats or elapsed <= 0:
            return 0, 0
        rx_diff = tx_diff = 0
        for iface, vals in current.items():
            prev = self.previous_stats.get(iface)
            if prev:
                d_rx = vals["rx"] - prev["rx"]
                d_tx = vals["tx"] - prev["tx"]
                if d_rx > 0:
                    rx_diff += d_rx
                if d_tx > 0:
                    tx_diff += d_tx
        return rx_diff / elapsed, tx_diff / elapsed

    def _loop(self, interval=1.0):
        self.start_time = datetime.now()
        self.previous_stats = self.get_stats()
        self.last_update_time = self.start_time
        while self.monitoring:
            time.sleep(interval)
            current = self.get_stats()
            if not current:
                continue
            now = datetime.now()
            elapsed = (now - self.last_update_time).total_seconds()
            dl, ul = self._speeds(current, elapsed)
            self.current_download_speed = dl
            self.current_upload_speed = ul
            self.total_downloaded += dl * elapsed
            self.total_uploaded += ul * elapsed
            self.previous_stats = current
            self.last_update_time = now

    def start(self):
        if self.monitoring:
            return
        self.monitoring = True
        self.total_uploaded = 0
        self.total_downloaded = 0
        self.monitor_thread = threading.Thread(target=self._loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        self.monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)

    def snapshot(self):
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        return {
            "upload_speed": format_size(self.current_upload_speed) + "/s",
            "download_speed": format_size(self.current_download_speed) + "/s",
            "total_uploaded": format_size(self.total_uploaded),
            "total_downloaded": format_size(self.total_downloaded),
            "elapsed_seconds": int(elapsed),
            "active": self.current_upload_speed > 1024 or self.current_download_speed > 1024,
        }


class TransferJob:
    """Represents one running or completed transfer for a profile."""

    def __init__(self, profile):
        self.profile = profile
        self.status = "idle"
        self.logs = []
        self.process = None
        self.stop_requested = False
        self.network_monitor = NetworkMonitor()
        self.lock = threading.Lock()
        self.destination_folder = None
        self.destination_type = "gdrive"
        self.files_count = 0
        self.thread = None

    def log(self, level, message):
        with self.lock:
            self.logs.append({"level": level, "message": message, "time": datetime.now().isoformat()})
            self.logs = self.logs[-500:]

    def _write_config_file(self):
        config_file = CONFIG_DIR / f"{self.profile['name']}.conf"
        with open(config_file, "w") as f:
            f.write(self.profile.get("rclone_config") or "")
        return str(config_file)

    def _run(self, command_list):
        try:
            result = subprocess.run(command_list, capture_output=True, text=True, shell=False)
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return False, "", str(e)

    def start(self, destination_type="gdrive"):
        if self.status == "running":
            return False, "Transfer already in progress"
        self.destination_type = destination_type
        self.stop_requested = False
        self.thread = threading.Thread(target=self._run_transfer, daemon=True)
        self.thread.start()
        return True, "Transfer started"

    def stop(self):
        self.stop_requested = True
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass

    def _run_transfer(self):
        self.status = "running"
        self.logs = []
        start_time = datetime.now()
        error_message = None
        video_files = []
        self.destination_folder = None

        try:
            self.log("info", "Checking rclone installation...")
            ok, rclone_path = RcloneInstaller.install(log=lambda m: self.log("info", m))
            if not ok:
                raise RuntimeError("Failed to install rclone")

            self.log("info", "Writing configuration...")
            config_file = self._write_config_file()

            self.log("info", "Verifying PIKKY remote...")
            ok, _, err = self._run([rclone_path, "--config", config_file, "lsd", "PIKKY:"])
            if not ok:
                raise RuntimeError(f"PIKKY remote failed: {err}")

            dest_remote = "GDRIVE" if self.destination_type == "gdrive" else "WEBDAV"
            self.log("info", f"Verifying {dest_remote} remote...")
            ok, _, err = self._run([rclone_path, "--config", config_file, "lsd", f"{dest_remote}:"])
            if not ok:
                raise RuntimeError(f"{dest_remote} remote failed: {err}")

            self.log("info", "Scanning PikPak for video files...")
            ok, out, err = self._run([rclone_path, "--config", config_file, "lsf", "PIKKY:", "--recursive"])
            if not ok:
                raise RuntimeError(f"Could not list PikPak files: {err}")

            all_files = out.split("\n") if out else []
            video_files = [f for f in all_files if f.split(".")[-1].lower() in VIDEO_EXTENSIONS]
            self.log("info", f"Found {len(all_files)} files, {len(video_files)} videos.")
            self.files_count = len(video_files)

            if not video_files:
                self.log("warning", "No video files found. Nothing to transfer.")
                self.status = "completed"
                return

            alien_name = generate_alien_name()
            self.destination_folder = f"{alien_name}-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            self.log("info", f"Destination folder: {self.destination_folder}")

            self.network_monitor.start()

            filter_rules = ["+ */"] + [f"+ *.{ext}" for ext in VIDEO_EXTENSIONS] + ["- .*", "- *"]
            command = [rclone_path, "--config", config_file, "sync", "PIKKY:",
                       f"{dest_remote}:{self.destination_folder}",
                       "--progress", "--stats", "5s", "--stats-one-line",
                       "--transfers", "4", "--checkers", "8", "--fast-list", "--checksum",
                       "--drive-chunk-size", "64M", "--buffer-size", "32M"]
            for rule in filter_rules:
                command += ["--filter", rule]

            self.log("info", f"Starting sync to {dest_remote}:{self.destination_folder}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            for line in self.process.stdout:
                line = line.strip()
                if line:
                    self.log("info", line)
                if self.stop_requested:
                    self.process.terminate()
                    time.sleep(1)
                    if self.process.poll() is None:
                        self.process.kill()
                    break

            self.process.wait()
            self.network_monitor.stop()

            if self.stop_requested:
                self.status = "cancelled"
                error_message = "Cancelled by user"
                self.log("warning", "Transfer cancelled by user.")
            elif self.process.returncode == 0:
                self.status = "completed"
                self.log("success", "Transfer completed successfully!")
            else:
                self.status = "failed"
                error_message = "rclone sync returned a non-zero exit code"
                self.log("error", "Transfer failed.")

        except Exception as e:
            self.status = "failed"
            error_message = str(e)
            self.log("error", str(e))
            self.network_monitor.stop()
        finally:
            self.process = None
            self.stop_requested = False
            ProfileManager.save_transfer(
                self.profile["id"], self.status, self.destination_type,
                start_time, datetime.now(), self.destination_folder,
                self.files_count, "unknown", error_message,
            )

    def snapshot(self):
        with self.lock:
            logs = list(self.logs[-200:])
        net = self.network_monitor.snapshot() if self.network_monitor.monitoring or self.network_monitor.start_time else None
        return {
            "status": self.status,
            "logs": logs,
            "network": net,
            "destination_folder": self.destination_folder,
            "files_count": self.files_count,
        }


class RcloneQuery:
    """Read-only rclone calls used for storage stats + drive listing, run against a saved profile."""

    def __init__(self, profile):
        self.profile = profile
        self.config_file = CONFIG_DIR / f"{profile['name']}.conf"
        with open(self.config_file, "w") as f:
            f.write(profile.get("rclone_config") or "")

    def _ensure_rclone(self):
        if not RcloneInstaller.is_installed():
            RcloneInstaller.install()
        return RcloneInstaller.get_path()

    def _run(self, args):
        rclone_path = self._ensure_rclone()
        try:
            result = subprocess.run([rclone_path, "--config", str(self.config_file)] + args,
                                     capture_output=True, text=True)
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return False, "", str(e)

    def about(self, remote):
        ok, out, err = self._run(["about", f"{remote}:"])
        if not ok:
            return {"error": err}
        info = {"total": "Unknown", "used": "Unknown", "free": "Unknown"}
        for line in out.split("\n"):
            for key in ("total", "used", "free"):
                if line.lower().startswith(f"{key}:"):
                    info[key] = line.split(":", 1)[1].strip()
        return info

    def videos(self, remote):
        ok, out, err = self._run(["lsf", f"{remote}:", "--recursive"])
        if not ok:
            return {"error": err}
        files = out.split("\n") if out else []
        videos = [f for f in files if f.split(".")[-1].lower() in VIDEO_EXTENSIONS]
        return {"total_files": len(files), "video_files": videos, "video_count": len(videos)}

    def list_dir(self, remote, path=""):
        ok, out, err = self._run(["lsjson", f"{remote}:{path}"])
        if not ok:
            return {"error": err}
        try:
            return {"items": json.loads(out)}
        except Exception:
            return {"items": []}

    def clear(self, remote, path=""):
        """Purge (recursively delete) everything at remote:path. Used for the
        'Clear PikPak files' / 'Clear Drive files' quick actions."""
        target = f"{remote}:{path}" if path else f"{remote}:"
        ok, out, err = self._run(["purge", target])
        if not ok:
            return {"ok": False, "error": err}
        return {"ok": True}


active_jobs = {}


def get_job(profile_name, profile):
    if profile_name not in active_jobs:
        active_jobs[profile_name] = TransferJob(profile)
    else:
        active_jobs[profile_name].profile = profile
    return active_jobs[profile_name]
