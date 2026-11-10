"""ローカル HTTP サーバー（Windows アプリの画面と iPad 共有の両方で使う）。"""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import LIBRARY_DIR, ROOT, SHARE_PORT, STATIC_DIR, load_settings, replace_file, save_settings
from .engines import NO_WINDOW, LlamaManager
from .envkeys import env_for_child, get_env
from .registry import ENGINES as REGISTRY
from .registry import PlamoEngine, engine_label, engine_list
from .reading import reading_is_current, write_reading

ID_RE = re.compile(r"^[a-z0-9]{6,32}$")
ENGINES = set(REGISTRY)
_reading_lock = threading.Lock()


def ensure_reading(doc_dir: Path, out: Path) -> None:
    """Rebuild reading data and PDF bookmarks made by an older version, once."""
    if not (out / "translated.pdf").exists() or reading_is_current(out):
        return
    with _reading_lock:
        if not reading_is_current(out):
            write_reading(out / "translated.pdf", doc_dir / "original.pdf", out)


def stage_label(stage: str) -> str:
    s = stage.lower()
    if "translate" in s or "term" in s:
        return "翻訳中"
    if "typeset" in s or "render" in s or "font" in s or "save" in s or "subset" in s:
        return "PDFを組み立て中"
    if "layout" in s or "parse" in s or "detect" in s or "table" in s or "paragraph" in s:
        return "レイアウトを解析中"
    return "処理中"


class Library:
    def __init__(self) -> None:
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def doc_dir(self, doc_id: str) -> Path:
        if not ID_RE.match(doc_id):
            raise KeyError(doc_id)
        return LIBRARY_DIR / doc_id

    def meta(self, doc_id: str) -> dict:
        p = self.doc_dir(doc_id) / "meta.json"
        if not p.exists():
            raise KeyError(doc_id)
        return json.loads(p.read_text(encoding="utf-8"))

    def save_meta(self, doc_id: str, meta: dict) -> None:
        p = self.doc_dir(doc_id) / "meta.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        replace_file(tmp, p)

    def update_translation(self, doc_id: str, engine: str, **kw) -> None:
        with self.lock:
            meta = self.meta(doc_id)
            meta.setdefault("translations", {}).setdefault(engine, {}).update(kw)
            self.save_meta(doc_id, meta)

    def list(self) -> list[dict]:
        out = []
        for d in LIBRARY_DIR.iterdir():
            if (d / "meta.json").exists():
                try:
                    out.append(json.loads((d / "meta.json").read_text(encoding="utf-8")))
                except ValueError:
                    pass
        return sorted(out, key=lambda m: m.get("created", 0), reverse=True)

    def add(self, filename: str, data: bytes) -> str:
        import pymupdf

        title = Path(filename).stem
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise ValueError("パスワード付きPDFです。解除したPDFを選んでください。")
                pages = doc.page_count
                if not pages:
                    raise ValueError("ページのないPDFは翻訳できません。")
                meta_title = (doc.metadata or {}).get("title") or ""
                if 8 < len(meta_title) < 300 and not meta_title.lower().endswith((".pdf", ".doc", ".docx")):
                    title = meta_title
        except (pymupdf.FileDataError, pymupdf.EmptyFileError) as e:
            raise ValueError("PDFを読み込めません。ファイルが壊れていないか確認してください。") from e
        doc_id = secrets.token_hex(6)
        d = self.doc_dir(doc_id)
        d.mkdir(parents=True)
        (d / "original.pdf").write_bytes(data)
        self.save_meta(doc_id, {"id": doc_id, "filename": filename, "title": title, "pages": pages,
                                "created": time.time(), "translations": {}})
        return doc_id

    def delete(self, doc_id: str) -> None:
        shutil.rmtree(self.doc_dir(doc_id), ignore_errors=True)


class Jobs:
    def __init__(self, library: Library, llama: LlamaManager) -> None:
        self.library = library
        self.llama = llama
        self.q: queue.Queue = queue.Queue()
        self.current: tuple[str, str] | None = None
        self.proc: subprocess.Popen | None = None
        threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, doc_id: str, engine: str, translate_references: bool | None = None) -> None:
        if translate_references is None:
            translate_references = bool(load_settings().get("translate_references"))
        with self.library.lock:
            tr = self.library.meta(doc_id).get("translations", {}).get(engine, {})
            if tr.get("status") in ("queued", "running"):
                return  # 連打や同時リクエストでも同じ翻訳は一度だけ受け付ける
            job_id = secrets.token_hex(8)
            self.library.update_translation(doc_id, engine, status="queued", progress=0, stage="順番待ち",
                                            error="", warning="", queued=time.time(), refs=translate_references,
                                            label=engine_label(engine, load_settings()), job_id=job_id)
            self.q.put((doc_id, engine, job_id))

    def _active(self, doc_id: str, engine: str, job_id: str) -> bool:
        try:
            tr = self.library.meta(doc_id).get("translations", {}).get(engine, {})
            return tr.get("job_id") == job_id and tr.get("status") in ("queued", "running")
        except KeyError:
            return False

    def _update(self, doc_id: str, engine: str, job_id: str, **kw) -> bool:
        with self.library.lock:
            if not self._active(doc_id, engine, job_id):
                return False
            self.library.update_translation(doc_id, engine, **kw)
            return True

    def cancel(self, doc_id: str, engine: str) -> None:
        with self.library.lock:
            tr = self.library.meta(doc_id).get("translations", {}).get(engine, {})
            if tr.get("status") in ("queued", "running"):
                self.library.update_translation(doc_id, engine, status="canceled", stage="中止しました")
            if self.current == (doc_id, engine) and self.proc and self.proc.poll() is None:
                self.proc.kill()

    def recover(self) -> None:
        for meta in self.library.list():
            for engine, tr in meta.get("translations", {}).items():
                if tr.get("status") in ("queued", "running"):
                    self.library.update_translation(meta["id"], engine, status="interrupted")
                    self.submit(meta["id"], engine, bool(tr.get("refs")))

    def _loop(self) -> None:
        while True:
            doc_id, engine, job_id = self.q.get()
            try:
                with self.library.lock:
                    if not self._active(doc_id, engine, job_id):
                        continue  # 中止済み、または再試行前の古いキュー項目
                    self.current = (doc_id, engine)
                self._run(doc_id, engine, job_id)
            except Exception as e:  # noqa: BLE001
                self._update(doc_id, engine, job_id, status="error", error=str(e))
            finally:
                with self.library.lock:
                    self.current = None
                    self.proc = None
                self.q.task_done()

    def _run(self, doc_id: str, engine: str, job_id: str) -> None:
        lib = self.library
        d = lib.doc_dir(doc_id)
        if not d.exists():
            return
        settings = load_settings()
        started = time.time()
        def update(**kw):
            return self._update(doc_id, engine, job_id, **kw)

        if not update(status="running", progress=0, stage="準備中",
                      started=started, label=engine_label(engine, settings)):
            return
        spec = REGISTRY[engine]
        ok, why = spec.available(settings)
        if not ok:
            raise RuntimeError(why)
        # API キーは環境変数のまま翻訳プロセスへ引き継ぐ（保存はしない）
        env = env_for_child(spec.child_env_names())
        env["PYTHONIOENCODING"] = "utf-8"
        refs = bool(lib.meta(doc_id).get("translations", {}).get(engine, {}).get("refs"))
        if isinstance(spec, PlamoEngine):
            if not update(stage="翻訳モデルを起動中"):
                return
            self.llama.ensure(engine)
        if not self._active(doc_id, engine, job_id):
            return
        out = d / "out" / engine
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        py = Path(sys.executable)
        if py.name.lower() != "python.exe":
            # pythonw.exe やアプリ名の PLaMoPaperReader.exe からは、コンソール版で翻訳プロセスを動かす
            py = Path(sys.prefix) / "Scripts" / "python.exe"
            if not py.exists():
                py = Path(sys.executable).with_name("python.exe")
        with lib.lock:
            if not self._active(doc_id, engine, job_id):
                return
            proc = subprocess.Popen(
                [str(py), "-m", "paperapp.worker", "--engine", engine,
                 "--input", str(d / "original.pdf"), "--outdir", str(out)]
                + (["--translate-references"] if refs else [])
                + (["--gemini-model", settings.get("gemini_model", "")] if engine == "gemini" else []),
                cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
            )
            self.proc = proc
        tail: list[str] = []
        error = ""
        warning = ""
        skipped_refs = 0
        last_write = 0.0
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.rstrip()
                if line.startswith("@@"):
                    try:
                        ev = json.loads(line[2:])
                    except ValueError:
                        continue
                    if ev.get("event") == "progress" and time.time() - last_write > 0.7:
                        last_write = time.time()
                        try:
                            update(progress=ev.get("progress", 0), stage=stage_label(ev.get("stage", "")))
                        except OSError:
                            pass  # 進み具合の表示だけなので、書けなくても翻訳は続ける
                    elif ev.get("event") == "error":
                        error = ev.get("error", "")
                    elif ev.get("event") == "warning":
                        warning = ev.get("warning", "")
                    elif ev.get("event") == "stats":
                        skipped_refs = int(ev.get("skipped_refs") or 0)
                elif line.strip():
                    tail = (tail + [line])[-25:]
            proc.wait()
        except BaseException:
            if proc.poll() is None:  # 翻訳プロセスを残したままにしない
                proc.kill()
            raise
        if not self._active(doc_id, engine, job_id):
            shutil.rmtree(out, ignore_errors=True)
            return
        log = out / "worker.log"
        log.write_text("\n".join(tail), encoding="utf-8")
        mono = next(iter(sorted(out.glob("*.mono.pdf"))), None)
        if proc.returncode != 0 or error or mono is None:
            msg = error or next((t for t in reversed(tail) if "Error" in t or "error" in t), "") or "翻訳に失敗しました。"
            update(status="error", error=msg[-400:])
            return
        replace_file(mono, out / "translated.pdf")
        dual = next(iter(sorted(out.glob("*.dual.pdf"))), None)
        if dual:
            replace_file(dual, out / "dual.pdf")
        if not update(stage="読書モードを準備中", progress=99):
            return
        data = write_reading(out / "translated.pdf", d / "original.pdf", out)
        updates = {"status": "done", "progress": 100, "stage": "完了", "error": "", "warning": warning, "skipped_refs": skipped_refs,
                   "seconds": round(time.time() - started, 1)}
        with lib.lock:
            if not self._active(doc_id, engine, job_id):
                return
            meta = lib.meta(doc_id)
            if data.get("title") and meta.get("title_ja") is None:
                meta["title_ja"] = data["title"]
                lib.save_meta(doc_id, meta)
            update(**updates)


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class App:
    def __init__(self) -> None:
        self.library = Library()
        self.llama = LlamaManager()
        self.jobs = Jobs(self.library, self.llama)
        self.share_server: ThreadingHTTPServer | None = None
        self.local_server: ThreadingHTTPServer | None = None

    @property
    def token(self) -> str:
        return load_settings()["share_token"]

    def share_info(self) -> dict:
        if not self.share_server:
            return {"enabled": False}
        url = f"http://{lan_ip()}:{SHARE_PORT}/?t={self.token}"
        return {"enabled": True, "url": url}

    def set_share(self, enable: bool) -> dict:
        if enable and not self.share_server:
            self.share_server = ThreadingHTTPServer(("0.0.0.0", SHARE_PORT), make_handler(self))  # noqa: S104
            threading.Thread(target=self.share_server.serve_forever, daemon=True).start()
        elif not enable and self.share_server:
            self.share_server.shutdown()
            self.share_server.server_close()
            self.share_server = None
        return self.share_info()

    def start_local(self, port: int) -> ThreadingHTTPServer:
        self.local_server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self))
        threading.Thread(target=self.local_server.serve_forever, daemon=True).start()
        self.jobs.recover()
        return self.local_server

    def shutdown(self) -> None:
        self.set_share(False)
        self.llama.stop()


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PaperReader"

        def log_message(self, fmt, *args):  # 静かにする
            pass

        # ---------- 共通 ----------
        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _err(self, code: int, msg: str):
            self._json({"error": msg}, code)

        def _authed(self, query: dict) -> bool:
            tok = self.headers.get("X-Token") or (query.get("t") or [""])[0]
            return secrets.compare_digest(tok, app.token)

        def _body(self, limit: int = 300 * 1024 * 1024) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0:
                raise ValueError("ファイルサイズが正しくありません。")
            if n > limit:
                raise ValueError("ファイルが大きすぎます。")
            return self.rfile.read(n)

        def _file(self, path: Path, ctype: str | None = None):
            if not path.exists() or not path.is_file():
                return self._err(404, "見つかりません")
            ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send(200, path.read_bytes(), ctype)

        # ---------- ルーティング ----------
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            path = u.path
            if not path.startswith("/api/"):
                rel = "index.html" if path in ("/", "") else path.lstrip("/")
                target = (STATIC_DIR / rel).resolve()
                if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                    return self._err(404, "見つかりません")
                ctype = None
                if target.suffix == ".js":
                    ctype = "text/javascript; charset=utf-8"
                elif target.suffix in (".html", ".css"):
                    ctype = f"text/{target.suffix[1:]}; charset=utf-8"
                return self._file(target, ctype)
            if not self._authed(q):
                return self._err(401, "アクセス用のリンクが正しくありません。")
            parts = path.strip("/").split("/")[1:]
            try:
                if parts == ["state"]:
                    s = load_settings()
                    return self._json({
                        "engines": engine_list(s),
                        "settings": {"engine": s.get("engine"), "gemini_model": s.get("gemini_model"),
                                     "translate_references": bool(s.get("translate_references"))},
                        "share": app.share_info(),
                        "is_local": self.client_address[0] == "127.0.0.1",
                    })
                if parts == ["library"]:
                    return self._json(app.library.list())
                if parts == ["share", "qr.svg"]:
                    info = app.share_info()
                    if not info.get("enabled"):
                        return self._err(404, "共有していません")
                    import io

                    import segno

                    buf = io.BytesIO()
                    segno.make(info["url"], error="m").save(buf, kind="svg", scale=6, border=2)
                    return self._send(200, buf.getvalue(), "image/svg+xml")
                if parts == ["gemini", "models"]:
                    key = get_env("GEMINI_API_KEY")
                    if not key:
                        return self._json([])
                    req = urllib.request.Request(
                        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                        headers={"x-goog-api-key": key})
                    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
                        data = json.loads(r.read().decode("utf-8"))
                    names = [m["name"].split("/", 1)[-1] for m in data.get("models", [])
                             if "generateContent" in m.get("supportedGenerationMethods", [])
                             and "gemini" in m["name"] and not any(x in m["name"] for x in ("image", "tts", "audio", "embedding", "live"))]
                    return self._json(sorted(set(names), reverse=True))
                if len(parts) >= 2 and parts[0] == "doc":
                    doc_id = parts[1]
                    d = app.library.doc_dir(doc_id)
                    if len(parts) == 2:
                        return self._json(app.library.meta(doc_id))
                    if parts[2] == "original":
                        return self._file(d / "original.pdf", "application/pdf")
                    if len(parts) >= 4 and parts[2] in ("translated", "dual", "reading", "fig"):
                        kind, engine = parts[2], parts[3]
                        if engine not in ENGINES:
                            return self._err(404, "見つかりません")
                        out = d / "out" / engine
                        if kind in ("translated", "dual", "reading"):
                            ensure_reading(d, out)
                        if kind == "translated":
                            return self._file(out / "translated.pdf", "application/pdf")
                        if kind == "dual":
                            return self._file(out / "dual.pdf", "application/pdf")
                        if kind == "reading":
                            return self._file(out / "reading.json", "application/json; charset=utf-8")
                        if kind == "fig" and len(parts) == 5 and re.fullmatch(r"p\d+_\d+\.png", parts[4]):
                            return self._file(out / "figs" / parts[4], "image/png")
                return self._err(404, "見つかりません")
            except KeyError:
                return self._err(404, "見つかりません")
            except Exception as e:  # noqa: BLE001
                return self._err(500, str(e))

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._authed(q):
                return self._err(401, "アクセス用のリンクが正しくありません。")
            parts = u.path.strip("/").split("/")[1:]
            try:
                if parts == ["translate"]:
                    engine = (q.get("engine") or ["plamo-2b"])[0]
                    name = (q.get("name") or ["paper.pdf"])[0]
                    if engine not in ENGINES:
                        return self._err(400, "エンジンが不明です")
                    data = self._body()
                    if not data.startswith(b"%PDF"):
                        return self._err(400, "PDFファイルではありません。")
                    refs = (q.get("refs") or [""])[0]
                    doc_id = app.library.add(name, data)
                    app.jobs.submit(doc_id, engine, refs == "1" if refs else None)
                    return self._json({"id": doc_id})
                if len(parts) == 3 and parts[0] == "doc" and parts[2] == "translate":
                    engine = (q.get("engine") or [""])[0]
                    if engine not in ENGINES:
                        return self._err(400, "エンジンが不明です")
                    app.library.meta(parts[1])
                    refs = (q.get("refs") or [""])[0]
                    app.jobs.submit(parts[1], engine, refs == "1" if refs else None)
                    return self._json({"ok": True})
                if len(parts) == 3 and parts[0] == "doc" and parts[2] == "delete":
                    for eng in ENGINES:
                        app.jobs.cancel(parts[1], eng) if (app.library.doc_dir(parts[1]) / "meta.json").exists() else None
                    app.library.delete(parts[1])
                    return self._json({"ok": True})
                if len(parts) == 3 and parts[0] == "doc" and parts[2] == "cancel":
                    engine = (q.get("engine") or [""])[0]
                    if engine not in ENGINES:
                        return self._err(400, "エンジンが不明です")
                    app.jobs.cancel(parts[1], engine)
                    return self._json({"ok": True})
                if parts == ["settings"]:
                    body = json.loads(self._body(1024 * 64) or b"{}")
                    allowed = {k: v.strip()[:80] for k, v in body.items() if k in ("engine", "gemini_model")
                               and isinstance(v, str)}
                    if "gemini_model" in allowed and not re.fullmatch(r"[\w.\-]+", allowed["gemini_model"]):
                        return self._err(400, "モデル名に使えない文字が含まれています。")
                    if isinstance(body.get("translate_references"), bool):
                        allowed["translate_references"] = body["translate_references"]
                    save_settings(allowed)
                    return self._json({"ok": True})
                if parts == ["share"]:
                    if self.client_address[0] != "127.0.0.1":
                        return self._err(403, "共有の設定はPCの画面から行ってください。")
                    body = json.loads(self._body(1024) or b"{}")
                    return self._json(app.set_share(bool(body.get("enable"))))
                return self._err(404, "見つかりません")
            except KeyError:
                return self._err(404, "見つかりません")
            except ValueError as e:
                return self._err(400, str(e))
            except OSError as e:
                return self._err(500, f"共有を開始できませんでした: {e}")
            except Exception as e:  # noqa: BLE001
                return self._err(500, str(e))

    return Handler
