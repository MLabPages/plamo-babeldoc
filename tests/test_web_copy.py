import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from paperapp import server
from tests.test_share_keys import post, serve


class WebCopyTests(unittest.TestCase):
    def test_preview_export_and_remove_selected_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            doc = root / "local"
            sync = root / "cloud"
            out = doc / "out/plamo-0.8b"
            (out / "figs").mkdir(parents=True)
            sync.mkdir()
            (doc / "original.pdf").write_bytes(b"%PDF-test")
            (out / "figs/p1_1.png").write_bytes(b"image")
            (out / "reading.json").write_text(json.dumps({"items": [
                {"t": "p", "text": "<script>x</script>", "orig": "English"},
                {"t": "fig", "src": "p1_1.png"},
            ]}), encoding="utf-8")
            app = Mock(token="tok")
            app.library.meta.return_value = {"filename": "Paper.pdf",
                                            "translations": {"plamo-0.8b": {"status": "done"}}}
            app.library.doc_dir.return_value = doc
            local, share = serve(app), serve(app)
            app.local_server = local
            try:
                with patch.object(server, "load_settings", return_value={"web_copy_dir": str(sync)}):
                    p = local.server_address[1]
                    data = {"id": "abcdef123456", "engine": "plamo-0.8b", "pdfs": []}
                    self.assertEqual(post(share.server_address[1], "/web_copy", {"action": "list"})[0], 403)
                    status, light = post(p, "/web_copy", dict(data, action="estimate"))
                    self.assertEqual(status, 200)
                    self.assertEqual(list(sync.iterdir()), [])
                    status, saved = post(p, "/web_copy", dict(data, action="save", pdfs=["original"]))
                    self.assertEqual(status, 200)
                    self.assertGreater(saved["bytes"], light["bytes"])
                    name = saved["copies"][0]["name"]
                    html = (sync / "MLab Web Library" / name).read_text(encoding="utf-8")
                    self.assertIn("&lt;script&gt;", html)
                    self.assertIn("<summary>原文</summary>", html)
                    self.assertIn("data:image/png;base64,aW1hZ2U=", html)
                    self.assertIn("data:application/pdf;base64,JVBERi10ZXN0", html)
                    self.assertEqual(post(p, "/web_copy", {"action": "remove", "name": "../original.pdf"})[0], 400)
                    self.assertEqual(post(p, "/web_copy", {"action": "remove", "name": name}), (200, {"copies": [], "bytes": 0}))
                    self.assertTrue((doc / "original.pdf").exists())
            finally:
                for listener in (local, share):
                    listener.shutdown()
                    listener.server_close()
