from flask import Flask, render_template, request, jsonify
from datetime import datetime
import os
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

@app.route("/fast-setup")
def fast_setup():
    theme = core.Preferences.get("theme", "dark")
    return render_template("fast_setup.html", theme=theme)


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
    destination = data.get("destination", "gdrive")
    remotes = ["PIKKY"]
    if destination == "gdrive":
        remotes.append("GDRIVE")
    elif destination == "webdav":
        remotes.append("WEBDAV")
    # local storage has no remote to verify — just PIKKY needs checking
    results = {}
    for remote in remotes:
        ok, out, err = checker._run(["lsd", f"{remote}:"])
        results[remote] = {"ok": ok, "error": err if not ok else None}
    if destination == "local":
        path = data.get("local_destination_path") or ""
        try:
            import os as _os
            _os.makedirs(path or str(__import__("pathlib").Path.home() / "PikpakTransfers"), exist_ok=True)
            results["LOCAL"] = {"ok": True, "error": None}
        except Exception as e:
            results["LOCAL"] = {"ok": False, "error": str(e)}
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
        local_destination_path=data.get("local_destination_path"),
        default_destination=data.get("default_destination", "gdrive"),
    )
    return jsonify({"ok": True})


@app.route("/api/profile/local_path", methods=["POST"])
def api_set_local_path():
    profile = current_profile()
    if not profile:
        return jsonify({"ok": False, "error": "No active profile"}), 400
    path = (request.json or {}).get("path", "").strip()
    if not path:
        return jsonify({"ok": False, "error": "Pick a folder first."}), 400
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    core.ProfileManager.set_local_path(profile["name"], path)
    return jsonify({"ok": True, "path": path})


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
    data = request.json or {}
    destination = data.get("destination", profile.get("default_destination", "gdrive"))
    selected_paths = data.get("selected_paths") or []
    job = core.get_job(profile["name"], profile)
    ok, message = job.start(destination_type=destination, selected_paths=selected_paths)
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


def _dest_remote(profile):
    dest = profile.get("default_destination")
    if dest == "webdav":
        return "WEBDAV"
    if dest == "local":
        return "LOCAL"
    return "GDRIVE"


@app.route("/api/stats/drive")
def api_stats_drive():
    profile = current_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 400
    q = core.RcloneQuery(profile)
    remote = _dest_remote(profile)
    about = q.about(remote)
    return jsonify({"about": about, "remote": remote})


@app.route("/api/stats/drive/list")
def api_stats_drive_list():
    profile = current_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 400
    q = core.RcloneQuery(profile)
    remote = _dest_remote(profile)
    path = request.args.get("path", "")
    return jsonify(q.list_dir(remote, path))


# ---------- Storage browsing (for file/folder selection) ----------

@app.route("/api/browse/source")
def api_browse_source():
    """Browse the PikPak (source) remote — used to pick specific files/folders to transfer."""
    profile = current_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 400
    q = core.RcloneQuery(profile)
    path = request.args.get("path", "")
    return jsonify(q.list_dir("PIKKY", path))


@app.route("/api/browse/dest")
def api_browse_dest():
    """Browse the current destination (gdrive / webdav / local) — read only."""
    profile = current_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 400
    q = core.RcloneQuery(profile)
    remote = _dest_remote(profile)
    path = request.args.get("path", "")
    return jsonify(q.list_dir(remote, path))


@app.route("/api/browse/fs")
def api_browse_fs():
    """Browse the local filesystem — used for the local-storage destination folder picker."""
    path = request.args.get("path") or None
    return jsonify(core.browse_filesystem(path))


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
    remote = _dest_remote(profile)
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
