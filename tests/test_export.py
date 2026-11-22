"""Automatic copies of finished PDFs to a cloud-synced folder, for reading on the iPad without the PC."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paperapp import server  # noqa: E402
from tests.test_share_keys import post, serve  # noqa: E402


class ExportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.sync = self.root / "OneDrive" / "論文の訳"
        self.sync.mkdir(parents=True)
        self.out = self.root / "doc" / "out" / "plamo-2b"
        self.out.mkdir(parents=True)
        (self.out / "translated.pdf").write_bytes(b"%PDF ja")
        (self.out / "dual.pdf").write_bytes(b"%PDF dual")
        self.meta = {"id": "abcdef123456", "filename": "Tan (2024) - Pet Robot.pdf",
                     "translations": {"plamo-2b": {"status": "done"}, "plamo-8b": {"status": "running"}}}
        self.settings = {"export_dir": str(self.sync)}
        p = patch.object(server, "load_settings", side_effect=lambda: dict(self.settings))
        p.start()
        self.addCleanup(p.stop)

    def test_copies_translation_and_bilingual_pdfs(self):
        written = server.export_pdfs(self.meta, "plamo-2b", self.out)
        self.assertEqual(sorted(p.name for p in written),
                         ["Tan (2024) - Pet Robot_対訳_plamo-2b.pdf", "Tan (2024) - Pet Robot_日本語訳_plamo-2b.pdf"])
        self.assertEqual((self.sync / "Tan (2024) - Pet Robot_日本語訳_plamo-2b.pdf").read_bytes(), b"%PDF ja")
        self.assertEqual(list(self.sync.glob("*.part")), [])

    def test_does_nothing_without_a_folder(self):
        self.settings["export_dir"] = ""
        self.assertEqual(server.export_pdfs(self.meta, "plamo-2b", self.out), [])
        self.settings["export_dir"] = str(self.root / "missing")
        self.assertEqual(server.export_pdfs(self.meta, "plamo-2b", self.out), [])

    def test_settings_and_export_all_only_from_the_pc_window(self):
        app = Mock(token="tok")
        app.library.list.return_value = [self.meta]
        app.library.doc_dir.return_value = self.root / "doc"
        local = serve(app)
        app.local_server = local
        share = serve(app)
        for s in (local, share):
            self.addCleanup(s.server_close)
            self.addCleanup(s.shutdown)
        with patch.object(server, "save_settings") as save:
            self.assertEqual(post(share.server_address[1], "/settings", {"export_dir": str(self.sync)})[0], 403)
            self.assertEqual(post(local.server_address[1], "/settings", {"export_dir": str(self.root / "nope")})[0], 400)
            self.assertEqual(post(local.server_address[1], "/settings", {"export_dir": str(self.sync)})[0], 200)
            save.assert_called_once_with({"export_dir": str(self.sync)})
        self.assertEqual(post(share.server_address[1], "/export_all", {})[0], 403)
        status, body = post(local.server_address[1], "/export_all", {})
        self.assertEqual((status, body), (200, {"ok": True, "files": 2}))  # running 8B is skipped


if __name__ == "__main__":
    unittest.main()

