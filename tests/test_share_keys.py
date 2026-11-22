"""API keys from the settings screen, share-port fallback and the Tailscale address for remote reading."""
import json
import socket
import sys
import threading
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paperapp import server  # noqa: E402


def serve(app, host="127.0.0.1"):
    http = server.ThreadingHTTPServer((host, 0), server.make_handler(app))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    return http


def post(port, path, body, token="tok"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api{path}", data=json.dumps(body).encode(),
                                 headers={"X-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.app = Mock(token="tok")
        self.local = serve(self.app)
        self.app.local_server = self.local
        self.addCleanup(self.local.server_close)
        self.addCleanup(self.local.shutdown)
        self.port = self.local.server_address[1]

    def test_saves_and_deletes_known_key_without_echoing_it(self):
        with patch.object(server, "set_user_env") as setenv:
            status, body = post(self.port, "/keys", {"name": "DEEPL_API_KEY", "value": "  abc:fx  "})
            self.assertEqual((status, body), (200, {"ok": True, "set": True}))
            setenv.assert_called_with("DEEPL_API_KEY", "abc:fx")
            status, body = post(self.port, "/keys", {"name": "DEEPL_API_KEY", "value": None})
            self.assertEqual(body["set"], False)
            setenv.assert_called_with("DEEPL_API_KEY", None)

    def test_rejects_unknown_names_bad_values_and_wrong_token(self):
        with patch.object(server, "set_user_env") as setenv:
            self.assertEqual(post(self.port, "/keys", {"name": "PATH", "value": "x"})[0], 400)
            self.assertEqual(post(self.port, "/keys", {"name": "GEMINI_API_KEY", "value": "a\nb"})[0], 400)
            self.assertEqual(post(self.port, "/keys", {"name": "GEMINI_API_KEY", "value": "x" * 600})[0], 400)
            self.assertEqual(post(self.port, "/keys", {"name": "GEMINI_API_KEY", "value": "x"}, token="bad")[0], 401)
            setenv.assert_not_called()

    def test_share_listener_cannot_set_keys(self):
        share = serve(self.app)  # same handler, but not the PC's own window server
        self.addCleanup(share.server_close)
        self.addCleanup(share.shutdown)
        with patch.object(server, "set_user_env") as setenv:
            self.assertEqual(post(share.server_address[1], "/keys", {"name": "GEMINI_API_KEY", "value": "x"})[0], 403)
            setenv.assert_not_called()


class ShareTests(unittest.TestCase):
    def fake_app(self):
        obj = types.SimpleNamespace(share_server=None, local_server=None, share_port=server.SHARE_PORT, token="tok")
        obj.share_info = lambda: server.App.share_info(obj)
        return obj

    def test_uses_next_free_port_when_share_port_is_taken(self):
        blocker = socket.socket()
        try:
            blocker.bind(("0.0.0.0", server.SHARE_PORT))
            blocker.listen()
        except OSError:
            pass  # already taken by another app on this PC, which is the same situation
        self.addCleanup(blocker.close)
        obj = self.fake_app()
        with patch.object(server, "tailscale_ip", return_value=None):
            info = server.App.set_share(obj, True)
        self.addCleanup(lambda: server.App.set_share(obj, False))
        self.assertGreater(obj.share_port, server.SHARE_PORT)
        self.assertIn(f":{obj.share_port}/?t=tok", info["url"])
        self.assertIsNone(info["remote_url"])

    def test_remote_url_uses_tailscale_address(self):
        obj = self.fake_app()
        obj.share_server = object()
        obj.share_port = 8766
        with patch.object(server, "tailscale_ip", return_value="100.101.102.103"):
            info = server.App.share_info(obj)
        self.assertEqual(info["remote_url"], "http://100.101.102.103:8766/?t=tok")

    def test_tailscale_detection_ignores_ordinary_addresses(self):
        addrs = [(socket.AF_INET, 0, 0, "", (ip, 0)) for ip in ("192.168.1.5", "10.0.0.2", "100.63.0.1")]
        with patch.object(server.socket, "getaddrinfo", return_value=addrs), \
             patch.object(server.os.path, "exists", return_value=False), \
             patch.object(server.shutil, "which", return_value=None):
            self.assertIsNone(server.tailscale_ip())
        addrs.append((socket.AF_INET, 0, 0, "", ("100.88.1.2", 0)))
        with patch.object(server.socket, "getaddrinfo", return_value=addrs):
            self.assertEqual(server.tailscale_ip(), "100.88.1.2")


if __name__ == "__main__":
    unittest.main()

