import http.client
import threading
import unittest
from unittest.mock import patch

import lookup_classical_text
import server


class StaticFileAllowlistTests(unittest.TestCase):
    def test_public_frontend_files_are_allowed(self):
        self.assertTrue(server.is_public_static_path("/index.html"))
        self.assertTrue(server.is_public_static_path("/assets/home-cover.png"))

    def test_repository_and_source_files_are_blocked(self):
        self.assertFalse(server.is_public_static_path("/.git/config"))
        self.assertFalse(server.is_public_static_path("/server.py"))
        self.assertFalse(server.is_public_static_path("/textbook_knowledge_base.json"))
        self.assertFalse(server.is_public_static_path("/assets/../server.py"))


class ResourceGuardTests(unittest.TestCase):
    def setUp(self):
        with server.rate_limit_lock:
            server.rate_limit_windows.clear()
        with server.verified_human_tokens_lock:
            server.verified_human_tokens.clear()

    def test_rate_limit_rejects_excess_requests(self):
        self.assertEqual(server.rate_limit_retry_after("test", "198.51.100.7", 2, 60), 0)
        self.assertEqual(server.rate_limit_retry_after("test", "198.51.100.7", 2, 60), 0)
        self.assertGreater(server.rate_limit_retry_after("test", "198.51.100.7", 2, 60), 0)

    def test_verification_token_store_is_bounded(self):
        with patch("server.MAX_VERIFIED_HUMAN_TOKENS", 2):
            server.issue_human_verification_token()
            server.issue_human_verification_token()
            server.issue_human_verification_token()
        self.assertLessEqual(len(server.verified_human_tokens), 2)

    def test_upstream_requests_are_https_and_allowlisted(self):
        self.assertTrue(server.is_allowed_upstream_url("https://www.guwendao.net/search.aspx?value=x"))
        self.assertTrue(server.is_allowed_upstream_url("https://poetry.palemoky.com/api/search?q=x"))
        self.assertFalse(server.is_allowed_upstream_url("http://www.guwendao.net/search.aspx"))
        self.assertFalse(server.is_allowed_upstream_url("https://127.0.0.1/admin"))
        self.assertTrue(lookup_classical_text.is_allowed_upstream_url(lookup_classical_text.GAOKAO_URL))
        self.assertFalse(lookup_classical_text.is_allowed_upstream_url("https://127.0.0.1/admin"))


class HttpServerGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = server.LimitedThreadingHTTPServer(("127.0.0.1", 0), server.AppHandler, max_workers=4)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        with server.rate_limit_lock:
            server.rate_limit_windows.clear()
        with server.verified_human_tokens_lock:
            server.verified_human_tokens.clear()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def test_source_git_head_and_encoded_traversal_are_blocked(self):
        self.assertEqual(self.request("GET", "/server.py")[0], 404)
        self.assertEqual(self.request("GET", "/.git/config")[0], 404)
        self.assertEqual(self.request("HEAD", "/server.py")[0], 404)
        self.assertEqual(self.request("GET", "/assets/%252e%252e/server.py")[0], 404)

    def test_redirect_and_security_headers_are_complete(self):
        status, headers, body = self.request("GET", "/reader.html")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("Content-Length"), "0")
        self.assertEqual(body, b"")
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("fonts.googleapis.com", headers.get("Content-Security-Policy", ""))
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_cross_site_post_body_limit_and_rate_limit(self):
        origin = f"http://{self.host}:{self.port}"
        self.assertEqual(self.request("POST", "/api/human-verify", headers={"Origin": "https://evil.example"})[0], 403)
        status, headers, _ = self.request("POST", "/api/human-verify", headers={"Origin": origin})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        oversized = b"{" + b"x" * server.MAX_JSON_BODY_BYTES + b"}"
        status, _, _ = self.request(
            "POST",
            "/api/recite/check",
            body=oversized,
            headers={"Origin": origin, "Cookie": cookie, "Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        with server.rate_limit_lock:
            server.rate_limit_windows.clear()
        statuses = [self.request("POST", "/api/human-verify", headers={"Origin": origin})[0] for _ in range(9)]
        self.assertEqual(statuses[-1], 429)


if __name__ == "__main__":
    unittest.main()
