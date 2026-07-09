"""
cloudflare_tunnel.py
--------------------
Optional Cloudflare Tunnel (cloudflared "quick tunnel") integration.

Why this exists
~~~~~~~~~~~~~~~
Google Colab runs on a remote VM. The Flask app listens on 127.0.0.1:5000,
which is unreachable from your browser. To open the dashboard from outside
Colab we expose the local port through a Cloudflare quick tunnel — no
account, no DNS, no setup. Cloudflare hands us a temporary
``https://<random>.trycloudflare.com`` URL that anyone with the link can
open. The tunnel dies when the Colab kernel is interrupted, which is
exactly what you want for a personal rclone control panel.

This module is intentionally dependency-light: only the Python standard
library is used. The ``cloudflared`` binary itself is downloaded on first
use into ``~/.pikky_web/bin/``, the same folder rclone lives in.

Usage
~~~~~
Direct, from a Colab cell::

    from cloudflare_tunnel import start_tunnel
    start_tunnel(port=5000)            # prints the public URL and blocks

Or via the unified launcher::

    python run.py                      # auto-detects Colab, starts the tunnel

If ``cloudflared`` cannot be reached (no internet, firewall), the tunnel
silently no-ops and the app falls back to localhost — local runs are
unaffected.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Optional, Tuple


# --------------------------------------------------------------------------- #
# Paths — kept in lockstep with core.py so rclone + cloudflared share a bin dir.
# --------------------------------------------------------------------------- #
APP_HOME = Path.home() / ".pikky_web"
BIN_DIR = APP_HOME / "bin"
BIN_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Platform detection.
# --------------------------------------------------------------------------- #
_IS_WINDOWS = platform.system().lower() == "windows"
_IS_MAC = platform.system().lower() == "darwin"

_MACHINE = platform.machine().lower()
if _MACHINE in ("x86_64", "amd64"):
    _ARCH = "amd64"
elif _MACHINE in ("aarch64", "arm64"):
    _ARCH = "arm64"
else:
    _ARCH = "386"

_OS_NAME = "windows" if _IS_WINDOWS else ("darwin" if _IS_MAC else "linux")

CLOUDFLARED_BIN_NAME = "cloudflared.exe" if _IS_WINDOWS else "cloudflared"

# Cloudflare publishes official, version-pinned binaries on GitHub. We pin to a
# known-stable release so the download URL is reproducible. Bump this when a
# newer release ships — the URL pattern is the same.
CLOUDFLARED_VERSION = "2024.12.2"

# Cloudflare uses different archive conventions per platform.
#   • Linux   → raw ELF binary (no archive)
#   • macOS   → .tgz
#   • Windows → raw .exe (no archive)
if _IS_WINDOWS:
    CLOUDFLARED_URL = (
        f"https://github.com/cloudflare/cloudflared/releases/download/"
        f"{CLOUDFLARED_VERSION}/cloudflared-windows-amd64.exe"
    )
elif _IS_MAC:
    CLOUDFLARED_URL = (
        f"https://github.com/cloudflare/cloudflared/releases/download/"
        f"{CLOUDFLARED_VERSION}/cloudflared-darwin-{_ARCH}.tgz"
    )
else:
    CLOUDFLARED_URL = (
        f"https://github.com/cloudflare/cloudflared/releases/download/"
        f"{CLOUDFLARED_VERSION}/cloudflared-linux-{_ARCH}"
    )


# --------------------------------------------------------------------------- #
# Colab detection
# --------------------------------------------------------------------------- #
def is_colab() -> bool:
    """Heuristic: are we running inside Google Colab?

    Colab sets a few environment variables and pre-installs the
    ``google.colab`` package. We check both so the detection is robust
    even after a kernel restart.
    """
    if os.environ.get("COLAB_GPU") is not None:
        return True
    # Colab VMs expose GCE metadata — but so does Kaggle. Confirm by importing
    # the colab package.
    try:
        import google.colab  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Binary install
# --------------------------------------------------------------------------- #
def is_installed() -> bool:
    path = BIN_DIR / CLOUDFLARED_BIN_NAME
    if not path.exists():
        return False
    return os.access(path, os.X_OK) if not _IS_WINDOWS else True


def get_path() -> str:
    return str(BIN_DIR / CLOUDFLARED_BIN_NAME)


def install(log=print) -> Tuple[bool, Optional[str]]:
    """Download + extract cloudflared into ``~/.pikky_web/bin/``.

    Returns ``(ok, path_or_None)``.
    """
    if is_installed():
        log("cloudflared already installed.")
        return True, get_path()

    cloudflared_path = BIN_DIR / CLOUDFLARED_BIN_NAME
    temp_dir = APP_HOME / "tmp_cf"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        log(f"Downloading cloudflared {CLOUDFLARED_VERSION} for {_OS_NAME}/{_ARCH}...")
        log(f"  URL: {CLOUDFLARED_URL}")

        # Linux: the file is the raw binary, no archive to unpack.
        if not _IS_WINDOWS and not _IS_MAC:
            urllib.request.urlretrieve(CLOUDFLARED_URL, cloudflared_path)
            os.chmod(
                cloudflared_path,
                stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
            )
        else:
            download_path = temp_dir / (
                "cloudflared.exe" if _IS_WINDOWS else "cloudflared.tgz"
            )
            urllib.request.urlretrieve(CLOUDFLARED_URL, download_path)

            if _IS_WINDOWS:
                shutil.copy2(download_path, cloudflared_path)
            else:  # macOS .tgz
                with tarfile.open(download_path, "r:gz") as tgz:
                    members = tgz.getmembers()
                    cloudflared_member = next(
                        (m for m in members if m.name.endswith("cloudflared")),
                        None,
                    )
                    if cloudflared_member is None:
                        log("Could not find cloudflared binary inside the .tgz.")
                        return False, None
                    # Extract just that one file, then move it.
                    cloudflared_member.name = "cloudflared"
                    tgz.extract(cloudflared_member, temp_dir)
                    shutil.copy2(temp_dir / "cloudflared", cloudflared_path)
                    os.chmod(
                        cloudflared_path,
                        stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
                    )

        shutil.rmtree(temp_dir, ignore_errors=True)

        # Smoke test.
        result = subprocess.run(
            [str(cloudflared_path), "version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            version_line = (result.stdout or result.stderr).strip().splitlines()[0]
            log(f"cloudflared installed: {version_line}")
            return True, str(cloudflared_path)

        log("cloudflared install verification failed.")
        return False, None

    except Exception as e:
        log(f"Failed to install cloudflared: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, None


# --------------------------------------------------------------------------- #
# Tunnel lifecycle
# --------------------------------------------------------------------------- #
_tunnel_process: Optional[subprocess.Popen] = None


def _read_tunnel_url(proc: subprocess.Popen, timeout: int = 60) -> Optional[str]:
    """Scan cloudflared's stderr (quick tunnels log there) for the public URL.

    A quick tunnel prints a line like::

        |  https://some-random-words.trycloudflare.com   |

    We grab the first such URL we see.
    """
    deadline = time.time() + timeout
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)

    # cloudflared writes its banner / URL to stderr in quick-tunnel mode.
    while time.time() < deadline:
        if proc.stderr is None:
            time.sleep(0.2)
            continue
        line = proc.stderr.readline()
        if not line:
            if proc.poll() is not None:
                return None
            time.sleep(0.2)
            continue
        text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
        sys.stderr.write(text)
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def start_tunnel(port: int = 5000, log=print) -> Optional[str]:
    """Start a Cloudflare quick tunnel pointing at ``http://localhost:<port>``.

    Blocks until the URL is known (or the tunnel fails). Returns the public
    URL on success, or ``None`` on failure. The tunnel subprocess runs for
    the lifetime of the Python process — killing Python tears it down.
    """
    global _tunnel_process

    ok, cloudflared_path = install(log=log)
    if not ok:
        log("cloudflared not available — skipping tunnel. "
            "The Flask app will still run on localhost.")
        return None

    log(f"Starting Cloudflare quick tunnel → http://localhost:{port} ...")
    try:
        _tunnel_process = subprocess.Popen(
            [
                cloudflared_path,
                "tunnel",
                "--no-autoupdate",
                "--url", f"http://localhost:{port}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        log(f"Failed to launch cloudflared: {e}")
        return None

    url = _read_tunnel_url(_tunnel_process, timeout=60)
    if not url:
        log("Could not detect the tunnel URL (cloudflared may have failed to start).")
        log("Falling back to localhost-only mode.")
        stop_tunnel()
        return None

    log("")
    log("=" * 60)
    log("  Public URL (share this with whoever needs the dashboard):")
    log(f"    {url}")
    log("=" * 60)
    log("")
    log("The tunnel stays up as long as this Python process is running.")
    log("Stop the cell / kernel to tear it down.")
    return url


def stop_tunnel() -> None:
    global _tunnel_process
    if _tunnel_process and _tunnel_process.poll() is None:
        try:
            _tunnel_process.terminate()
            try:
                _tunnel_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _tunnel_process.kill()
        except Exception:
            pass
    _tunnel_process = None


if __name__ == "__main__":
    # Manual smoke test: ``python cloudflare_tunnel.py``
    print(f"Colab detected: {is_colab()}")
    print(f"OS={_OS_NAME}  ARCH={_ARCH}")
    print(f"URL={CLOUDFLARED_URL}")
    ok, path = install()
    print(f"Installed: {ok}  path={path}")
