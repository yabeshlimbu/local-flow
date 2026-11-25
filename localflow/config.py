"""Settings storage. Everything lives in ~/Library/Application Support/LocalFlow."""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

APP_DIR = Path.home() / "Library" / "Application Support" / "LocalFlow"
APP_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = APP_DIR / "settings.json"
DB_PATH = APP_DIR / "localflow.db"
RECORDINGS_DIR = APP_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)

DEFAULTS: dict = {
    # --- Hotkeys -----------------------------------------------------------
    # "fn", "right_option", "right_command", "right_control", "right_shift"
    "dictation_key": "fn",
    # Hold the dictation key together with this modifier for Command Mode.
    "command_modifier": "control",
    # Double-tap the dictation key to lock hands-free recording.
    "hands_free_double_tap": True,
    # --- Speech recognition -----------------------------------------------
    "whisper_model": "mlx-community/whisper-large-v3-turbo",
    "language": "auto",  # "auto" or ISO code like "en", "es", "ne", "hi"
    "whisper_mode": True,  # boost quiet / whispered speech
    "sounds": True,
    "input_device": None,  # None = system default
    # --- AI editing (Ollama, fully local) ---------------------------------
    "ollama_url": "http://127.0.0.1:11434",
    "llm_model": "qwen2.5:7b",
    "ai_edits": True,  # filler removal, backtracking, punctuation, lists
    "command_mode": True,
    # Styles per app category: formal | casual | very_casual | none
    "styles": {
        "personal_messages": "casual",
        "work_messages": "casual",
        "email": "formal",
        "other": "none",
    },
    # app bundle id (lowercase substring) -> category
    "app_categories": {
        "com.apple.mobilesms": "personal_messages",
        "net.whatsapp": "personal_messages",
        "com.facebook.messenger": "personal_messages",
        "org.telegram": "personal_messages",
        "ru.keepcoder.telegram": "personal_messages",
        "com.hnc.discord": "personal_messages",
        "com.tinyspeck.slackmacgap": "work_messages",
        "com.microsoft.teams": "work_messages",
        "com.microsoft.teams2": "work_messages",
        "com.apple.mail": "email",
        "com.microsoft.outlook": "email",
        "com.readdle.smartemail": "email",
        "com.superhuman": "email",
    },
    # --- Personalisation ----------------------------------------------------
    "dictionary": [],  # list of words / names: ["Priya", "Kubernetes"]
    "replacements": {},  # misheard -> correct  {"cube ernetes": "Kubernetes"}
    "snippets": {},  # trigger phrase -> expansion
    "auto_learn": True,  # learn capitalised names from your corrections in History
    # --- Misc -----------------------------------------------------------------
    "dashboard_port": 8765,
    "max_recording_seconds": 360,
    "restore_clipboard": True,
}


class Settings:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        if SETTINGS_PATH.exists():
            try:
                saved = json.loads(SETTINGS_PATH.read_text())
                for k, v in saved.items():
                    if isinstance(v, dict) and isinstance(self._data.get(k), dict):
                        self._data[k].update(v)
                    else:
                        self._data[k] = v
            except Exception as exc:  # corrupt file: keep defaults, back it up
                SETTINGS_PATH.rename(SETTINGS_PATH.with_suffix(".bad.json"))
                print(f"[settings] could not read settings ({exc}); using defaults")
        self.save()

    def __getitem__(self, key):
        with self._lock:
            return copy.deepcopy(self._data[key])

    def get(self, key, default=None):
        with self._lock:
            return copy.deepcopy(self._data.get(key, default))

    def all(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def update(self, values: dict) -> None:
        with self._lock:
            for k, v in values.items():
                if k in DEFAULTS:
                    self._data[k] = v
            self.save()

    def save(self) -> None:
        with self._lock:
            tmp = SETTINGS_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
            tmp.replace(SETTINGS_PATH)


settings = Settings()
