"""Queue/cancellation regressions. Uses temporary PDFs and no translation API."""
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import pymupdf

from paperapp import server


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        p = patch.object(server, "LIBRARY_DIR", self.root)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(server, "load_settings", return_value={"translate_references": False})
        p.start()
        self.addCleanup(p.stop)
        self.lib = server.Library()
        self.llama = Mock()
        with patch.object(server.threading.Thread, "start"):
            self.jobs = server.Jobs(self.lib, self.llama)
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), "A synthetic test paper.")
            self.pdf = doc.tobytes()
        self.doc_id = self.lib.add("test.pdf", self.pdf)
        self.engine = "plamo-0.8b"

    def translation(self):
        return self.lib.meta(self.doc_id)["translations"].get(self.engine, {})

    def queued(self):
        self.jobs.submit(self.doc_id, self.engine)
        return self.jobs.q.get_nowait()

    def drain(self):
        # Run the actual loop, ending once its finite test queue is empty.
        items = []
        while not self.jobs.q.empty():
            items.append(self.jobs.q.get_nowait())
        with patch.object(self.jobs.q, "get", side_effect=items + [StopIteration]):
            with self.assertRaises(StopIteration):
                self.jobs._loop()

    def process(self, code=0, lines=""):
        out = self.lib.doc_dir(self.doc_id) / "out" / self.engine
        (out / "test.mono.pdf").write_bytes(self.pdf)
        return Mock(stdout=io.StringIO(lines), returncode=code, wait=Mock(return_value=code))

    def run_job(self, item, code=0, lines="", reading=None):
        with patch.object(server.REGISTRY[self.engine], "available", return_value=(True, "")), \
             patch.object(server.subprocess, "Popen", side_effect=lambda *a, **kw: self.process(code, lines)), \
             patch.object(server, "write_reading", side_effect=reading or (lambda *a: {"title": "Test title"})) as read:
            self.jobs._run(*item)
            return read

    def test_concurrent_submissions_only_queue_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: self.jobs.submit(self.doc_id, self.engine), range(20)))
        self.assertEqual(self.jobs.q.qsize(), 1)

    def test_canceled_queue_entry_cannot_run_retry(self):
        self.jobs.submit(self.doc_id, self.engine)
        old = self.translation()["job_id"]
        self.jobs.cancel(self.doc_id, self.engine)
        self.jobs.submit(self.doc_id, self.engine)
        new = self.translation()["job_id"]
        with patch.object(self.jobs, "_run") as run:
            self.drain()
        self.assertNotEqual(old, new)
        run.assert_called_once_with(self.doc_id, self.engine, new)

    def test_cancel_during_model_start_does_not_launch_worker(self):
        item = self.queued()
        self.llama.ensure.side_effect = lambda _: self.jobs.cancel(self.doc_id, self.engine)
        with patch.object(server.REGISTRY[self.engine], "available", return_value=(True, "")), \
             patch.object(server.subprocess, "Popen") as spawn:
            self.jobs._run(*item)
        spawn.assert_not_called()
        self.assertEqual(self.translation()["status"], "canceled")

    def test_old_failure_cannot_overwrite_retry(self):
        self.jobs.submit(self.doc_id, self.engine)

        def fail(*args):
            self.jobs.cancel(self.doc_id, self.engine)
            self.jobs.submit(self.doc_id, self.engine)
            raise RuntimeError("late failure from canceled attempt")

        with patch.object(self.jobs, "_run", side_effect=fail):
            self.drain()
        self.assertEqual(self.translation()["status"], "queued")
        self.assertEqual(self.translation()["error"], "")

    def test_nonzero_exit_is_failure_even_with_pdf(self):
        read = self.run_job(self.queued(), code=1)
        read.assert_not_called()
        self.assertEqual(self.translation()["status"], "error")

    def test_explicit_error_is_failure_even_with_zero_exit(self):
        read = self.run_job(self.queued(), lines='@@{"event":"error","error":"test failure"}\n')
        read.assert_not_called()
        self.assertEqual(self.translation()["error"], "test failure")

    def test_success_publishes_pdf_and_reading(self):
        self.run_job(self.queued())
        self.assertEqual(self.translation()["status"], "done")
        self.assertTrue((self.lib.doc_dir(self.doc_id) / "out" / self.engine / "translated.pdf").exists())

    def test_cancel_during_reading_is_not_marked_done(self):
        def reading(*args):
            self.jobs.cancel(self.doc_id, self.engine)
            return {"title": "Must not be published"}
        self.run_job(self.queued(), reading=reading)
        self.assertEqual(self.translation()["status"], "canceled")
        self.assertNotIn("title_ja", self.lib.meta(self.doc_id))

    def test_recover_legacy_job_preserves_reference_option(self):
        self.lib.update_translation(self.doc_id, self.engine, status="running", refs=True)
        self.jobs.recover()
        self.assertEqual(self.jobs.q.qsize(), 1)
        self.assertTrue(self.translation()["refs"])
        self.assertEqual(self.translation()["status"], "queued")

    def test_invalid_pdf_leaves_no_library_entry(self):
        before = set(self.root.iterdir())
        with self.assertRaisesRegex(ValueError, "PDFを読み込めません"):
            self.lib.add("broken.pdf", b"%PDF broken")
        self.assertEqual(set(self.root.iterdir()), before)

    def test_password_pdf_leaves_no_library_entry(self):
        with pymupdf.open(stream=self.pdf, filetype="pdf") as doc:
            encrypted = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                                   owner_pw="owner", user_pw="reader")
        before = set(self.root.iterdir())
        with self.assertRaisesRegex(ValueError, "パスワード付きPDF"):
            self.lib.add("locked.pdf", encrypted)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_http_upload_validation_and_acceptance(self):
        app = Mock(library=self.lib, token="test-only-token")
        http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{http.server_port}/api/translate?engine={self.engine}&name=test.pdf"
        try:
            for data, expected in ((b"%PDF broken", 400), (self.pdf, 200)):
                request = urllib.request.Request(url, data=data, headers={"X-Token": app.token})
                try:
                    response = urllib.request.urlopen(request, timeout=5)
                except urllib.error.HTTPError as e:
                    response = e
                with response:
                    self.assertEqual(response.status, expected)
                    body = json.load(response)
                if expected == 400:
                    self.assertIn("PDFを読み込めません", body["error"])
                    app.jobs.submit.assert_not_called()
                else:
                    app.jobs.submit.assert_called_once_with(body["id"], self.engine, None)
                    self.assertEqual(self.lib.meta(body["id"])["pages"], 1)
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
