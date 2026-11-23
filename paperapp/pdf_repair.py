"""Repair translated/dual PDFs for scanned pages: blank rotated pages, damaged figures, centered headings."""

from __future__ import annotations

from pathlib import Path

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


def _restore_scan_figures(orig_page: pymupdf.Page, mono_page: pymupdf.Page, fig_rects: list[pymupdf.Rect]) -> bool:
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
        if clip.is_empty or clip.width < 20 or clip.height < 20:
            continue
        # Only patch if BabelDOC actually painted whiteout rectangles inside this figure area.
        if not any(not (w & clip).is_empty for w in white_rects):
            continue
        pix = orig_page.get_pixmap(clip=clip, dpi=300)
        mono_page.insert_image(clip, pixmap=pix, overlay=True)
        changed = True
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
