"""BabelDOC を PC 上の PLaMo 3 Translate（llama.cpp サーバー）で動かす実行スクリプト。

使い方:
  .venv\Scripts\python.exe run_plamo.py 論文.pdf [BabelDOC の追加オプション]

llama-server が http://127.0.0.1:8090 で起動している必要があります（start_server.ps1）。
"""

from __future__ import annotations

import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent

# BabelDOC はキャッシュ・フォント・解析モデルを「ホーム\.cache\babeldoc」に置く。
# このフォルダの中に収めるため、BabelDOC を読み込む前にホームの場所だけ差し替える。
pathlib.Path.home = classmethod(lambda cls: ROOT / "home")  # type: ignore[assignment]

import babeldoc.main as bmain  # noqa: E402
from babeldoc.translator.translator import OpenAITranslator  # noqa: E402

GLOSSARY_FILE = ROOT / "glossary.csv"


def load_glossary() -> list[tuple[str, str]]:
    if not GLOSSARY_FILE.exists():
        return []
    terms = []
    with GLOSSARY_FILE.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            src = (row.get("source") or "").strip()
            tgt = (row.get("target") or "").strip()
            if src and tgt and not src.startswith("#"):
                terms.append((src, tgt))
    return sorted(terms, key=lambda t: -len(t[0]))


class PlamoTranslator(OpenAITranslator):
    """PLaMo 3 Translate 用。段落ごとに PFML3 形式（chat template 経由）で送る。"""

    name = "plamo"

    def __init__(self, *args, **kwargs):
        self.glossary = load_glossary()
        self.form = "plain"  # 論文向けに常体（だ・である調）
        super().__init__(*args, **kwargs)
        self.add_cache_impact_parameters("glossary", repr(self.glossary))

    def prompt(self, text):
        lower = text.lower()
        lines = ["[plamo-translate]", f"target_lang={self.lang_out}", f"form={self.form}"]
        for src, tgt in self.glossary:
            if src.lower() in lower:
                lines.append(f"glossary={src} => {tgt}")
        lines.append("---")
        return [
            {"role": "system", "content": "\n".join(lines)},
            {"role": "user", "content": text if text.strip() else " "},
        ]

    def do_llm_translate(self, text, rate_limit_params=None):
        # 一括 JSON 翻訳や自動用語抽出は翻訳専用モデルに向かないため、
        # 段落単位の通常翻訳だけを使わせる。
        raise NotImplementedError


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(__doc__)
        return
    bmain.OpenAITranslator = PlamoTranslator
    defaults = [
        "--openai",
        "--openai-model", "plamo-3-translate-2b",
        "--openai-base-url", "http://127.0.0.1:8090/v1",
        "--openai-api-key", "local",
        "--lang-in", "en",
        "--lang-out", "ja",
        "--no-auto-extract-glossary",
        "--qps", "4",
        "--pool-max-workers", "4",
        "--output", str(ROOT / "output"),
    ]
    files = [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]
    extra = [a for a in sys.argv[1:] if not a.lower().endswith(".pdf")]
    file_args = [x for f in files for x in ("--files", f)]
    sys.argv = [sys.argv[0], *defaults, *extra, *file_args]
    bmain.cli()


if __name__ == "__main__":
    main()
