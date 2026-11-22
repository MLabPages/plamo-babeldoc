"""PLaMo 論文リーダー（Windows アプリ）の起動ファイル。

  .venv\Scripts\pythonw.exe app.py            アプリの窓で開く
  .venv\Scripts\python.exe  app.py --browser  ブラウザで開く
"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser
import ctypes

import json
import urllib.request

from paperapp.config import LOCAL_PORT, SHARE_PORT, load_settings
from paperapp.server import App


class Api:
    """画面の JavaScript から呼ぶ機能（window.pywebview.api）。"""

    def __init__(self) -> None:
        # 先頭の "_" で、pywebview が画面へ公開する対象から外す（窓オブジェクトをたどると固まる）
        self._window = None

    def save_pdf(self, doc_id: str, kind: str, engine: str) -> dict:
        import shutil

        from paperapp.server import ID_RE, LIBRARY_DIR, pdf_download_name, pdf_path

        try:
            if not ID_RE.match(doc_id or ""):
                raise KeyError(doc_id)
            doc_dir = LIBRARY_DIR / doc_id
            src = pdf_path(doc_dir, kind, engine)
            if not src.exists():
                return {"error": "PDFが見つかりません。"}
            meta = json.loads((doc_dir / "meta.json").read_text(encoding="utf-8"))
            import webview

            chosen = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=pdf_download_name(meta, kind),
                file_types=("PDF (*.pdf)",))
            if not chosen:
                return {}
            dest = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
            if not str(dest).lower().endswith(".pdf"):
                dest = str(dest) + ".pdf"
            shutil.copyfile(src, dest)
            return {"saved": str(dest)}
        except KeyError:
            return {"error": "PDFが見つかりません。"}
        except OSError as e:
            return {"error": f"保存できませんでした: {e}"}

    def choose_folder(self, start: str = "") -> str:
        import webview

        chosen = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start or "")
        if not chosen:
            return ""
        return str(chosen[0] if isinstance(chosen, (list, tuple)) else chosen)

ICON = __import__("pathlib").Path(__file__).resolve().parent / "assets" / "app.ico"


def set_window_icon(window) -> None:
    """窓とタスクバーにアプリのアイコンを付ける（WinForms 版 pywebview）。"""
    try:
        from System import Action  # type: ignore[import-not-found]
        from System.Drawing import Icon  # type: ignore[import-not-found]

        form = window.native
        form.Invoke(Action(lambda: setattr(form, "Icon", Icon(str(ICON)))))
    except Exception:
        pass


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        if port == SHARE_PORT:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("空いているポートがありません")


def running_instance(token: str) -> str | None:
    """すでに起動中のアプリがあればその URL を返す（二重起動しない）。"""
    for port in [LOCAL_PORT] + list(range(SHARE_PORT + 1, SHARE_PORT + 10)):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers={"X-Token": token})
            with urllib.request.urlopen(req, timeout=1) as r:  # noqa: S310
                if "engines" in json.loads(r.read().decode("utf-8")):
                    return f"http://127.0.0.1:{port}/?t={token}"
        except Exception:
            continue
    return None


def main() -> None:
    if sys.platform == "win32":
        # Use the same identity as the Start-menu shortcut, independently of Python.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PLaMo.PaperReader.Desktop")
    token = load_settings()["share_token"]
    url = running_instance(token)
    app = None
    if url is None:
        app = App()
        port = free_port(LOCAL_PORT)
        app.start_local(port)
        url = f"http://127.0.0.1:{port}/?t={token}"
    try:
        if "--serve" in sys.argv:
            print(url, flush=True)
            threading.Event().wait()
        elif "--browser" in sys.argv:
            webbrowser.open(url)
            print("ブラウザで開きました。終了するには Ctrl+C を押してください。")
            threading.Event().wait()
        else:
            import webview

            api = Api()
            window = webview.create_window("PLaMo 論文リーダー", url, width=1320, height=900, min_size=(760, 560),
                                           js_api=api)
            api._window = window
            window.events.shown += lambda: set_window_icon(window)
            webview.start(private_mode=False)
    except KeyboardInterrupt:
        pass
    finally:
        if app is not None:
            app.shutdown()


if __name__ == "__main__":
    main()
