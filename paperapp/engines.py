from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request

from .config import LLAMA_EXE, LLAMA_PORT, LLAMA_URL, MODELS_DIR, ROOT

LOCAL_MODELS = {
    "plamo-0.8b": {
        "label": "PLaMo 0.8B（最速）",
        "file": "plamo-3-translate-0.8b-Q4_K_M.gguf",
        "alias": "plamo-3-translate-0.8b",
    },
    "plamo-2b": {
        "label": "PLaMo 2B（標準）",
        "file": "plamo-3-translate-2b-Q4_K_M.gguf",
        "alias": "plamo-3-translate-2b",
    },
    "plamo-8b": {
        "label": "PLaMo 8B（高品質・遅め）",
        "file": "plamo-3-translate-8b-Q4_K_M.gguf",
        "alias": "plamo-3-translate-8b",
    },
}
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def engine_label(engine: str, settings: dict | None = None) -> str:
    if engine in LOCAL_MODELS:
        return LOCAL_MODELS[engine]["label"]
    if engine == "gemini":
        model = (settings or {}).get("gemini_model") or "Gemini"
        return f"Gemini（{model}）"
    return engine


def engine_list(settings: dict) -> list[dict]:
    items = []
    for key, info in LOCAL_MODELS.items():
        ok = (MODELS_DIR / info["file"]).exists()
        items.append({
            "id": key,
            "label": info["label"],
            "kind": "local",
            "available": ok,
            "note": "PC内で翻訳します。論文は外部に送られません。" if ok else "モデルファイルがありません。",
        })
    has_key = bool(settings.get("gemini_api_key"))
    items.append({
        "id": "gemini",
        "label": engine_label("gemini", settings),
        "kind": "cloud",
        "available": has_key,
        "note": "論文の本文をGoogleのGemini APIへ送って翻訳します。"
        if has_key else "設定でGeminiのAPIキーを登録すると使えます。",
    })
    return items


def _get_json(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 (localhost)
        return json.loads(r.read().decode("utf-8"))


class LlamaManager:
    """PLaMo を動かす llama-server を 1 つだけ起動し、必要に応じてモデルを入れ替える。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None

    def current_alias(self) -> str | None:
        try:
            data = _get_json(f"{LLAMA_URL}/v1/models")
            return data["data"][0]["id"]
        except Exception:
            return None

    def ensure(self, engine: str) -> None:
        info = LOCAL_MODELS[engine]
        with self.lock:
            current = self.current_alias()
            if current == info["alias"]:
                return
            if current is not None or self._port_busy():
                self.stop_locked()
            model = MODELS_DIR / info["file"]
            log = open(ROOT / "server.err.log", "ab")  # noqa: SIM115
            self.proc = subprocess.Popen(
                [str(LLAMA_EXE), "-m", str(model), "--host", "127.0.0.1", "--port", str(LLAMA_PORT),
                 "-ngl", "99", "-c", "16384", "-np", "4", "--jinja", "--alias", info["alias"]],
                cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=log, creationflags=NO_WINDOW,
            )
            deadline = time.time() + 240
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError("翻訳モデルの起動に失敗しました（server.err.log を確認してください）。")
                if self.current_alias() == info["alias"] and self._healthy():
                    return
                time.sleep(1)
            raise RuntimeError("翻訳モデルの起動が時間内に終わりませんでした。")

    def _healthy(self) -> bool:
        try:
            return _get_json(f"{LLAMA_URL}/health").get("status") == "ok"
        except Exception:
            return False

    def _port_busy(self) -> bool:
        try:
            urllib.request.urlopen(f"{LLAMA_URL}/health", timeout=1)  # noqa: S310
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            return False

    def stop(self) -> None:
        with self.lock:
            self.stop_locked()

    def stop_locked(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        # 以前に start_server.ps1 で起動したものも止める（このフォルダの llama-server だけ）
        exe = str(LLAMA_EXE).replace("'", "''")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process llama-server -ErrorAction SilentlyContinue | "
             f"Where-Object {{ $_.Path -eq '{exe}' }} | Stop-Process -Force"],
            creationflags=NO_WINDOW, check=False, capture_output=True,
        )
        for _ in range(20):
            if not self._port_busy():
                break
            time.sleep(0.5)
