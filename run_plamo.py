"""コマンドで PDF を翻訳する（PC 上の PLaMo）。

使い方:
  .venv\Scripts\python.exe run_plamo.py 論文.pdf [--engine plamo-0.8b|plamo-2b|plamo-8b] [--pages 1-3] [--translate-references]

llama-server が起動していない場合は、指定したモデルで自動起動します。
結果は output フォルダに出ます。
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from paperapp.config import ROOT
from paperapp.engines import LlamaManager
from paperapp.registry import ENGINES, PlamoEngine

LOCAL_MODELS = [k for k, v in ENGINES.items() if isinstance(v, PlamoEngine)]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pdf", nargs="+")
    p.add_argument("--engine", default="plamo-2b", choices=list(LOCAL_MODELS))
    p.add_argument("--pages")
    p.add_argument("--translate-references", action="store_true", help="参考文献も翻訳する")
    a = p.parse_args()
    LlamaManager().ensure(a.engine)
    for pdf in a.pdf:
        cmd = [sys.executable, "-m", "paperapp.worker", "--engine", a.engine,
               "--input", pdf, "--outdir", str(ROOT / "output")]
        if a.pages:
            cmd += ["--pages", a.pages]
        if a.translate_references:
            cmd.append("--translate-references")
        subprocess.run(cmd, cwd=str(ROOT), check=False)


if __name__ == "__main__":
    main()
