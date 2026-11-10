"""Rebuild PDF bookmarks from source sections and translated heading positions."""
from pathlib import Path

import pymupdf

from .reading import _key


def write_outline(pdf: Path, mono_pdf: Path, data: dict) -> None:
    headings = [i for i in data["items"] if i["t"] in ("h2", "h3")]
    if not headings:
        return
    by_source = {(i["page"], _key(i["source_heading"])): i for i in headings}
    source_toc = data.get("source_toc") or [
        [i["level"], i["source_heading"], i["page"]] for i in headings]
    tmp = pdf.with_name(pdf.stem + ".outline.tmp.pdf")
    try:
        with pymupdf.open(pdf) as doc, pymupdf.open(mono_pdf) as mono:
            # Only handle the default one-page or side-by-side layout.
            if len(doc) != len(mono):
                return
            toc = []
            previous_level = 0
            for level, label, page in source_toc:
                if not 1 <= page <= len(doc):
                    continue
                heading = by_source.get((page, _key(label)))
                x, y = (heading["x"], heading["y"]) if heading else (36, 36)
                if doc[page - 1].rect.width > mono[page - 1].rect.width * 1.8:
                    x += mono[page - 1].rect.width
                label = heading["text"] if heading else label
                level = min(max(1, level), previous_level + 1)
                previous_level = level
                toc.append([level, label, page, {"kind": pymupdf.LINK_GOTO, "page": page - 1,
                                               "to": pymupdf.Point(x, max(0, y - 8)), "zoom": 0}])
            doc.set_toc(toc, collapse=0)
            doc.set_pagemode("UseOutlines")
            doc.save(tmp, garbage=3, deflate=True)
        tmp.replace(pdf)
    finally:
        tmp.unlink(missing_ok=True)
