from __future__ import annotations

import json
import os
import secrets
import threading
import time
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
    "gemini_model": "gemini-3.8-flash",
    "translate_references": False,
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
        changed = False
        if "gemini_api_key" in data:
            # API キーは環境変数で渡す方式に変えたため、以前の保存分は消す
            data.pop("gemini_api_key", None)
            changed = True
        if data.get("gemini_model") == "gemini-2.5-flash":
            data["gemini_model"] = DEFAULT_SETTINGS["gemini_model"]
            changed = True
        if not data.get("share_token"):
            data["share_token"] = secrets.token_urlsafe(18)
            changed = True
        if changed:
            try:
                _write(data)
            except OSError:
                pass  # 書き込めなくても読み込んだ値で続ける
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
    replace_file(tmp, SETTINGS_FILE)


def replace_file(src: Path, dst: Path, timeout: float = 2.0) -> None:
    """Atomically replace dst with src.

    On Windows the replacement is refused while another reader (the library screen polling
    meta.json, an indexer or antivirus) has the file open, so retry briefly.
    """
    deadline = time.monotonic() + timeout
    delay = .02
    while True:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, .2)
