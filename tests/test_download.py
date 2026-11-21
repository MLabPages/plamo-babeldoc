"""Saving translated PDFs: browser download headers and the app window's save dialog."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app  # noqa: E402
from paperapp import server  # noqa: E402

PDF = b"%PDF-1.4 test"


class DownloadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.doc = self.root / "lib" / "abcdef123456"
        (self.doc / "out" / "plamo-2b").mkdir(parents=True)
        (self.doc / "meta.json").write_text(json.dumps({"id": "abcdef123456",
            "filename": "Tan et al. (2024). - Design: Pet Robot.pdf"}), encoding="utf-8")
        (self.doc / "out" / "plamo-2b" / "translated.pdf").write_bytes(PDF)
        p = patch.object(server, "LIBRARY_DIR", self.root / "lib")
        p.start()
        self.addCleanup(p.stop)

    def test_download_link_returns_attachment_with_japanese_name(self):
        fake = Mock(library=server.Library(), token="tok")
        http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(fake))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        with patch.object(server, "ensure_reading"):
            base = f"http://127.0.0.1:{http.server_port}/api/doc/abcdef123456/translated/plamo-2b?t=tok"
            with urllib.request.urlopen(base + "&dl=1", timeout=5) as r:
                disposition = r.headers["Content-Disposition"]
                self.assertEqual(r.read(), PDF)
            with urllib.request.urlopen(base, timeout=5) as r:
                self.assertIsNone(r.headers["Content-Disposition"])  # viewing in the page stays inline
        self.assertTrue(disposition.startswith("attachment;"))
        name = urllib.parse.unquote(disposition.split("filename*=UTF-8''")[1])
        self.assertEqual(name, "Tan et al. (2024). - Design_ Pet Robot_日本語訳.pdf")

    def test_app_window_save_dialog_copies_the_pdf(self):
        dest = self.root / "saved" / "訳.pdf"
        dest.parent.mkdir()
        api = app.Api()
        api._window = Mock(create_file_dialog=Mock(return_value=str(dest)))
        with patch.object(server, "LIBRARY_DIR", self.root / "lib"):
            result = api.save_pdf("abcdef123456", "translated", "plamo-2b")
        self.assertEqual(result, {"saved": str(dest)})
        self.assertEqual(dest.read_bytes(), PDF)
        self.assertEqual(api._window.create_file_dialog.call_args.kwargs["save_filename"],
                         "Tan et al. (2024). - Design_ Pet Robot_日本語訳.pdf")

    def test_cancelled_dialog_and_bad_input_do_not_write(self):
        api = app.Api()
        api._window = Mock(create_file_dialog=Mock(return_value=None))
        self.assertEqual(api.save_pdf("abcdef123456", "translated", "plamo-2b"), {})
        self.assertIn("error", api.save_pdf("../../etc", "translated", "plamo-2b"))
        self.assertIn("error", api.save_pdf("abcdef123456", "dual", "plamo-2b"))  # not translated yet
        self.assertIn("error", api.save_pdf("abcdef123456", "translated", "no-such-engine"))

    def test_only_save_pdf_is_exposed_to_the_page(self):
        public = [n for n in dir(app.Api()) if not n.startswith("_")]
        self.assertEqual(public, ["save_pdf"])


if __name__ == "__main__":
    unittest.main()
