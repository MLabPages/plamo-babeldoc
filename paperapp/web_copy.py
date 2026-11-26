"""Self-contained browser copies for a user's private sync folder."""

import base64
import json
import re
import tempfile
from html import escape
from pathlib import Path

from .config import replace_file


KINDS = {"original": "原文PDF", "translated": "日本語訳PDF", "dual": "対訳PDF"}
COPY_NAME = re.compile(r"MLab-[0-9a-f]{6,32}-[a-z0-9.-]+--.+\.html")


def copies(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("MLab-*.html")
                  if COPY_NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink())


def document(title: str, data: dict, figures: Path, pdfs: dict[str, Path]) -> list[bytes | Path]:
    """Compose HTML with inline images and optional PDF downloads, with no network resources."""
    parts = []

    def add(value: str) -> None:
        parts.append(value.encode("utf-8"))

    title = escape(title)
    add("""<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<style>
:root{color-scheme:light dark}body{max-width:42rem;margin:auto;padding:1rem;font:1.15rem/1.85 serif;overflow-wrap:anywhere}
img{max-width:100%;height:auto}figure{margin:1rem 0}summary,nav,label{font:1rem/1.5 system-ui}details{margin-block:.3rem 1.4rem}
blockquote{margin:.4rem 0;padding-left:1rem;border-left:3px solid #8d8174}.ref{padding-left:2em;text-indent:-2em}
.center{text-align:center}small{opacity:.75}nav{display:flex;flex-wrap:wrap;gap:1rem}p{margin:.5em 0}
</style>""")
    add(f"<title>{title}</title><main><h1>{title}</h1>")
    if pdfs:
        add("<nav aria-label='PDF'>")
        for kind, path in pdfs.items():
            add(f'<a download="{KINDS[kind]}.pdf" href="data:application/pdf;base64,')
            parts.append(path)
            add(f'">{KINDS[kind]}</a>')
        add("</nav>")
    shown_title = False
    for item in data["items"]:
        kind = item["t"]
        text = item.get("text") or ""
        if kind == "page":
            add(f"<hr><small>{escape(str(item['page']))} ページ</small>")
            continue
        if kind in ("fig", "eq") and re.fullmatch(r"p\d+_\d+\.png", item.get("src") or ""):
            image = figures / item["src"]
            if image.is_file():
                add('<figure><img loading="lazy" alt="' + ("数式" if kind == "eq" else "図表")
                    + '" src="data:image/png;base64,')
                parts.append(image)
                add('"></figure>')
                continue
        if not text:
            continue
        if kind in ("h2", "h3") and text == data.get("title") and not shown_title:
            shown_title = True
            continue
        tag = kind if kind in ("h2", "h3") else "p"
        cls = "ref" if kind == "ref" else "center" if item.get("align") == "center" else ""
        content = escape(text)
        if item.get("italic"):
            content = f"<em>{content}</em>"
        runs = item.get("runs", [])
        if runs and "".join(run[0] for run in runs) == text:
            markup = {"b": ("<strong>", "</strong>"), "i": ("<em>", "</em>"),
                      "bi": ("<strong><em>", "</em></strong>")}
            content = "".join(markup.get(style, ("", ""))[0] + escape(value)
                              + markup.get(style, ("", ""))[1] for value, style in runs)
        add(f'<{tag} class="{cls}">{content}</{tag}>')
        if item.get("orig"):
            add(f"<details><summary>原文</summary><blockquote>{escape(item['orig'])}</blockquote></details>")
    add("</main></html>")
    return parts


def plan(meta: dict, source: Path, engine: str, kinds: list[str]) -> list[bytes | Path]:
    out = source / "out" / engine
    data = json.loads((out / "reading.json").read_text(encoding="utf-8"))
    pdfs = {}
    for kind in KINDS:
        if kind in kinds:
            path = (source if kind == "original" else out) / (kind + ".pdf")
            if not path.is_file():
                raise ValueError(f"{KINDS[kind]}が見つかりません。")
            pdfs[kind] = path
    return document(meta.get("title_ja") or data.get("title") or meta["filename"], data, out / "figs", pdfs)


def size(parts: list[bytes | Path]) -> int:
    return sum(len(part) if isinstance(part, bytes) else 4 * ((part.stat().st_size + 2) // 3) for part in parts)


def save(destination: Path, parts: list[bytes | Path]) -> None:
    destination.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with temporary.open("wb") as stream:
            for part in parts:
                if isinstance(part, bytes):
                    stream.write(part)
                else:
                    with part.open("rb") as source:
                        while chunk := source.read(3 * 64 * 1024):
                            stream.write(base64.b64encode(chunk))
        replace_file(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
