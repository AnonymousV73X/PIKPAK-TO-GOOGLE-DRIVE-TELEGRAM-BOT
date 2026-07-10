#!/usr/bin/env python3
"""
run.py
------
Unified entry point for the Relay (PikPak → Google Drive / WebDAV) web app.

Behaviour is determined by the runtime environment:

  • Google Colab  →  bind Flask to 0.0.0.0 (so the tunnel can reach it),
                     disable the reloader, fire up a Cloudflare quick tunnel,
                     and print the public ``https://<random>.trycloudflare.com``
                     URL to the cell output.
  • Local machine →  bind Flask to 127.0.0.1:5000 (loopback only, no tunnel),
                     keeping the original local-only behaviour.

You can override the auto-detection with environment variables:

  • ``RELAY_HOST=0.0.0.0``        — bind a specific interface
  • ``RELAY_PORT=8080``           — bind a specific port
  • ``RELAY_TUNNEL=1``            — force the Cloudflare tunnel on (even locally)
  • ``RELAY_TUNNEL=0``            — force the tunnel off (even in Colab)

Examples
--------
Local run::

    python run.py

Force a tunnel from your laptop (e.g. to share a transfer with a friend)::

    RELAY_TUNNEL=1 python run.py

Run inside a Colab cell::

    !git clone https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT.git
    %cd PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT/pikky-web
    !pip install -r requirements.txt
    !python run.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

# Importing app also runs core.init_db() as a side-effect, which we want.
import app as app_module
import cloudflare_tunnel


# --------------------------------------------------------------------------- #
# Configuration (env-var overridable).
# --------------------------------------------------------------------------- #
def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    in_colab = cloudflare_tunnel.is_colab()

    # Tunnel: forced on/off via env, otherwise on iff Colab.
    want_tunnel = _env_bool("RELAY_TUNNEL", default=in_colab)

    # In Colab we must bind 0.0.0.0 so the cloudflared process (a separate
    # child) can reach the Flask server. Locally we keep 127.0.0.1 so the
    # dashboard isn't exposed to the LAN.
    default_host = "0.0.0.0" if (in_colab or want_tunnel) else "127.0.0.1"
    host = _env("RELAY_HOST", default_host)
    port = int(_env("RELAY_PORT", "5005"))

    print("=" * 60)
    print("  Relay — PikPak → Google Drive / WebDAV")
    print(f"  Environment : {'Google Colab' if in_colab else 'Local'}")
    print(f"  Bind        : http://{host}:{port}")
    print(f"  Tunnel      : {'on (cloudflared quick tunnel)' if want_tunnel else 'off'}")
    print("=" * 60)
    print()

    # The Flask reloader spawns a child process, which would start a *second*
    # cloudflared tunnel and confuse the URL detection. Always disable it
    # when we're managing the lifecycle ourselves.
    app_module.app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
    )

    return 0


if __name__ == "__main__":
    # If a tunnel was requested, start it in a background thread BEFORE
    # Flask takes over the main thread. cloudflared will retry-connect
    # until Flask is up, so the ordering is fine.
    want_tunnel = _env_bool("RELAY_TUNNEL", default=cloudflare_tunnel.is_colab())
    if want_tunnel:
        port = int(_env("RELAY_PORT", "5005"))

        def _tunnel_thread() -> None:
            # Give Flask a moment to bind, then start the tunnel.
            time.sleep(1.5)
            try:
                cloudflare_tunnel.start_tunnel(port=port)
            except Exception as exc:  # pragma: no cover — defensive
                print(f"[tunnel] failed: {exc}", file=sys.stderr)

        threading.Thread(target=_tunnel_thread, name="cf-tunnel", daemon=True).start()

    sys.exit(main())
