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
READING_VERSION = 4
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+[^\d\W]", re.UNICODE)
LETTERED_HEADING = re.compile(r"^([IVX]{1,5}|[A-H])\.\s+[A-Z]")


def _key(text: str) -> str:
    return "".join(c.lower() for c in text if c.isalnum())


def _tidy_heading(text: str) -> str:
    # "A B S T R A C T" -> "ABSTRACT"
    return re.sub(r"\b(?:[A-Z] ){3,}[A-Z]\b", lambda m: m.group(0).replace(" ", ""), text)


def reading_is_current(out_dir: Path) -> bool:
    try:
        return json.loads((out_dir / "reading.json").read_text(encoding="utf-8")).get("version") == READING_VERSION
    except (OSError, ValueError):
        return False


def _source_layout(doc: pymupdf.Document) -> list[list[dict]]:
    """Use the original typography, not resized translated fragments, as structure."""
    toc = doc.get_toc()
    sizes = sorted(sp["size"] for page in doc for b in page.get_text("dict")["blocks"] if b["type"] == 0
                   for ln in b["lines"] for sp in ln["spans"] for _ in sp["text"].strip())
    median = sizes[len(sizes) // 2] if sizes else 10.0
    result = []
    for pno, page in enumerate(doc):
        blocks = []
        heading_keys = {_key(label) for level, label, p in toc if p == pno + 1 and level > 1}
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            pending = []
            pending_kind = None
            heading_acc = ""

            def flush():
                if pending:
                    rect = pymupdf.Rect(pending[0]["bbox"])
                    for line in pending[1:]:
                        rect |= pymupdf.Rect(line["bbox"])
                    blocks.append({"type": 0, "bbox": tuple(rect), "lines": list(pending)})
                    pending.clear()

            for line in block["lines"]:
                text = "".join(s["text"] for s in line["spans"]).strip()
                if heading_acc:
                    acc = heading_acc + _key(text)
                    if acc in heading_keys:
                        pending.append(line)
                        flush()
                        pending_kind, heading_acc = None, ""
                        continue
                    if any(k.startswith(acc) for k in heading_keys):
                        pending.append(line)
                        heading_acc = acc
                        continue
                    flush()
                    pending_kind, heading_acc = None, ""
                line_key = _key(text)
                if len(line_key) >= 8 and line_key not in heading_keys and any(
                        k.startswith(line_key) for k in heading_keys):
                    flush()  # a long section title wrapped onto the next line
                    pending.append(line)
                    pending_kind, heading_acc = "heading", line_key
                    continue
                styled = any(s["flags"] & (2 | 16) for s in line["spans"])
                spans = [s for s in line["spans"] if s["text"].strip()]
                all_bold = bool(spans) and all(s["flags"] & 16 or "bold" in s["font"].lower() for s in spans)
                if pending_kind == "open" and len(text) < 90:
                    kind = "open_end"  # e.g. "INTRODUCTION" after a separate "I." line
                elif not toc and re.fullmatch(r"[IVX]{1,5}\.|[A-H]\.", text):
                    kind = "open"
                elif (_key(text) in heading_keys or (NUMBERED_HEADING.match(text) and styled and len(text) < 120)
                        or (not toc and LETTERED_HEADING.match(text) and len(text) < 90)):
                    kind = "heading"  # a known section line always starts its own block
                elif not toc and all_bold:
                    kind = "bold"     # consecutive bold lines stay together (titles, abstracts)
                else:
                    kind = "body"
                if kind == "open_end":
                    pending.append(line)
                    flush()
                    pending_kind = None
                    continue
                if kind in ("heading", "open") or kind != pending_kind:
                    flush()
                pending.append(line)
                pending_kind = kind
                if kind == "heading":
                    flush()
                    pending_kind = None
            flush()
        infos = [i for b in blocks
                 if (i := _block_info(b)) is not None]
        merged: list[dict] = []
        for info in infos:
            prev = merged[-1] if merged else None
            gap = info["rect"].y0 - prev["rect"].y1 if prev is not None else 0
            large = info["size"] >= median * 1.18 and 0 <= gap < info["size"] * 2
            # A colored/bold heading wrapped into one block per line, e.g. "The future lies in
            # specialized models" + "for specific tasks".
            wrapped_heading = (prev is not None and (info["bold"] or info["colored"])
                               and prev["colored"] == info["colored"] and info["size"] >= median * .97
                               and len(_join(prev["lines"] + info["lines"])) <= 90
                               and -info["size"] < gap < info["size"] * .6)
            if (prev is not None and not toc and (large or wrapped_heading)
                    and abs(prev["size"] - info["size"]) < .5 and prev["bold"] == info["bold"]
                    and not (info["rect"].x1 < prev["rect"].x0 or info["rect"].x0 > prev["rect"].x1)
                    and not _join(prev["lines"]).endswith(TERMINAL)):
                prev["lines"] += info["lines"]  # pull quotes and sidebar titles split into one block per line
                prev["rect"] = prev["rect"] | info["rect"]
                continue
            merged.append(info)
        infos = merged
        masthead = any("contentslistsavailable" in _key(_join(i["lines"]))
                       or "journalhomepage" in _key(_join(i["lines"])) for i in infos)
        for index, info in enumerate(infos):
            text, r = _join(info["lines"]), info["rect"]
            info.update(source_id=index, text=text, role="body", level=0)
            margin = (r.y1 < page.rect.height * .07 or r.y0 > page.rect.height * .94) and r.height < 35
            publication = pno == 0 and (
                (masthead and r.y1 < page.rect.height * .18)
                or (r.y0 > page.rect.height * .80 and re.search(
                    r"corresponding author|e-?mail address|https?://doi\.org|received\s|available online|©|all rights",
                    text, re.I)))
            contact = r.y0 > page.rect.height * .55 and re.search(
                r"corresponding author|e-?mail addresses?:", text, re.I)
            if margin or publication or contact:
                info["role"] = "noise"
                continue
            if (r.y0 > page.rect.height * .6 and info["size"] < median * .95
                    and re.match(r"^(\*|†|‡|§|¶|[¹²³⁴⁵⁶⁷⁸⁹]|\d{1,2}\s)", text)):
                info["role"] = "note"  # footnote: shown after the paragraph it interrupts
                continue
            for level, label, target_page in toc:
                k, label_key = _key(text), _key(label)
                if target_page == pno + 1 and (k == label_key or
                        (level == 1 and len(label_key) > 60 and k.startswith(label_key))):
                    info.update(role="title" if level == 1 and pno == 0 else "heading", level=level,
                                source_heading=label)
                    break
            if info["role"] == "body" and len(text) < 160 and len(info["lines"]) <= 3:
                number = NUMBERED_HEADING.match(text)
                lettered = LETTERED_HEADING.match(text)
                table_row = sum(1 for o in infos if o is not info and abs(o["rect"].y0 - r.y0) < 3
                                and len(_join(o["lines"])) < 40) >= 1
                if number and (info["bold"] or info["italic"]):
                    info.update(role="heading", level=min(5, number[1].count(".") + 2), source_heading=text)
                elif _key(text) in {"abstract", "references", "conclusion", "conclusions", "acknowledgements", "acknowledgments"}:
                    info.update(role="heading", level=2, source_heading=text)
                elif not toc and lettered and len(text) <= 90 and not table_row:
                    info.update(role="heading", level=2 if len(lettered[1]) > 1 or lettered[1] == "I" else 3,
                                source_heading=text)
                elif (not toc and len(text) <= 90 and len(info["lines"]) <= 2 and not text.endswith(TERMINAL)
                      and not table_row and sum(c.isalpha() for c in text) >= 4
                      # Bold/colored text smaller than body text is a label in a figure,
                      # sidebar or author box, not a section heading.
                      and (info["size"] >= median * 1.18
                           or ((info["bold"] or info["colored"]) and info["size"] >= median * .97))):
                    info.update(role="heading", level=2 if info["size"] >= median * 1.18 else 3,
                                source_heading=text)
                elif (not toc and (info["bold"] or info["colored"]) and info["size"] < median * .97
                      and len(text) <= 60 and len(info["lines"]) <= 3):
                    info["role"] = "label"  # small label inside a figure, sidebar or author box
        if pno == 0 and not any(i["role"] == "title" for i in infos):
            candidates = [i for i in infos if i["role"] != "noise" and len(i["text"]) > 25
                          and i["rect"].y0 < page.rect.height * .40]
            if candidates:
                title = max(candidates, key=lambda i: i["size"])
                title.update(role="title", level=1, source_heading=title["text"])
        result.append(infos)
    return result


def _source_match(rect: pymupdf.Rect, infos: list[dict]) -> dict | None:
    candidates = []
    for info in infos:
        r = info["rect"]
        overlap = (rect & r).get_area() / max(rect.get_area(), 1)
        if overlap > .35:
            candidates.append((overlap, -abs((r.y0 + r.y1) / 2 - (rect.y0 + rect.y1) / 2), info))
    return max(candidates, key=lambda c: c[:2])[2] if candidates else None


def _split_by_source(block: dict, sources: list[dict]) -> list[dict]:
    """A translated PDF block can contain both a section heading and body lines."""
    if not sources:
        return [block]
    groups = []
    for line in block.get("lines", []):
        source = _source_match(pymupdf.Rect(line["bbox"]), sources)
        key = source["source_id"] if source else None
        if groups and groups[-1][0] == key:
            groups[-1][1].append(line)
        else:
            groups.append((key, [line]))
    result = []
    for _, lines in groups:
        rect = pymupdf.Rect(lines[0]["bbox"])
        for line in lines[1:]:
            rect |= pymupdf.Rect(line["bbox"])
        result.append({"type": 0, "bbox": tuple(rect), "lines": lines})
    return result


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
    lines, size, bold_chars, italic_chars, color_chars, chars = [], 0.0, 0, 0, 0, 0
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
            if sp["flags"] & 2 or "italic" in sp.get("font", "").lower():
                italic_chars += n
            if not _is_dark(sp.get("color", 0)):
                color_chars += n
        lines.append(t)
    if not lines or chars == 0:
        return None
    return {"rect": pymupdf.Rect(block["bbox"]), "lines": lines, "size": size,
            "bold": bold_chars / chars > 0.8, "italic": italic_chars / chars > 0.8,
            "colored": color_chars / chars > 0.8}


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
            same_source = b.get("source_id") == p.get("source_id")
            if same_source and b.get("source_id") is not None:
                same_col = True  # 原文の同じ段落内の字下げ・折り返しを許容
                same_style = True  # 訳文の書体・文字サイズの揺れでも原文の1段落は分けない
            if same_style and same_col and same_source and -2 <= gap < p["size"] * 0.9:
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


FIGURE_MARK = re.compile(r"^(FIGURE|Figure|Fig\.?|EXHIBIT|Exhibit)\s*\d")


def _panels(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Boxed infographics: a large drawn panel whose figure label sits inside it."""
    area = page.rect.get_area()
    marks = [pymupdf.Rect(b[:4]) for b in page.get_text("blocks") if b[6] == 0 and FIGURE_MARK.match(b[4])]
    if not marks:
        return []
    try:
        clusters = page.cluster_drawings()
    except Exception:
        return []
    return [pymupdf.Rect(c) & page.rect for c in clusters
            if .15 * area < pymupdf.Rect(c).get_area() < .92 * area
            and any(pymupdf.Rect(c).contains(m) for m in marks)]


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
    source_pages = _source_layout(orig) if orig is not None else []

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
    notes: list[dict] = []
    for pno, (page, blocks) in enumerate(zip(doc, pages)):
        H = page.rect.height
        items.append({"t": "page", "page": pno + 1})
        fig_list = _figure_rects(page, blocks)
        # 囲み型の図（枠の中に「FIGURE 1」などがある文字の多いインフォグラフィック）は
        # 中の文字を本文として並べず、図として画像で見せる
        panels = _panels(orig[pno]) if orig is not None and pno < orig.page_count else []
        if panels:
            fig_list = [(r, ras) for r, ras in fig_list
                        if not any((p & r).get_area() > .5 * r.get_area() for p in panels)]
            fig_list += [(p, None) for p in panels]
        figs = [r for r, _ in fig_list]
        placed = [False] * len(figs)
        orig_blocks = []
        used_orig: set[int] = set()
        sources = source_pages[pno] if pno < len(source_pages) else []
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
        text_blocks = [part for b in blocks if b["type"] == 0 for part in _split_by_source(b, sources)]
        for b in text_blocks:
            info = _block_info(b)
            if info is None:
                continue
            rect = info["rect"]
            text = _join(info["lines"])
            if len(text.strip()) < 1:
                continue
            source = _source_match(rect, sources)
            if source:
                if source["role"] == "noise":
                    continue
                info.update(source_id=source["source_id"], role=source["role"], level=source["level"],
                            source_heading=source.get("source_heading", ""), source_text=source["text"])
            if (rect.y1 < 0.07 * H or rect.y0 > 0.93 * H) and len(text) < 140:
                continue  # ヘッダー・フッター
            center = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            if len(text) <= 120 and any(r.contains(center) for r in figs):
                continue  # 図の中の文字は図として見せる
            if any(p.contains(center) for p in panels):
                continue
            infos.append(info)

        for info in _merge_adjacent(infos):
            rect, size = info["rect"], info["size"]
            text = _join(info["lines"])
            if len(text.strip()) < 2 and not MATH_RE.search(text):
                continue
            place_figs_before(rect.y0, rect.x0, rect.x1)

            original = ""
            if info.get("source_text"):
                source_id = info["source_id"]
                if source_id not in used_orig:
                    original = info["source_text"]
                    used_orig.add(source_id)
            elif orig_blocks and not sources:
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
            elif info.get("role") in ("title", "heading"):
                kind = "h2" if info.get("level", 2) <= 2 else "h3"
            elif info.get("role") == "note":
                kind = "note"
            elif info.get("role") == "label":
                kind = "label"
            elif not sources and short and NUMBERED_HEADING.match(text) and (info["bold"] or info["italic"]):
                kind = "h2"
            else:
                kind = "p"
            if info.get("role") == "title":
                title = text
            elif not sources and pno == 0 and kind == "h2" and size > title_size and len(text) < 160:
                title_size, title = size, text

            prev = next((it for it in reversed(items) if it["t"] != "page"), None)
            adjacent = items and (items[-1] is prev or items[-1]["t"] == "page")
            if kind == "note":
                notes.append({"t": "note", "text": text, "page": pno + 1, **({"orig": original} if original else {})})
                continue
            # 数式の断片はまとめる
            if kind == "eq" and prev is not None and prev["t"] == "eq" and adjacent:
                prev["text"] += " " + text
                prev["_rect"] = prev["_rect"] | rect
                continue
            # 段や改ページで切れた段落はつなぐ。間に図・図の説明・ページ区切り・脚注が
            # 挟まっていても、文が終わっていない段落の続きとみなす
            if kind == "p":
                k = len(items) - 1
                while k >= 0 and items[k]["t"] in ("page", "fig", "cap", "note"):
                    k -= 1
                if k >= 0 and items[k]["t"] == "p":
                    prev, adjacent = items[k], True
                    crossed = k < len(items) - 1
                else:
                    crossed = False
                # 同じページで次の段へ移った（前のブロックより上から始まる）文章も続きとみなす。
                # 表のセルは短いので対象にしない
                last = prev.get("_r") if prev is not None else None
                if (last and last[0] == pno and rect.y0 < last[2] - 30
                        and len(prev["text"]) >= 20 and len(text) >= 20):
                    crossed = True
                # 訳文は日本語の文が「。」で終わっていなければ途中。原文の段落・ブロック境界を
                # 越えて訳されたものも、すぐ下に続く日本語の文章ならつなぐ
                if (last and last[0] == pno and -6 <= rect.y0 - last[3] < 14 and abs(rect.x0 - last[1]) < 40
                        and len(prev["text"]) >= 20 and len(text) >= 10
                        and JP_RE.search(prev["text"][-10:]) and JP_RE.search(text[:10])):
                    crossed = True
                # 図などで右の段の途中から続く場合（左右の段をまたぐ）
                if (last and last[0] == pno and rect.x0 - last[1] > 100
                        and len(prev["text"]) >= 20 and len(text) >= 10
                        and JP_RE.search(prev["text"][-6:]) and JP_RE.search(text[:6])):
                    crossed = True
            if (kind == "p" and prev is not None and prev["t"] == "p" and adjacent
                    and not prev["text"].endswith(TERMINAL)
                    and (len(prev["text"]) > 80 or text[:1] in CONTINUATION or crossed)):
                prev["text"] = _join([prev["text"], text])
                prev["_r"] = (pno, rect.x0, rect.y0, rect.y1)
                if original and original not in prev.get("orig", ""):
                    prev["orig"] = _join([prev.get("orig", ""), original])
                continue
            item = {"t": kind, "text": text, "page": pno + 1}
            if kind == "p":
                item["_r"] = (pno, rect.x0, rect.y0, rect.y1)
            if kind in ("h2", "h3"):
                item["text"] = _tidy_heading(text)
                item.update(level=info.get("level", 2), source_heading=info.get("source_heading", text),
                            x=rect.x0, y=rect.y0)
            if kind == "eq":
                item["_rect"] = pymupdf.Rect(rect)
            if original and kind != "eq":
                item["orig"] = original
            items.extend(notes)
            notes.clear()
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

    items.extend(notes)
    for it in items:
        it.pop("_r", None)
    source_toc = orig.get_toc() if orig is not None else []
    doc.close()
    if orig is not None:
        orig.close()
    return {"version": READING_VERSION, "title": title, "items": items, "source_toc": source_toc}


def write_reading(mono_pdf: Path, original_pdf: Path, out_dir: Path) -> dict:
    from .pdf_outline import write_outline

    data = build_reading(mono_pdf, original_pdf, out_dir / "figs")
    write_outline(mono_pdf, mono_pdf, data)
    if (out_dir / "dual.pdf").exists():
        write_outline(out_dir / "dual.pdf", mono_pdf, data)
    tmp = out_dir / "reading.tmp.json"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_dir / "reading.json")
    return data
