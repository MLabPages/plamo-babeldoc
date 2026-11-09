"""PLaMo 論文リーダー（Windows アプリ）の起動ファイル。

  .venv\Scripts\pythonw.exe app.py            アプリの窓で開く
  .venv\Scripts\python.exe  app.py --browser  ブラウザで開く
"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser

import json
import urllib.request

from paperapp.config import LOCAL_PORT, SHARE_PORT, load_settings
from paperapp.server import App

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

            window = webview.create_window("PLaMo 論文リーダー", url, width=1320, height=900, min_size=(760, 560))
            window.events.shown += lambda: set_window_icon(window)
            webview.start(private_mode=False)
    except KeyboardInterrupt:
        pass
    finally:
        if app is not None:
            app.shutdown()


if __name__ == "__main__":
    main()
