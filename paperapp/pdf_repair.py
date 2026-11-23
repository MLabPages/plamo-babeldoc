"""Repair translated/dual PDFs for scanned pages: blank rotated pages, damaged figures, centered headings."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import pymupdf

from .config import replace_file

_BOLD_FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\yumindb.ttf"),
    Path(r"C:\Windows\Fonts\YuGothB.ttc"),
    Path(r"C:\Windows\Fonts\meiryob.ttc"),
    Path(r"C:\Windows\Fonts\BIZ-UDGothicB.ttc"),
)


def _bold_font_path() -> str | None:
    for p in _BOLD_FONT_CANDIDATES:
        if p.exists():
            return str(p)
    return None


def _needs_blank_page_restore(orig_page: pymupdf.Page, mono_page: pymupdf.Page) -> bool:
    """BabelDOC can drop rotated scanned pages (0 text chars, images pushed off-page)."""
    if len(mono_page.get_text("text").strip()) > 0:
        return False
    orig_has_content = bool(orig_page.get_text("text").strip() or orig_page.get_images())
    if not orig_has_content:
        return False
    if orig_page.rotation != 0:
        return True
    pr = mono_page.rect
    blocks = mono_page.get_text("dict")["blocks"]
    visible_imgs = sum(
        1 for b in blocks if b["type"] == 1 and not (pymupdf.Rect(b["bbox"]).normalize() & pr).is_empty
    )
    return visible_imgs == 0


def _restore_scan_figures(orig_page: pymupdf.Page, mono_page: pymupdf.Page,
                          fig_rects: list[pymupdf.Rect], *, min_size: float = 20) -> bool:
    """Overlay crisp original scan image over figure areas damaged by OCR whiteout rectangles."""
    if not fig_rects:
        return False
    drawings = mono_page.get_drawings()
    white_rects = [
        d["rect"] for d in drawings
        if d.get("fill") is not None and all(c > 0.95 for c in d["fill"])
    ]
    changed = False
    for r in fig_rects:
        clip = r & orig_page.rect
        if clip.is_empty or min(clip.width, clip.height) < min_size:
            continue
        # Only patch if BabelDOC actually painted whiteout rectangles inside this figure area.
        if not any(not (w & clip).is_empty for w in white_rects):
            continue
        pix = orig_page.get_pixmap(clip=clip, dpi=300)
        mono_page.insert_image(clip, pixmap=pix, overlay=True)
        changed = True
    return changed


def _table_number_cells(page: pymupdf.Page, tables: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Use original pixels for bare numeric cells in scanned tables."""
    words = page.get_text("words")
    cells = []
    for table in tables:
        matches = [pymupdf.Rect(word[:4]) for word in words
                   if table.contains(pymupdf.Rect(word[:4]))
                   and re.fullmatch(r"[+\-−]?\d+(?:[.,]\d+)?%?", word[4])]
        if len(matches) >= 4:
            cells.extend(r + (-1.5, -1, 1.5, 1) for r in matches)
    return cells


_SERIES = re.compile(r"\b([a-z]+)\s+(\d+)\s*=\s*(\d+(?:\s*,\s*\d+){2,})", re.I)
_BROKEN_LIST = re.compile(r"(?:[,，]\s*){3,}")


def _restore_numeric_series(source: pymupdf.Page, page: pymupdf.Page) -> bool:
    """Reflow a damaged inline series using the source values and keep the Japanese suffix."""
    changed = False
    font_path = _bold_font_path()
    if font_path is None:
        return False
    blocks = [b for b in page.get_text("blocks") if b[6] == 0]
    for original in source.get_text("blocks"):
        if original[6] != 0:
            continue
        values = _SERIES.findall(original[4])
        if len(values) < 3:
            continue
        label = values[0][0].lower()
        if any(word.lower() != label or int(index) != n for n, (word, index, _) in enumerate(values, 1)):
            continue
        zone = pymupdf.Rect(original[:4]) + (-2, -2, 2, 2)
        for block in blocks:
            area = pymupdf.Rect(block[:4])
            if not zone.contains(area) or not _BROKEN_LIST.search(block[4]):
                continue
            nearby = [b for b in blocks if b[1] <= block[1] and b[3] >= block[1] - 3
                      and zone.contains(pymupdf.Rect(b[:4])) and re.search(r"\b1\s*=\s*\d", b[4])]
            if len(nearby) != 1:
                continue
            area |= pymupdf.Rect(nearby[0][:4])
            suffix = re.search(r"。\s*(\S.*)$", block[4].strip(), flags=re.S)
            if not suffix:
                continue
            entries = [index + " = " + ", ".join(re.findall(r"\d+", nums)) for _, index, nums in values]
            lines = [";  ".join(entries[i:i + 3]) for i in range(0, len(entries), 3)]
            suffix_text = unicodedata.normalize("NFKC", " ".join(suffix[1].split()))
            if any(pymupdf.get_text_length(line, fontname="cour", fontsize=8.5) > area.width for line in lines):
                continue
            shape = page.new_shape()
            for n, line in enumerate(lines):
                shape.insert_text((area.x0, area.y0 + 8 + n * 10), line, fontname="cour", fontsize=8.5)
            suffix_area = pymupdf.Rect(area.x0, area.y0 + len(lines) * 10, area.x1, area.y1)
            if suffix_area.is_empty or shape.insert_textbox(
                suffix_area, suffix_text, fontname="jpseries", fontfile=font_path, fontsize=8.5, lineheight=1.15,
            ) < 0:
                continue
            page.add_redact_annot(area, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions(images=0, graphics=0)
            # Applying redactions can discard the fonts registered by the uncommitted shape.
            page.insert_font(fontname="cour")
            page.insert_font(fontname="jpseries", fontfile=font_path)
            shape.commit()
            changed = True
            break
    return changed


def _style_centered_headings(
    mono_page: pymupdf.Page,
    headings: list[dict],
    body_size: float,
    font_path: str | None,
) -> bool:
    """Redraw centered scanned-page headings in bold, centered at a readable heading size."""
    if not headings:
        return False
    pw = mono_page.rect.width
    changed = False
    fontname = "jpbold" if font_path else "japan"
    for h in headings:
        rect = h.get("_orig_mono_rect")
        if rect is None:
            continue
        r = pymupdf.Rect(rect)
        if r.is_empty:
            continue
        # すでに中央寄せかつ太字で描き直し済みなら重複処理しない
        cx = (r.x0 + r.x1) / 2.0
        centered = h.get("align") == "center"
        italic = h.get("italic", False)
        if centered and abs(cx - pw / 2.0) < 0.04 * pw and h.get("_mono_bold"):
            continue
        text = h["text"].strip()
        if not text:
            continue
        target_size = round(body_size * (1.22 if h["t"] == "h2" else 1.06), 1)
        target_size = max(9.5, min(target_size, 16.0))
        # Measure text width to center horizontally on the page.
        if font_path and not italic:
            font_obj = pymupdf.Font(fontfile=font_path)
            tw = font_obj.text_length(text, fontsize=target_size)
        else:
            tw = pymupdf.Font("cjk").text_length(text, fontsize=target_size)
        # Shrink slightly if wider than 82% of page width.
        if tw > pw * 0.82 and tw > 0:
            target_size = max(8.5, target_size * (pw * 0.82 / tw))
            tw = pw * 0.82
        x = max(24.0, (pw - tw) / 2.0) if centered else r.x0
        y = r.y0 + (r.height + target_size * 0.72) / 2.0
        target = pymupdf.Rect(x, y - target_size, x + tw, y + target_size * .25)
        if any((target & pymupdf.Rect(b[:4])).get_area() > 2
               for b in mono_page.get_text("blocks") if b[6] == 0
               and not (pymupdf.Rect(b[:4]) & r).get_area() > .8 * r.get_area()):
            continue
        mono_page.add_redact_annot(r, fill=False, cross_out=False)
        mono_page.apply_redactions(images=0, graphics=0)
        mono_page.insert_text(
            pymupdf.Point(x, y),
            text,
            fontsize=target_size,
            fontname="japan" if italic else fontname,
            fontfile=None if italic else font_path,
            morph=(pymupdf.Point(x, y), pymupdf.Matrix(1, 0, .18, 1, 0, 0)) if italic else None,
            color=(0.05, 0.05, 0.05),
            overlay=True,
        )
        changed = True
    return changed


def repair_pdfs(
    mono_pdf: Path,
    original_pdf: Path,
    dual_pdf: Path | None,
    scan_pages: dict[int, list[pymupdf.Rect]],
    centered_headings: dict[int, list[dict]],
    body_size: float,
    *,
    scanned_tables: dict[int, list[pymupdf.Rect]],
) -> bool:
    """Fix blank rotated pages, damaged scan figures, and centered scan headings in mono and dual PDFs."""
    if not mono_pdf.exists() or not original_pdf.exists():
        return False
    font_path = _bold_font_path()
    tmp_mono = mono_pdf.with_name(mono_pdf.stem + ".repair.tmp.pdf")
    tmp_dual = dual_pdf.with_name(dual_pdf.stem + ".repair.tmp.pdf") if dual_pdf and dual_pdf.exists() else None
    modified_pages: set[int] = set()
    try:
        with pymupdf.open(original_pdf) as orig_doc, pymupdf.open(mono_pdf) as mono_doc:
            if len(orig_doc) != len(mono_doc):
                return False
            for pno in range(len(mono_doc)):
                orig_p = orig_doc[pno]
                mono_p = mono_doc[pno]
                if _needs_blank_page_restore(orig_p, mono_p):
                    mono_doc.delete_page(pno)
                    mono_doc.insert_pdf(orig_doc, from_page=pno, to_page=pno, start_at=pno)
                    modified_pages.add(pno)
                    continue
                page_changed = False
                if pno in scan_pages:
                    if _restore_scan_figures(orig_p, mono_p, scan_pages[pno]):
                        page_changed = True
                if pno in scanned_tables and not orig_p.rotation and not mono_p.rotation:
                    if _restore_scan_figures(orig_p, mono_p, _table_number_cells(orig_p, scanned_tables[pno]), min_size=2):
                        page_changed = True
                    if _restore_numeric_series(orig_p, mono_p):
                        page_changed = True
                if pno in centered_headings:
                    if _style_centered_headings(mono_p, centered_headings[pno], body_size, font_path):
                        page_changed = True
                if page_changed:
                    modified_pages.add(pno)
            if not modified_pages:
                return False
            mono_doc.subset_fonts()
            mono_doc.save(tmp_mono, garbage=3, deflate=True)

            if tmp_dual is not None and dual_pdf is not None:
                with pymupdf.open(dual_pdf) as dual_doc:
                    if len(dual_doc) == len(mono_doc):
                        for pno in sorted(modified_pages):
                            dp = dual_doc[pno]
                            mp = mono_doc[pno]
                            if dp.rect.width > mp.rect.width * 1.8:
                                half = dp.rect.width / 2
                                stream = dual_doc.get_new_xref()
                                dual_doc.update_object(stream, "<<>>")
                                dual_doc.update_stream(stream, b"")
                                dp.set_contents(stream)
                                for source, x in ((orig_doc, 0), (mono_doc, half)):
                                    page = source[pno]
                                    rotation = page.rotation
                                    page.set_rotation(0)
                                    try:
                                        dp.show_pdf_page(pymupdf.Rect(x, 0, x + half, dp.rect.height), source, pno)
                                    finally:
                                        page.set_rotation(rotation)
                        dual_doc.save(tmp_dual, garbage=3, deflate=True)
        if tmp_dual is not None and tmp_dual.exists() and dual_pdf is not None:
            replace_file(tmp_dual, dual_pdf)
        replace_file(tmp_mono, mono_pdf)
        return True
    finally:
        tmp_mono.unlink(missing_ok=True)
        if tmp_dual is not None:
            tmp_dual.unlink(missing_ok=True)
