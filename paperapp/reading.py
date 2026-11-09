"""翻訳済み PDF から読書モード用の本文（段落・見出し・図・数式）を取り出す。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

TERMINAL = tuple("。．.!?！？」』）)：:")
CAPTION_RE = re.compile(r"^(図|表)\s*[\d０-９]+\s*[.．:：\s　]|^(Figure|Fig\.|Table)\s*\d+\s*[.:]", re.IGNORECASE)
MATH_RE = re.compile(r"[\U0001D400-\U0001D7FF∑∫√≈≤≥±×÷∂∆∇]")
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
CONTINUATION = set("をのにがはでともるれりたっゃゅょァィゥェォッャュョーぁぃぅぇぉ、")


def _join(parts: list[str]) -> str:
    out = ""
    for s in parts:
        s = s.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ").strip()
        if not s:
            continue
        if not out:
            out = s
        elif out.endswith("-") and s[:1].islower():
            out = out[:-1] + s
        elif out[-1:].isascii() and out[-1:].isalnum() and s[:1].isascii() and s[:1].isalnum():
            out += " " + s
        elif out[-1:] in ",.;:)" and s[:1].isascii():
            out += " " + s
        else:
            out += s
    return out


def _is_dark(color: int) -> bool:
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return max(r, g, b) - min(r, g, b) < 40  # 黒・灰色（無彩色）


def _block_info(block: dict) -> dict | None:
    lines, size, bold_chars, color_chars, chars = [], 0.0, 0, 0, 0
    for line in block.get("lines", []):
        dx, dy = line.get("dir", (1, 0))
        if abs(dx - 1) > 0.05 or abs(dy) > 0.05:
            continue  # 縦書きの欄外表記などは読まない
        t = "".join(sp["text"] for sp in line["spans"])
        for sp in line["spans"]:
            n = len(sp["text"].strip())
            chars += n
            size = max(size, sp["size"])
            if sp["flags"] & 16 or "bold" in sp.get("font", "").lower():
                bold_chars += n
            if not _is_dark(sp.get("color", 0)):
                color_chars += n
        lines.append(t)
    if not lines or chars == 0:
        return None
    return {"rect": pymupdf.Rect(block["bbox"]), "lines": lines, "size": size,
            "bold": bold_chars / chars > 0.8, "colored": color_chars / chars > 0.8}


def _merge_adjacent(infos: list[dict]) -> list[dict]:
    """同じ段・同じ書式で行間程度しか離れていないブロックを 1 段落にまとめる。"""
    out: list[dict] = []
    for b in infos:
        p = out[-1] if out else None
        if p is not None:
            r, q = b["rect"], p["rect"]
            same_style = abs(b["size"] - p["size"]) < 0.8 and b["bold"] == p["bold"] and b["colored"] == p["colored"]
            same_col = abs(r.x0 - q.x0) < 8 or (r.x0 >= q.x0 - 8 and r.x1 <= q.x1 + 8)
            gap = r.y0 - q.y1
            # 短い 1 行の後に本文が続く場合は小見出しとみなしてつながない
            lone_heading = (len(p["lines"]) == 1 and len(_join(p["lines"])) <= 40
                            and not _join(p["lines"]).endswith(TERMINAL) and q.width < 0.6 * r.width)
            if lone_heading:
                p["heading"] = True
            if same_style and same_col and not lone_heading and -2 <= gap < p["size"] * 0.9:
                p["lines"] += b["lines"]
                p["rect"] = q | r
                continue
        out.append(dict(b))
    return out


def _merge_rects(rects: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    rects = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out: list[pymupdf.Rect] = []
        for r in rects:
            for o in out:
                if o.intersects(r):
                    o |= r
                    changed = True
                    break
            else:
                out.append(r)
        rects = out
    return rects


def _figure_rects(page: pymupdf.Page, blocks: list[dict]) -> list[tuple[pymupdf.Rect, dict | None]]:
    """図の領域を返す。写真 1 枚だけの領域には、その画像ブロックも添える。"""
    pr = page.rect
    area = pr.width * pr.height
    # 長い本文ブロック（これと大きく重なるものは背景画像・背景の枠とみなす）
    body = []
    for b in blocks:
        if b["type"] == 0:
            n = sum(len(sp["text"]) for ln in b["lines"] for sp in ln["spans"])
            if n > 80:
                body.append(pymupdf.Rect(b["bbox"]))
    cands = []
    rasters = []
    for b in blocks:
        if b["type"] == 1:
            r = pymupdf.Rect(b["bbox"]) & pr
            if 0.02 * area < r.width * r.height < 0.7 * area:
                cands.append(r)
                rasters.append((pymupdf.Rect(r), b))
    try:
        for r in page.cluster_drawings(x_tolerance=4, y_tolerance=4):
            r = pymupdf.Rect(r) & pr
            if (0.04 * area < r.width * r.height < 0.55 * area
                    and r.width > 0.15 * pr.width and r.height > 0.08 * pr.height):
                cands.append(r)
    except Exception:
        pass
    out = []
    for r in _merge_rects(cands):
        ra = r.width * r.height
        if ra >= 0.75 * area:
            continue
        covered = sum((r & t).width * (r & t).height for t in body if r.intersects(t))
        single = [b for rr, b in rasters if abs(rr.x0 - r.x0) < 1 and abs(rr.y0 - r.y0) < 1
                  and abs(rr.x1 - r.x1) < 1 and abs(rr.y1 - r.y1) < 1]
        raster = single[0] if len(single) == 1 else None
        if covered > 0.12 * ra and raster is None:
            continue
        out.append((r, raster))
    return out


def _save_raster(block: dict, path: Path) -> tuple[int, int] | None:
    try:
        import io

        from PIL import Image

        im = Image.open(io.BytesIO(block["image"]))
        if im.mode not in ("RGB", "RGBA", "L"):
            im = im.convert("RGB")
        if max(im.size) > 1600:
            im.thumbnail((1600, 1600))
        im.save(path, "PNG")
        return im.size
    except Exception:
        return None


def build_reading(mono_pdf: Path, original_pdf: Path, fig_dir: Path) -> dict:
    fig_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(mono_pdf))
    orig = pymupdf.open(str(original_pdf)) if original_pdf.exists() else None

    pages = []
    sizes: list[float] = []
    for page in doc:
        d = page.get_text("dict", sort=False)
        pages.append(d["blocks"])
        for b in d["blocks"]:
            if b["type"] == 0:
                for line in b["lines"]:
                    for sp in line["spans"]:
                        sizes += [sp["size"]] * len(sp["text"].strip())
    sizes.sort()
    median = sizes[len(sizes) // 2] if sizes else 10.0

    items: list[dict] = []
    title = ""
    title_size = 0.0
    fig_no = 0
    for pno, (page, blocks) in enumerate(zip(doc, pages)):
        H = page.rect.height
        items.append({"t": "page", "page": pno + 1})
        fig_list = _figure_rects(page, blocks)
        figs = [r for r, _ in fig_list]
        placed = [False] * len(figs)
        orig_blocks = []
        used_orig: set[int] = set()
        if orig is not None and pno < orig.page_count:
            orig_blocks = [b for b in orig[pno].get_text("blocks") if b[6] == 0]

        def place_figs_before(y_top: float, x0: float, x1: float, force: bool = False):
            nonlocal fig_no
            for i, r in enumerate(figs):
                if placed[i]:
                    continue
                if force or (r.y1 <= y_top + 4 and not (r.x1 < x0 or r.x0 > x1)):
                    placed[i] = True
                    fig_no += 1
                    name = f"p{pno + 1}_{fig_no}.png"
                    size = _save_raster(fig_list[i][1], fig_dir / name) if fig_list[i][1] else None
                    if size is None:
                        pix = page.get_pixmap(clip=r, dpi=150)
                        pix.save(str(fig_dir / name))
                        size = (pix.width, pix.height)
                    items.append({"t": "fig", "src": name, "page": pno + 1, "w": size[0], "h": size[1]})

        infos = []
        for b in blocks:
            if b["type"] != 0:
                continue
            info = _block_info(b)
            if info is None:
                continue
            rect = info["rect"]
            text = _join(info["lines"])
            if len(text.strip()) < 1:
                continue
            if (rect.y1 < 0.07 * H or rect.y0 > 0.93 * H) and len(text) < 140:
                continue  # ヘッダー・フッター
            center = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            if len(text) <= 120 and any(r.contains(center) for r in figs):
                continue  # 図の中の文字は図として見せる
            infos.append(info)

        for info in _merge_adjacent(infos):
            rect, size = info["rect"], info["size"]
            text = _join(info["lines"])
            if len(text.strip()) < 2 and not MATH_RE.search(text):
                continue
            place_figs_before(rect.y0, rect.x0, rect.x1)

            original = ""
            if orig_blocks:
                hits = []
                for i, ob in enumerate(orig_blocks):
                    if i in used_orig:
                        continue
                    orect = pymupdf.Rect(ob[:4])
                    inter = orect & rect
                    if inter.is_empty:
                        continue
                    small = min(orect.width * orect.height, rect.width * rect.height) or 1
                    if inter.width * inter.height > 0.25 * small:
                        hits.append(i)
                for i in hits:
                    used_orig.add(i)
                original = _join([_join(orig_blocks[i][4].splitlines()) for i in hits])

            n_math = len(MATH_RE.findall(text))
            if len(JP_RE.findall(text)) > 0.25 * max(len(text), 1):
                n_math = 0  # 日本語の文に混じった記号は数式扱いしない
            short = len(text) <= 90 and not text.endswith("。")
            if n_math >= 2 or (n_math and len(text) < 30) or re.fullmatch(r"\(\d+\)", text.strip()):
                kind = "eq"
            elif CAPTION_RE.match(text) and len(text) < 400:
                kind = "cap"
            elif size >= median * 1.18 and short and len(text) >= 2:
                kind = "h2"
            elif info["colored"] and short and len(text) <= 70:
                kind = "h2"
            elif info["bold"] and len(text) <= 60 and not text.endswith("。"):
                kind = "h3"
            elif info.get("heading") and len(text) <= 40 and not text.endswith(TERMINAL):
                kind = "h3"
            else:
                kind = "p"
            if pno == 0 and kind == "h2" and size > title_size and len(text) < 160:
                title_size, title = size, text

            prev = next((it for it in reversed(items) if it["t"] != "page"), None)
            adjacent = items and (items[-1] is prev or items[-1]["t"] == "page")
            # 数式の断片はまとめる
            if kind == "eq" and prev is not None and prev["t"] == "eq" and adjacent:
                prev["text"] += " " + text
                prev["_rect"] = prev["_rect"] | rect
                continue
            # 段や改ページで切れた段落はつなぐ
            if (kind == "p" and prev is not None and prev["t"] == "p" and adjacent
                    and not prev["text"].endswith(TERMINAL)
                    and (len(prev["text"]) > 80 or text[:1] in CONTINUATION)):
                prev["text"] = _join([prev["text"], text])
                if original and original not in prev.get("orig", ""):
                    prev["orig"] = _join([prev.get("orig", ""), original])
                continue
            item = {"t": kind, "text": text, "page": pno + 1}
            if kind == "eq":
                item["_rect"] = pymupdf.Rect(rect)
            if original and kind != "eq":
                item["orig"] = original
            items.append(item)
        place_figs_before(0, 0, 0, force=True)
        for it in items:
            r = it.pop("_rect", None)
            if r is not None:
                fig_no += 1
                name = f"p{pno + 1}_{fig_no}.png"
                pix = page.get_pixmap(clip=(r + (-4, -4, 4, 4)) & page.rect, dpi=200)
                pix.save(str(fig_dir / name))
                it.update({"src": name, "w": pix.width, "h": pix.height})

    return {"title": title, "items": items}


def write_reading(mono_pdf: Path, original_pdf: Path, out_dir: Path) -> dict:
    data = build_reading(mono_pdf, original_pdf, out_dir / "figs")
    (out_dir / "reading.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
