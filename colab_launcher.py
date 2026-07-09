# ============================================================
#  PIKKY-WEB — One-Cell Colab Launcher
#  Paste this entire cell into Google Colab and run it.
#  A public https://xxxxx.trycloudflare.com URL will appear.
# ============================================================

import subprocess, sys, os, threading, time

# Always work from /content so re-running the cell is safe
BASE_DIR  = "/content"
REPO_URL  = "https://github.com/AnonymousV73X/PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT.git"
REPO_DIR  = os.path.join(BASE_DIR, "PIKPAK-TO-GOOGLE-DRIVE-TELEGRAM-BOT")
GUI_DIR   = os.path.join(REPO_DIR, "FLASK GUI")

# 1. Clone or update repo
if not os.path.exists(REPO_DIR):
    subprocess.run(["git", "clone", REPO_URL, REPO_DIR], check=True)
else:
    print("[*] Repo already cloned, pulling latest...")
    subprocess.run(["git", "-C", REPO_DIR, "pull"], check=True)

# 2. Install requirements
print("[*] Installing requirements...")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "-r", os.path.join(GUI_DIR, "requirements.txt")],
    check=True
)
print("[*] Requirements installed.")

# 3. Set env vars so app.py binds to 0.0.0.0
os.environ["RELAY_HOST"] = "0.0.0.0"
os.environ["RELAY_PORT"] = "5000"

# 4. Start the Cloudflare tunnel in a background thread
def start_tunnel():
    time.sleep(2)  # Give Flask a moment to bind
    sys.path.insert(0, GUI_DIR)
    try:
        import cloudflare_tunnel
        cloudflare_tunnel.start_tunnel(port=5000)
    except Exception as e:
        print(f"[tunnel] error: {e}")

tunnel_thread = threading.Thread(target=start_tunnel, daemon=True)
tunnel_thread.start()

# 5. Run app.py (blocking — tunnel URL prints from the thread above)
print("\n" + "="*60)
print("  Launching Pikky-Web GUI...")
print("  Wait for the trycloudflare.com URL to appear below.")
print("="*60 + "\n")

os.chdir(GUI_DIR)
subprocess.run([sys.executable, "app.py"])
