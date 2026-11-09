"""BabelDOC を読み込む前に import する。キャッシュ類をこのフォルダ内に置く。"""

import pathlib

from .config import ROOT

_HOME = ROOT / "home"
pathlib.Path.home = classmethod(lambda cls: _HOME)  # type: ignore[assignment]
