"""翻訳ジョブ本体（別プロセスで実行）。進捗は '@@{json}' 行で標準出力へ出す。"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys

from . import bdenv  # noqa: F401
from .config import GLOSSARY_FILE, LLAMA_URL
from .engines import GEMINI_BASE_URL, LOCAL_MODELS


def emit(**kw) -> None:
    print("@@" + json.dumps(kw, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--engine", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--pages")
    a = p.parse_args(argv)

    import babeldoc.main as bmain

    from .translators import GeminiTranslator, PlamoTranslator

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

    if a.engine in LOCAL_MODELS:
        bmain.OpenAITranslator = PlamoTranslator
        args = ["--openai", "--openai-model", LOCAL_MODELS[a.engine]["alias"],
                "--openai-base-url", f"{LLAMA_URL}/v1", "--openai-api-key", "local",
                "--no-auto-extract-glossary", "--qps", "4", "--pool-max-workers", "4"]
    elif a.engine == "gemini":
        key = os.environ.get("PAPERAPP_GEMINI_KEY", "")
        model = os.environ.get("PAPERAPP_GEMINI_MODEL", "gemini-2.5-flash")
        if not key:
            emit(event="error", error="GeminiのAPIキーが登録されていません。")
            sys.exit(2)
        bmain.OpenAITranslator = GeminiTranslator
        base_url = os.environ.get("PAPERAPP_GEMINI_BASE_URL", GEMINI_BASE_URL)  # 試験用に差し替え可能
        args = ["--openai", "--openai-model", model, "--openai-base-url", base_url,
                "--openai-api-key", key, "--qps", "4", "--pool-max-workers", "4"]
        if GLOSSARY_FILE.exists():
            args += ["--glossary-files", str(GLOSSARY_FILE)]
    else:
        emit(event="error", error=f"不明なエンジン: {a.engine}")
        sys.exit(2)

    common = ["--lang-in", "en", "--lang-out", "ja", "--output", a.outdir, "--no-watermark"]
    if a.pages:
        common += ["--pages", a.pages]
    sys.argv = ["babeldoc", *args, *common, "--files", a.input]
    bmain.cli()

    from .translators import STATS

    from pathlib import Path

    if STATS["ok"] == 0 and STATS["fail"] > 0:
        for f in Path(a.outdir).glob("*.pdf"):
            f.unlink(missing_ok=True)
        msg = STATS["last_error"]
        if any(x in msg for x in ("API key", "400", "401", "403", "PERMISSION", "Authentication")):
            msg = "APIキーまたはモデル名が正しくない可能性があります。設定を確認してください。（" + msg[:160] + "）"
        elif "Connection" in msg:
            msg = "翻訳サーバーに接続できませんでした。（" + msg[:160] + "）"
        emit(event="error", error="翻訳できませんでした: " + msg)
        sys.exit(1)
    if STATS["fail"]:
        emit(event="warning", warning=f"{STATS['fail']}か所の翻訳に失敗し、原文のまま残っています。")


if __name__ == "__main__":
    main()
