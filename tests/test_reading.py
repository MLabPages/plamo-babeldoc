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
        # A figure caption between the unfinished paragraph and its continuation on page 2.
        text(p1, (306, 300, 556, 315), "図1. 研究モデル。" if jp else "Fig. 1. Research model.", 8, font)
        text(p1, (40, 660, 556, 680), "* 責任著者。メールアドレス：a@example.org" if jp else
             "* Corresponding author. E-mail address: a@example.org", 7, font)
        text(p1, (40, 690, 556, 710), "https://doi.org/10.1/x 2025年受理 © 2025 Elsevier Ltd." if jp else
             "https://doi.org/10.1/x Received 5 March 2025 © 2025 Elsevier Ltd. All rights reserved.", 7, font)
        p2 = doc.new_page(width=W, height=H)
        text(p2, (40, 60, 290, 120), "多様化させることで価値を示す。" if jp else "diversify digital cues to show value.", 8, font)
        text(p2, (40, 130, 290, 145), "2. 方法" if jp else "2. Methods", 8, font, bold=not jp)
        text(p2, (40, 150, 290, 260), body, 8, font)
        # An Elsevier-style table: caption, full-width rule, cells, closing double rule.
        text(p2, (40, 300, 290, 315), "表1 信頼性。" if jp else "Table 1 Reliability.", 8, font)
        for y in (318, 360, 361.2):
            p2.draw_line((40, y), (290, y), width=.5)
        text(p2, (40, 322, 290, 336), "変数 アルファ CR" if jp else "Variable alpha CR", 8, font)
        text(p2, (40, 340, 290, 354), "感覚 0.661 0.802" if jp else "Sensory 0.661 0.802", 8, font)
        # A flat diagram (boxes and an arrow) above its caption, lower than the usual figure size.
        p2.draw_rect((320, 60, 420, 85), width=.6)
        p2.draw_rect((460, 60, 550, 85), width=.6)
        p2.draw_line((420, 72), (460, 72), width=.6)
        text(p2, (360, 92, 520, 106), "図2. モデル。" if jp else "Fig. 2. Model.", 8, font)
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

    def test_table_is_one_image_right_after_its_caption(self):
        kinds = [(i["t"], i.get("text", "")) for i in self.items]
        at = kinds.index(("cap", "表1 信頼性。"))
        self.assertEqual(kinds[at + 1][0], "fig")
        self.assertFalse(any("0.661" in t for _, t in kinds))

    def test_flat_diagram_above_caption_becomes_a_figure(self):
        kinds = [(i["t"], i.get("text", "")) for i in self.items]
        at = kinds.index(("cap", "図2. モデル。"))
        self.assertEqual(kinds[at - 1][0], "fig")


if __name__ == "__main__":
    unittest.main()


class ScannedPageTest(unittest.TestCase):
    """A scanned page stored as full-width image strips with an OCR text layer."""

    def test_page_image_strips_are_not_figures(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 40), False)
            pix.set_rect(pix.irect, (255, 255, 255))
            png = pix.tobytes("png")
            docs = []
            for jp in (False, True):
                doc = pymupdf.open()
                page = doc.new_page(width=W, height=H)
                strip = H / 10
                for k in range(10):
                    page.insert_image(pymupdf.Rect(0, k * strip, W, (k + 1) * strip), stream=png, keep_proportion=False)
                font = "japan" if jp else "tiro"
                body = "本文の段落です。" * 30 if jp else "Body paragraph text of a scanned article. " * 20
                text(page, (40, 120, 556, 300), body, 9, font)
                text(page, (40, 320, 300, 335), "表1 結果" if jp else "TABLE 1", 9, font)
                text(page, (40, 345, 556, 360), "条件 A B" if jp else "Condition  A  B", 9, font)
                text(page, (40, 365, 556, 380), "高 1.0 2.0" if jp else "High  1.0  2.0", 9, font)
                text(page, (40, 420, 556, 600), body, 9, font)
                docs.append(doc)
            paths = folder / "original.pdf", folder / "translated.pdf"
            docs[0].save(paths[0]); docs[1].save(paths[1])
            out = folder / "out"
            out.mkdir()
            data = write_reading(paths[1], paths[0], out)
            figs = [it for it in data["items"] if it["t"] == "fig"]
            # Only the table is shown as an image; the page strips stay out of the reading view.
            self.assertEqual(len(figs), 1)
            self.assertLess(figs[0]["h"], figs[0]["w"])
            self.assertTrue(any(it["t"] == "p" and len(it["text"]) > 100 for it in data["items"]))


class ReferenceFormattingTest(unittest.TestCase):
    """Hanging-indent references and numbered reference notes split cleanly into ref items."""

    def test_hanging_indent_and_numbered_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source, translated = pymupdf.open(), pymupdf.open()
            for doc, jp in ((source, False), (translated, True)):
                font = "japan" if jp else "tiro"
                p1 = doc.new_page(width=W, height=H)
                text(p1, (40, 60, 556, 85), "テスト論文のタイトル" if jp else "A Test Paper Title For References", 14, font)
                text(p1, (40, 95, 556, 150), ("本文の段落です。" * 10) if jp else ("Body paragraph text. " * 15), 9, font)
                text(p1, (40, 170, 556, 190), "参考文献" if jp else "REFERENCES", 11, font, bold=True)
                # Two hanging-indent entries whose lines are close enough to be grouped into one block.
                p1.insert_text((40, 210), "Alpha, A. First title in journal.", fontsize=9, fontname="tiro")
                p1.insert_text((56, 221), "Journal of Testing, 1970, 1, 1-10.", fontsize=9, fontname="tiro")
                p1.insert_text((40, 232), "Beta, B. Second title in journal.", fontsize=9, fontname="tiro")
                p1.insert_text((56, 243), "Journal of Testing, 1971, 2, 11-20.", fontsize=9, fontname="tiro")
                p2 = doc.new_page(width=W, height=H)
                text(p2, (40, 60, 556, 80), "参考文献" if jp else "REFERENCE NOTES", 11, font, bold=True)
                if jp:
                    text(p2, (40, 95, 556, 200),
                         "1. McDaniel, C. K. 色覚と色命名。1972年。 "
                         "2. Rosch, E. 非典型性効果。1975年。 "
                         "3. Mervis, C. B. 単語頻度の関係。1975年。（1975年6月3日受理）", 9, font)
                else:
                    text(p2, (40, 95, 556, 200),
                         "1. McDaniel, C. K. Hue naming. 1972.\n"
                         "2. Rosch, E. Typicality effects. 1975.\n"
                         "3. Mervis, C. B. Word frequency. 1975.\n(Accepted June 3, 1975)", 9, font)
            paths = folder / "original.pdf", folder / "translated.pdf"
            source.save(paths[0]); translated.save(paths[1])
            out = folder / "out"; out.mkdir()
            data = write_reading(paths[1], paths[0], out)
            refs = [it for it in data["items"] if it["t"] == "ref"]
            self.assertEqual(len(refs), 5)
            self.assertTrue(refs[0]["text"].startswith("Alpha, A.") and refs[0]["text"].endswith("1-10."))
            self.assertTrue(refs[1]["text"].startswith("Beta, B.") and refs[1]["text"].endswith("11-20."))
            self.assertTrue(refs[2]["text"].startswith("1. McDaniel"))
            self.assertTrue(refs[3]["text"].startswith("2. Rosch"))
            self.assertTrue(refs[4]["text"].startswith("3. Mervis"))
            self.assertNotIn("受理", refs[4]["text"])
            self.assertTrue(any(it["t"] == "p" and "1975年6月3日受理" in it["text"] for it in data["items"]))
