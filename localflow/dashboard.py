"""Local web dashboard on 127.0.0.1 (never exposed to the network)."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import sounddevice as sd
from flask import Flask, jsonify, request, send_file

from . import editor, llm, storage
from .config import DEFAULTS, settings
from .notetaker import ask_meetings, notetaker

STATIC = Path(__file__).parent / "static"
app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
_ui = None  # LocalFlowApp, for syncing menu toggles


ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


@app.before_request
def block_cross_site():
    """Only the dashboard itself may use the API. Blocks other websites (CSRF) and
    DNS-rebinding attacks from reading or changing LocalFlow data."""
    from flask import abort
    host = (request.host or "").rsplit(":", 1)[0]
    if host not in ALLOWED_HOSTS:
        abort(403)
    origin = request.headers.get("Origin")
    if origin and origin.split("://", 1)[-1].rsplit(":", 1)[0] not in ALLOWED_HOSTS:
        abort(403)
    if request.method not in ("GET", "HEAD") and request.path.startswith("/api/"):
        # application/json can't be sent cross-site without a CORS preflight we never allow
        if not (request.content_type or "").startswith("application/json"):
            abort(415)


def _local_url(url: str) -> bool:
    from urllib.parse import urlparse
    return (urlparse(str(url)).hostname or "") in ALLOWED_HOSTS | {"::1"}


@app.get("/")
def index():
    return send_file(STATIC / "index.html")


@app.get("/api/state")
def state():
    try:
        devices = [{"index": i, "name": d["name"]} for i, d in enumerate(sd.query_devices())
                   if d["max_input_channels"] > 0]
    except Exception:
        devices = []
    return jsonify({
        "settings": settings.all(),
        "stats": storage.stats(),
        "models": llm.available_models(),
        "devices": devices,
        "ready": bool(_ui and _ui.engine.ready),
        "notetaker": {"active": notetaker.active, "status": notetaker.status,
                      "transcript": notetaker.transcript() if notetaker.active else ""},
    })


@app.post("/api/settings")
def save_settings():
    data = request.get_json(force=True) or {}
    clean = {k: v for k, v in data.items() if k in DEFAULTS}
    if "ollama_url" in clean and not _local_url(clean["ollama_url"]):
        return jsonify({"ok": False, "error": "Ollama URL must be on this Mac"}), 400
    settings.update(clean)
    if _ui:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(_ui.sync_toggles)
    return jsonify({"ok": True, "settings": settings.all()})


@app.get("/api/history")
def history():
    return jsonify(storage.list_dictations(500, request.args.get("q", "")))


@app.delete("/api/history/<int:rid>")
def history_delete(rid):
    storage.delete_dictation(rid)
    return jsonify({"ok": True})


@app.delete("/api/history")
def history_clear():
    storage.clear_dictations()
    return jsonify({"ok": True})


@app.post("/api/learn")
def learn():
    d = request.get_json(force=True)
    words = editor.learn_from_correction(d.get("original", ""), d.get("corrected", ""))
    return jsonify({"learned": words})


@app.post("/api/test-edit")
def test_edit():
    d = request.get_json(force=True)
    return jsonify(editor.polish(d.get("text", ""), d.get("app", "")))


@app.get("/api/meetings")
def meetings():
    return jsonify(storage.list_meetings())


@app.get("/api/meetings/<int:mid>")
def meeting(mid):
    m = storage.get_meeting(mid)
    if m:
        m.pop("embedding", None)
    return jsonify(m)


@app.post("/api/meetings/<int:mid>")
def meeting_update(mid):
    d = request.get_json(force=True)
    storage.update_meeting(mid, **{k: v for k, v in d.items() if k in ("title", "notes")})
    return jsonify({"ok": True})


@app.delete("/api/meetings/<int:mid>")
def meeting_delete(mid):
    storage.delete_meeting(mid)
    return jsonify({"ok": True})


@app.post("/api/notetaker/toggle")
def notetaker_toggle():
    if _ui:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(_ui.toggle_meeting)
    return jsonify({"ok": True})


@app.post("/api/notetaker/notes")
def notetaker_notes():
    notetaker.notes = (request.get_json(force=True) or {}).get("notes", "")
    return jsonify({"ok": True})


@app.post("/api/notetaker/catchup")
def notetaker_catchup():
    try:
        return jsonify({"answer": notetaker.catch_up()})
    except llm.LLMError as exc:
        return jsonify({"answer": f"Error: {exc}"})


@app.post("/api/ask")
def ask():
    q = (request.get_json(force=True) or {}).get("question", "")
    try:
        return jsonify(ask_meetings(q))
    except llm.LLMError as exc:
        return jsonify({"answer": f"Error: {exc}", "sources": []})


def serve(ui=None) -> None:
    global _ui
    _ui = ui
    app.run(host="127.0.0.1", port=settings["dashboard_port"], threaded=True, use_reloader=False)


if __name__ == "__main__":  # dashboard-only mode, handy for development
    storage.init()
    threading.Thread(target=serve, daemon=True).start()
    import time
    while True:
        time.sleep(3600)
