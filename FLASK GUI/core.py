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
            local_destination_path TEXT,
            default_destination TEXT DEFAULT 'gdrive',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Migration for DBs created before local storage support existed.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()]
        if "local_destination_path" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN local_destination_path TEXT")
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
    def save(name, rclone_config=None, webdav_url=None, webdav_user=None, webdav_pass=None,
             local_destination_path=None, default_destination="gdrive"):
        with get_db() as conn:
            existing = conn.execute("SELECT * FROM profiles WHERE name=?", (name,)).fetchone()
            if existing:
                conn.execute("""UPDATE profiles SET rclone_config=COALESCE(?, rclone_config),
                    webdav_url=COALESCE(?, webdav_url), webdav_user=COALESCE(?, webdav_user),
                    webdav_pass=COALESCE(?, webdav_pass), local_destination_path=COALESCE(?, local_destination_path),
                    default_destination=? WHERE name=?""",
                    (rclone_config, webdav_url, webdav_user, webdav_pass, local_destination_path, default_destination, name))
            else:
                conn.execute("""INSERT INTO profiles (name, rclone_config, webdav_url, webdav_user, webdav_pass,
                    local_destination_path, default_destination)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, rclone_config, webdav_url, webdav_user, webdav_pass, local_destination_path, default_destination))
            conn.commit()
        Preferences.set("active_profile", name)

    @staticmethod
    def set_local_path(name, path):
        with get_db() as conn:
            conn.execute("UPDATE profiles SET local_destination_path=? WHERE name=?", (path, name))
            conn.commit()

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


def browse_filesystem(path=None):
    """List directories under `path` (or home) so the UI can offer a folder picker
    for the local-storage destination. Only returns directories (files aren't
    pickable as a destination)."""
    p = Path(path) if path else Path.home()
    try:
        if not p.exists() or not p.is_dir():
            p = Path.home()
        p = p.resolve()
    except Exception:
        p = Path.home().resolve()
    items = []
    try:
        for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    items.append({"name": entry.name, "path": str(entry)})
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError) as e:
        return {"path": str(p), "parent": None, "items": [], "error": str(e)}
    parent = str(p.parent) if str(p.parent) != str(p) else None
    return {"path": str(p), "parent": parent, "items": items}


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


class TransferJob:
    """Represents one running or completed transfer for a profile."""

    STATS_RE = re.compile(
        r"Transferred:\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+),\s*(\d+)%,\s*([\d.]+\s*\w+/s),\s*ETA\s*(\S+)"
    )

    def __init__(self, profile):
        self.profile = profile
        self.status = "idle"
        self.logs = []
        self.process = None
        self.stop_requested = False
        self.lock = threading.Lock()
        self.destination_folder = None
        self.destination_type = "gdrive"
        self.selected_paths = []
        self.files_count = 0
        self.thread = None
        self.start_time = None
        self.end_time = None
        self.stats = {"speed": None, "progress_pct": 0, "eta": None, "transferred": None, "total": None}

    def log(self, level, message):
        with self.lock:
            self.logs.append({"level": level, "message": message, "time": datetime.now().isoformat()})
            self.logs = self.logs[-500:]

    def _write_config_file(self):
        config_file = CONFIG_DIR / f"{self.profile['name']}.conf"
        with open(config_file, "w") as f:
            f.write(self.profile.get("rclone_config") or "")
        return str(config_file)

    def _local_base_dir(self):
        base = self.profile.get("local_destination_path") or str(Path.home() / "PikpakTransfers")
        Path(base).mkdir(parents=True, exist_ok=True)
        return base

    def _run(self, command_list):
        try:
            result = subprocess.run(command_list, capture_output=True, text=True, shell=False)
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return False, "", str(e)

    def start(self, destination_type="gdrive", selected_paths=None):
        if self.status == "running":
            return False, "Transfer already in progress"
        self.destination_type = destination_type
        self.selected_paths = [p for p in (selected_paths or []) if p]
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

    def _handle_stdout_line(self, line):
        m = self.STATS_RE.search(line)
        if m:
            with self.lock:
                self.stats = {
                    "transferred": m.group(1),
                    "total": m.group(2),
                    "progress_pct": int(m.group(3)),
                    "speed": m.group(4),
                    "eta": m.group(5),
                }
            return
        if line:
            self.log("info", line)

    def _run_transfer(self):
        self.status = "running"
        self.logs = []
        self.start_time = datetime.now()
        self.end_time = None
        self.stats = {"speed": None, "progress_pct": 0, "eta": None, "transferred": None, "total": None}
        error_message = None
        matched_files = []
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

            is_local = self.destination_type == "local"
            if is_local:
                local_base = self._local_base_dir()
                self.log("info", f"Destination: local folder {local_base}")
            else:
                dest_remote = "GDRIVE" if self.destination_type == "gdrive" else "WEBDAV"
                self.log("info", f"Verifying {dest_remote} remote...")
                ok, _, err = self._run([rclone_path, "--config", config_file, "lsd", f"{dest_remote}:"])
                if not ok:
                    raise RuntimeError(f"{dest_remote} remote failed: {err}")

            self.log("info", "Scanning PikPak files...")
            ok, out, err = self._run([rclone_path, "--config", config_file, "lsf", "PIKKY:", "--recursive"])
            if not ok:
                raise RuntimeError(f"Could not list PikPak files: {err}")

            all_files = out.split("\n") if out else []

            if self.selected_paths:
                selected = [p.strip("/") for p in self.selected_paths]
                def matches(f):
                    return any(f == s or f.startswith(s + "/") for s in selected)
                matched_files = [f for f in all_files if matches(f)]
                self.log("info", f"{len(matched_files)} file(s) match your selection out of {len(all_files)} total.")
                filter_rules = []
                for s in selected:
                    filter_rules.append(f"+ {s}/**")
                    filter_rules.append(f"+ {s}")
                filter_rules.append("- *")
            else:
                matched_files = [f for f in all_files if f.split(".")[-1].lower() in VIDEO_EXTENSIONS]
                self.log("info", f"Found {len(all_files)} files, {len(matched_files)} videos (no manual selection, defaulting to all videos).")
                filter_rules = ["+ */"] + [f"+ *.{ext}" for ext in VIDEO_EXTENSIONS] + ["- .*", "- *"]

            self.files_count = len(matched_files)

            if not matched_files:
                self.log("warning", "Nothing matches — nothing to transfer.")
                self.status = "completed"
                self.end_time = datetime.now()
                return

            alien_name = generate_alien_name()
            self.destination_folder = f"{alien_name}-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            self.log("info", f"Destination folder: {self.destination_folder}")

            if is_local:
                dest_arg = str(Path(local_base) / self.destination_folder)
            else:
                dest_arg = f"{dest_remote}:{self.destination_folder}"

            # "copy" (not "sync") so a partial selection or an existing local folder
            # never has unrelated files deleted out from under it.
            command = [rclone_path, "--config", config_file, "copy", "PIKKY:", dest_arg,
                       "--progress", "--stats", "2s", "--stats-one-line",
                       "--transfers", "8", "--checkers", "16", "--fast-list",
                       "--drive-chunk-size", "128M", "--buffer-size", "64M",
                       "--multi-thread-streams", "8", "--multi-thread-cutoff", "50M"]
            if not is_local:
                # WebDAV in particular benefits from bigger direct chunked PUTs
                # instead of many small round trips.
                command += ["--webdav-nextcloud-chunk-size", "64M"]
            for rule in filter_rules:
                command += ["--filter", rule]

            self.log("info", f"Starting transfer to {'local:' + dest_arg if is_local else dest_arg}")
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            for raw_line in self.process.stdout:
                self._handle_stdout_line(raw_line.strip())
                if self.stop_requested:
                    self.process.terminate()
                    time.sleep(1)
                    if self.process.poll() is None:
                        self.process.kill()
                    break

            self.process.wait()

            if self.stop_requested:
                self.status = "cancelled"
                error_message = "Cancelled by user"
                self.log("warning", "Transfer cancelled by user.")
            elif self.process.returncode == 0:
                self.status = "completed"
                self.log("success", "Transfer completed successfully!")
            else:
                self.status = "failed"
                error_message = "rclone returned a non-zero exit code"
                self.log("error", "Transfer failed.")

        except Exception as e:
            self.status = "failed"
            error_message = str(e)
            self.log("error", str(e))
        finally:
            self.process = None
            self.stop_requested = False
            self.end_time = datetime.now()
            ProfileManager.save_transfer(
                self.profile["id"], self.status, self.destination_type,
                self.start_time, self.end_time, self.destination_folder,
                self.files_count, self.stats.get("total") or "unknown", error_message,
            )

    def snapshot(self):
        with self.lock:
            logs = list(self.logs[-200:])
            stats = dict(self.stats)

        if self.status == "running" and self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
        elif self.start_time and self.end_time:
            elapsed = (self.end_time - self.start_time).total_seconds()
        else:
            elapsed = 0

        transferred = None
        if stats.get("total"):
            transferred = f"{stats.get('transferred') or '0'} / {stats.get('total')}"

        return {
            "status": self.status,
            "logs": logs,
            "destination_folder": self.destination_folder,
            "files_count": self.files_count,
            "elapsed_seconds": int(elapsed),
            "speed": stats.get("speed") if self.status == "running" else None,
            "progress_pct": stats.get("progress_pct") or 0,
            "eta": stats.get("eta") if self.status == "running" else None,
            "transferred": transferred,
        }


class RcloneQuery:
    """Read-only rclone calls used for storage stats + drive listing, run against a saved profile.
    Also transparently handles the special "LOCAL" pseudo-remote (the local-storage
    destination), which is just a folder on disk rather than an rclone remote."""

    def __init__(self, profile):
        self.profile = profile
        self.config_file = CONFIG_DIR / f"{profile['name']}.conf"
        with open(self.config_file, "w") as f:
            f.write(profile.get("rclone_config") or "")

    def _local_dir(self):
        return self.profile.get("local_destination_path") or str(Path.home() / "PikpakTransfers")

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
        if remote == "LOCAL":
            try:
                total, used, free = shutil.disk_usage(self._local_dir())
                return {"total": format_size(total), "used": format_size(used), "free": format_size(free)}
            except Exception as e:
                return {"error": str(e)}
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
        if remote == "LOCAL":
            base = Path(self._local_dir())
            target = (base / path) if path else base
            try:
                target = target.resolve()
                if base.resolve() not in target.parents and target != base.resolve():
                    return {"error": "Path escapes the local storage folder."}
                items = []
                for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                    rel = str(entry.relative_to(base)).replace("\\", "/")
                    size = 0
                    try:
                        size = entry.stat().st_size if entry.is_file() else 0
                    except Exception:
                        pass
                    items.append({"Name": entry.name, "Path": rel, "IsDir": entry.is_dir(), "Size": size})
                return {"items": items}
            except Exception as e:
                return {"error": str(e)}
        # Build the rclone target.  For root: "PIKKY:" — for a sub-path: "PIKKY:My Pack"
        # DO NOT add a trailing slash; the PikPak backend resolves the ID from the
        # name and a trailing slash confuses it into thinking the dir doesn't exist.
        clean_path = path.strip("/")
        target = f"{remote}:{clean_path}" if clean_path else f"{remote}:"
        ok, out, err = self._run([
            "lsjson",
            target,
            "--no-modtime",
            "--no-mimetype",
            "--fast-list",
        ])
        if not ok:
            return {"error": err}
        try:
            return {"items": json.loads(out)}
        except Exception:
            return {"items": []}

    def clear(self, remote, path=""):
        """Purge (recursively delete) everything at remote:path. Used for the
        'Clear PikPak files' / 'Clear Drive files' quick actions."""
        if remote == "LOCAL":
            base = Path(self._local_dir())
            target = (base / path) if path else base
            try:
                target = target.resolve()
                if target == base.resolve() and not path:
                    return {"ok": False, "error": "Pick a subfolder — the local storage root can't be cleared from here."}
                if base.resolve() not in target.parents:
                    return {"ok": False, "error": "Path escapes the local storage folder."}
                shutil.rmtree(target)
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
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
