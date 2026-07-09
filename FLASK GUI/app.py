from flask import Flask, render_template, request, jsonify
from datetime import datetime
import core

app = Flask(__name__)


def current_profile():
    return core.ProfileManager.get_active()


@app.route("/")
def index():
    profile = current_profile()
    profiles = core.ProfileManager.list_profiles()
    theme = core.Preferences.get("theme", "dark")
    if not profile:
        return render_template("wizard.html", os_info=core.os_report(), theme=theme)
    return render_template("index.html", profile=profile, profiles=profiles,
                            os_info=core.os_report(), theme=theme)


@app.route("/wizard")
def wizard():
    theme = core.Preferences.get("theme", "dark")
    return render_template("wizard.html", os_info=core.os_report(), theme=theme)


@app.route("/help")
def help_page():
    theme = core.Preferences.get("theme", "dark")
    return render_template("help.html", os_info=core.os_report(), theme=theme)


# ---------- Preferences ----------

@app.route("/api/theme", methods=["POST"])
def set_theme():
    theme = request.json.get("theme", "dark")
    core.Preferences.set("theme", theme)
    return jsonify({"ok": True, "theme": theme})


@app.route("/api/os")
def api_os():
    return jsonify(core.os_report())


# ---------- Setup wizard ----------

@app.route("/api/rclone/install", methods=["POST"])
def api_install_rclone():
    logs = []
    ok, path = core.RcloneInstaller.install(log=lambda m: logs.append(m))
    return jsonify({"ok": ok, "path": path, "logs": logs})


@app.route("/api/profile/verify", methods=["POST"])
def api_verify_profile():
    data = request.json or {}
    fake_profile = {
        "name": data.get("name", "default"),
        "rclone_config": data.get("rclone_config", ""),
    }
    checker = core.RcloneQuery(fake_profile)
    results = {}
    for remote in ["PIKKY", "GDRIVE" if data.get("destination", "gdrive") == "gdrive" else "WEBDAV"]:
        ok, out, err = checker._run(["lsd", f"{remote}:"])
        results[remote] = {"ok": ok, "error": err if not ok else None}
    return jsonify(results)


@app.route("/api/profile/save", methods=["POST"])
def api_save_profile():
    data = request.json or {}
    name = data.get("name", "default")
    core.ProfileManager.save(
        name=name,
        rclone_config=data.get("rclone_config"),
        webdav_url=data.get("webdav_url"),
        webdav_user=data.get("webdav_user"),
        webdav_pass=data.get("webdav_pass"),
        default_destination=data.get("default_destination", "gdrive"),
    )
    return jsonify({"ok": True})


@app.route("/api/profile/switch", methods=["POST"])
def api_switch_profile():
    name = (request.json or {}).get("name")
    core.Preferences.set("active_profile", name)
    return jsonify({"ok": True})


@app.route("/api/profile/delete", methods=["POST"])
def api_delete_profile():
    name = (request.json or {}).get("name")
    core.ProfileManager.delete(name)
    return jsonify({"ok": True})


@app.route("/api/profile/next_name")
def api_profile_next_name():
    return jsonify({"name": core.ProfileManager.next_name()})


# ---------- Transfers ----------

@app.route("/api/transfer/start", methods=["POST"])
def api_transfer_start():
    profile = current_profile()
    if not profile:
        return jsonify({"ok": False, "error": "No active profile"}), 400
    destination = (request.json or {}).get("destination", profile.get("default_destination", "gdrive"))
    job = core.get_job(profile["name"], profile)
    ok, message = job.start(destination_type=destination)
    return jsonify({"ok": ok, "message": message})


@app.route("/api/transfer/stop", methods=["POST"])
def api_transfer_stop():
    profile = current_profile()
    if not profile:
        return jsonify({"ok": False, "error": "No active profile"}), 400
    job = core.get_job(profile["name"], profile)
    job.stop()
    return jsonify({"ok": True})


@app.route("/api/transfer/status")
def api_transfer_status():
    profile = current_profile()
    if not profile:
        return jsonify({"status": "no_profile"})
    job = core.get_job(profile["name"], profile)
    return jsonify(job.snapshot())


@app.route("/api/history")
def api_history():
    profile = current_profile()
    if not profile:
        return jsonify({"transfers": []})
    transfers = core.ProfileManager.get_transfers(profile["id"])
    return jsonify({"transfers": transfers})


# ---------- Storage stats ----------

@app.route("/api/stats/pikpak")
def api_stats_pikpak():
    profile = current_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 400
    q = core.RcloneQuery(profile)
    about = q.about("PIKKY")
    videos = q.videos("PIKKY")
    return jsonify({"about": about, "videos": videos})


@app.route("/api/stats/drive")
def api_stats_drive():
    profile = current_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 400
    q = core.RcloneQuery(profile)
    remote = "WEBDAV" if profile.get("default_destination") == "webdav" else "GDRIVE"
    about = q.about(remote)
    return jsonify({"about": about, "remote": remote})


@app.route("/api/stats/drive/list")
def api_stats_drive_list():
    profile = current_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 400
    q = core.RcloneQuery(profile)
    remote = "WEBDAV" if profile.get("default_destination") == "webdav" else "GDRIVE"
    path = request.args.get("path", "")
    return jsonify(q.list_dir(remote, path))


# ---------- Clear / cleanup ----------

@app.route("/api/pikpak/clear", methods=["POST"])
def api_pikpak_clear():
    profile = current_profile()
    if not profile:
        return jsonify({"ok": False, "error": "No active profile"}), 400
    job = core.get_job(profile["name"], profile)
    if job.status == "running":
        return jsonify({"ok": False, "error": "Stop the current transfer before clearing PikPak."}), 400
    q = core.RcloneQuery(profile)
    result = q.clear("PIKKY")
    return jsonify(result)


@app.route("/api/drive/clear", methods=["POST"])
def api_drive_clear():
    profile = current_profile()
    if not profile:
        return jsonify({"ok": False, "error": "No active profile"}), 400
    data = request.json or {}
    path = (data.get("path") or "").strip().strip("/")
    if not path:
        return jsonify({"ok": False, "error": "Pick a folder to clear — the drive root can't be cleared from here."}), 400
    job = core.get_job(profile["name"], profile)
    if job.status == "running":
        return jsonify({"ok": False, "error": "Stop the current transfer before clearing the drive."}), 400
    q = core.RcloneQuery(profile)
    remote = "WEBDAV" if profile.get("default_destination") == "webdav" else "GDRIVE"
    result = q.clear(remote, path)
    return jsonify(result)


if __name__ == "__main__":
    # When run directly (rather than via run.py), pick a sensible bind address:
    # inside Google Colab we have to listen on 0.0.0.0 so cloudflared (a
    # separate child process) can reach the server; locally we stay on
    # loopback for safety. Use run.py if you want the auto-tunnel behaviour.
    import os as _os
    try:
        import cloudflare_tunnel as _cf
        _in_colab = _cf.is_colab()
    except Exception:
        _in_colab = False
    _host = _os.environ.get("RELAY_HOST", "0.0.0.0" if _in_colab else "127.0.0.1")
    _port = int(_os.environ.get("RELAY_PORT", "5005"))
    print(f"Relay starting on http://{_host}:{_port}")
    print("Tip: run `python run.py` to also start a Cloudflare tunnel in Colab.")
    app.run(host=_host, port=_port, debug=False, use_reloader=False)
