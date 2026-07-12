import unittest
from types import SimpleNamespace
from unittest.mock import patch

import server
from server import (
    build_recite_check_payload,
    compare_recitation,
    is_allowed_upstream_url,
    is_public_static_path,
    normalize_text,
    rate_limit_retry_after,
)


class RecitationComparisonTests(unittest.TestCase):
    def test_punctuation_and_whitespace_are_ignored(self):
        result = compare_recitation("床前明月光，", "床前 明月光")
        self.assertTrue(result["passed"])
        self.assertEqual(result["accuracy"], 1.0)

    def test_reports_substitution_missing_and_extra_characters(self):
        substitution = compare_recitation("床前明月光", "床前名月光")
        self.assertFalse(substitution["passed"])
        self.assertEqual(substitution["substitutions"], [{"expected": "明", "spoken": "名"}])

        missing = compare_recitation("床前明月光", "床前月光")
        self.assertEqual(missing["missing_chars"], ["明"])

        extra = compare_recitation("床前明月光", "床前啊明月光")
        self.assertEqual(extra["extra_chars"], ["啊"])

    def test_homophone_is_not_silently_counted_as_exact(self):
        result = compare_recitation("床前明月光", "窗前明月光")
        self.assertFalse(result["passed"])
        self.assertEqual(result["phonetic_similarity"], 1.0)

    def test_normalization_handles_full_width_characters(self):
        self.assertEqual(normalize_text("Ａ，B。"), "AB")

    def test_low_quality_input_does_not_trigger_order_error(self):
        work = SimpleNamespace(title="测试诗", author="佚名")
        pages = [{"lines": ["床前明月光", "举头望明月"]}]
        with patch("server.extract_recite_pages", return_value=(work, pages)):
            result = build_recite_check_payload("测试诗", "", 0, 0, "啊", source="manual")
        self.assertEqual(result["status"], "partial_fail")
        self.assertEqual(result["matched_line_index"], 0)

    def test_adjacent_exact_line_still_reports_order_error(self):
        work = SimpleNamespace(title="测试诗", author="佚名")
        pages = [{"lines": ["床前明月光", "举头望明月"]}]
        with patch("server.extract_recite_pages", return_value=(work, pages)):
            result = build_recite_check_payload("测试诗", "", 0, 0, "举头望明月", source="manual")
        self.assertEqual(result["status"], "order_error")
        self.assertEqual(result["matched_line_index"], 1)

    def test_speech_homophone_is_flagged_for_confirmation(self):
        work = SimpleNamespace(title="测试诗", author="佚名")
        pages = [{"lines": ["床前明月光"]}]
        with patch("server.extract_recite_pages", return_value=(work, pages)):
            result = build_recite_check_payload("测试诗", "", 0, 0, "窗前明月光", source="speech")
        self.assertEqual(result["status"], "speech_uncertain")
        self.assertFalse(result["passed"])


class StaticFileAllowlistTests(unittest.TestCase):
    def test_public_frontend_files_are_allowed(self):
        self.assertTrue(is_public_static_path("/index.html"))
        self.assertTrue(is_public_static_path("/assets/home-cover.png"))

    def test_repository_and_source_files_are_blocked(self):
        self.assertFalse(is_public_static_path("/.git/config"))
        self.assertFalse(is_public_static_path("/server.py"))
        self.assertFalse(is_public_static_path("/textbook_knowledge_base.json"))
        self.assertFalse(is_public_static_path("/assets/../server.py"))


class SecurityGuardTests(unittest.TestCase):
    def setUp(self):
        with server.rate_limit_lock:
            server.rate_limit_windows.clear()
        with server.verified_human_tokens_lock:
            server.verified_human_tokens.clear()

    def test_rate_limit_rejects_excess_requests(self):
        self.assertEqual(rate_limit_retry_after("test", "198.51.100.7", 2, 60), 0)
        self.assertEqual(rate_limit_retry_after("test", "198.51.100.7", 2, 60), 0)
        self.assertGreater(rate_limit_retry_after("test", "198.51.100.7", 2, 60), 0)

    def test_verification_token_store_is_bounded(self):
        with patch("server.MAX_VERIFIED_HUMAN_TOKENS", 2):
            server.issue_human_verification_token()
            server.issue_human_verification_token()
            server.issue_human_verification_token()
        self.assertLessEqual(len(server.verified_human_tokens), 2)

    def test_upstream_requests_are_https_and_allowlisted(self):
        self.assertTrue(is_allowed_upstream_url("https://www.guwendao.net/search.aspx?value=%E6%9D%8E%E7%99%BD"))
        self.assertFalse(is_allowed_upstream_url("http://www.guwendao.net/search.aspx"))
        self.assertFalse(is_allowed_upstream_url("https://127.0.0.1/admin"))


if __name__ == "__main__":
    unittest.main()
