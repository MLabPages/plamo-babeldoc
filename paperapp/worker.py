"""翻訳ジョブ本体（別プロセスで実行）。進捗は '@@{json}' 行で標準出力へ出す。"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from . import bdenv  # noqa: F401
from .config import load_settings
from .registry import ENGINES


def emit(**kw) -> None:
    # BabelDOC のログが改行せずに終わることがあるので、先頭で改行して行頭から出す
    print("\n@@" + json.dumps(kw, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--engine", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--pages")
    p.add_argument("--translate-references", action="store_true")
    p.add_argument("--gemini-model")
    a = p.parse_args(argv)

    engine = ENGINES.get(a.engine)
    if engine is None:
        emit(event="error", error=f"不明なエンジン: {a.engine}")
        sys.exit(2)
    settings = load_settings()
    if a.gemini_model:
        settings["gemini_model"] = a.gemini_model
    ok, why = engine.available(settings)
    if not ok:
        emit(event="error", error=why)
        sys.exit(2)

    import babeldoc.main as bmain

    def make_handler(config, show_log=False):
        last = {"v": -1.0}

        def handler(ev):
            t = ev.get("type")
            if t in ("progress_update", "progress_end"):
                v = round(float(ev.get("overall_progress", 0) or 0), 1)
                if v != last["v"]:
                    last["v"] = v
                    emit(event="progress", progress=v, stage=ev.get("stage", ""))
            elif t == "error":
                emit(event="error", error=str(ev.get("error")))
            elif t == "finish":
                emit(event="finish")

        return contextlib.nullcontext(), handler

    bmain.create_progress_handler = make_handler
    args = engine.configure(bmain, settings, a.translate_references)
    common = ["--lang-in", "en", "--lang-out", "ja", "--output", a.outdir, "--no-watermark"]
    if a.pages:
        common += ["--pages", a.pages]
    if os.environ.get("PAPERAPP_IGNORE_CACHE") == "1":  # 試験用
        common.append("--ignore-cache")
    sys.argv = ["babeldoc", *args, *common, "--files", a.input]
    bmain.cli()

    from .translators import STATS

    if STATS["ok"] == 0 and STATS["fail"] > 0:
        for f in Path(a.outdir).glob("*.pdf"):
            f.unlink(missing_ok=True)
        msg = STATS["last_error"]
        if any(x in msg for x in ("API key", "400", "401", "403", "456", "PERMISSION", "Authentication", "Unauthorized")):
            msg = "APIキー・モデル名・利用枠のいずれかに問題がある可能性があります。（" + msg[:180] + "）"
        elif "Connection" in msg:
            msg = "翻訳サービスに接続できませんでした。（" + msg[:180] + "）"
        emit(event="error", error="翻訳できませんでした: " + msg)
        sys.exit(1)
    emit(event="stats", skipped_refs=STATS["skipped_refs"], ok=STATS["ok"], fail=STATS["fail"])
    if STATS["fail"]:
        emit(event="warning", warning=f"{STATS['fail']}か所の翻訳に失敗し、原文のまま残っています。")


if __name__ == "__main__":
    main()
