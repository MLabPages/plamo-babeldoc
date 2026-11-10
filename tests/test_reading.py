"""Reading-mode structure regressions with small synthetic source/translated PDFs."""
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from paperapp.reading import READING_VERSION, write_reading

W, H = 595, 794
LEFT, RIGHT = pymupdf.Rect(40, 120, 290, 700), pymupdf.Rect(306, 120, 556, 700)


def text(page, rect, value, size=8, font="tiro", bold=False):
    page.insert_textbox(pymupdf.Rect(rect), value, fontsize=size, fontname="tibo" if bold and font == "tiro" else font)


def make_pair(folder: Path) -> tuple[Path, Path]:
    source, translated = pymupdf.open(), pymupdf.open()
    for doc, jp in ((source, False), (translated, True)):
        font = "japan" if jp else "tiro"
        p1 = doc.new_page(width=W, height=H)
        text(p1, (40, 60, 556, 100), "日本語の論文タイトル" if jp else "An English paper title for testing", 14, font)
        text(p1, (40, 130, 290, 145), "1. はじめに" if jp else "1. Introduction", 8, font, bold=not jp)
        body = "本文の段落です。" * 12 if jp else "Body paragraph text. " * 25
        text(p1, (40, 150, 290, 260), body, 8, font)
        # A paragraph whose translation is split into a long fragment and a short last line.
        if jp:
            text(p1, (306, 130, 556, 145), "植物性食品の主要な流通チャネルとして、ソーシャルコマースプラッ", 7.6, font)
            text(p1, (306, 144, 556, 159), "トフォームは人工知能などのデジタル技術を活用して", 7.6, font)
        else:
            text(p1, (306, 130, 556, 160), "As a key distribution channel for plant-based food, social commerce "
                 "platforms employ digital technologies like artificial intelligence to", 8, font)
        text(p1, (40, 660, 556, 680), "* 責任著者。メールアドレス：a@example.org" if jp else
             "* Corresponding author. E-mail address: a@example.org", 7, font)
        text(p1, (40, 690, 556, 710), "https://doi.org/10.1/x 2025年受理 © 2025 Elsevier Ltd." if jp else
             "https://doi.org/10.1/x Received 5 March 2025 © 2025 Elsevier Ltd. All rights reserved.", 7, font)
        p2 = doc.new_page(width=W, height=H)
        text(p2, (40, 60, 290, 120), "多様化させることで価値を示す。" if jp else "diversify digital cues to show value.", 8, font)
        text(p2, (40, 130, 290, 145), "2. 方法" if jp else "2. Methods", 8, font, bold=not jp)
        text(p2, (40, 150, 290, 260), body, 8, font)
    source.set_toc([[1, "An English paper title for testing", 1], [2, "1 Introduction", 1], [2, "2 Methods", 2]])
    paths = folder / "original.pdf", folder / "translated.pdf"
    source.save(paths[0]); translated.save(paths[1])
    dual = pymupdf.open()
    for i in range(2):
        page = dual.new_page(width=W * 2, height=H)
        page.show_pdf_page(pymupdf.Rect(0, 0, W, H), source, i)
        page.show_pdf_page(pymupdf.Rect(W, 0, W * 2, H), translated, i)
    dual.save(folder / "dual.pdf")
    return paths


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.original, self.translated = make_pair(self.dir)
        self.data = write_reading(self.translated, self.original, self.dir)
        self.items = [i for i in self.data["items"] if i["t"] != "page"]

    def test_publication_and_contact_text_are_removed(self):
        joined = " ".join(i.get("text", "") for i in self.items)
        for word in ("責任著者", "メールアドレス", "doi.org", "Elsevier"):
            self.assertNotIn(word, joined)

    def test_headings_follow_source_structure(self):
        headings = [(i["t"], i["text"]) for i in self.items if i["t"] in ("h2", "h3")]
        self.assertEqual([h[1] for h in headings], ["日本語の論文タイトル", "1. はじめに", "2. 方法"])
        self.assertEqual(self.data["title"], "日本語の論文タイトル")

    def test_short_translated_line_is_joined_and_continues_on_next_page(self):
        para = next(i["text"] for i in self.items if i["t"] == "p" and i["text"].startswith("植物性食品"))
        self.assertIn("プラットフォームは人工知能", para)
        self.assertTrue(para.endswith("多様化させることで価値を示す。"))

    def test_pdf_bookmarks_are_translated_expanded_and_opened(self):
        for name, x_min in (("translated.pdf", 0), ("dual.pdf", W)):
            with pymupdf.open(self.dir / name) as doc:
                toc = doc.get_toc(False)
                self.assertEqual([t[1] for t in toc], ["日本語の論文タイトル", "1. はじめに", "2. 方法"])
                self.assertEqual([t[2] for t in toc], [1, 1, 2])
                self.assertTrue(all(not t[3].get("collapse") for t in toc))
                self.assertGreaterEqual(toc[1][3]["to"].x, x_min)
                self.assertEqual(doc.pagemode, "UseOutlines")

    def test_rebuild_marker_is_written(self):
        saved = json.loads((self.dir / "reading.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["version"], READING_VERSION)


if __name__ == "__main__":
    unittest.main()
