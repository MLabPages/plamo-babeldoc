from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
LLAMA_EXE = ROOT / "llama" / "llama-server.exe"
LIBRARY_DIR = ROOT / "library"
GLOSSARY_FILE = ROOT / "glossary.csv"
STATIC_DIR = Path(__file__).resolve().parent / "static"
LLAMA_PORT = 8090
LLAMA_URL = f"http://127.0.0.1:{LLAMA_PORT}"
LOCAL_PORT = 8765
SHARE_PORT = 8766

SETTINGS_DIR = Path(os.environ.get("APPDATA", str(ROOT))) / "PLaMoPaperReader"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "engine": "plamo-2b",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "share_token": "",
}

_lock = threading.Lock()


def load_settings() -> dict:
    with _lock:
        data = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        if not data.get("share_token"):
            data["share_token"] = secrets.token_urlsafe(18)
            _write(data)
        return data


def save_settings(update: dict) -> dict:
    data = load_settings()
    with _lock:
        data.update(update)
        _write(data)
    return data


def _write(data: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)
