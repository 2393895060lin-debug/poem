import unittest
from unittest.mock import patch

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
        self.assertFalse(server.is_allowed_upstream_url("http://www.guwendao.net/search.aspx"))
        self.assertFalse(server.is_allowed_upstream_url("https://127.0.0.1/admin"))


if __name__ == "__main__":
    unittest.main()
