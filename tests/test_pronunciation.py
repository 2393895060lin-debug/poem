import unittest
from types import SimpleNamespace
from unittest.mock import patch

import server


def pinyin_for(text, title=""):
    return [item["pinyin"] for item in server.tokens_for_text(text, title)]


class PronunciationOverrideTests(unittest.TestCase):
    def test_tengwang_pavilion_work_override(self):
        text = "临帝子之长洲"
        result = pinyin_for(text, "滕王阁序")
        self.assertEqual(result[text.index("长")], "cháng")

    def test_lanting_work_override_uses_correct_title(self):
        text = "少长咸集"
        result = pinyin_for(text, "兰亭集序")
        self.assertEqual(result[text.index("长")], "zhǎng")

    def test_global_classical_phrase_overrides(self):
        soup = pinyin_for("浩浩汤汤")
        toast = pinyin_for("将进酒，杯莫停")
        self.assertEqual(soup, ["hào", "hào", "shāng", "shāng"])
        self.assertEqual(toast[0], "qiāng")

    def test_unrelated_polyphonic_phrases_keep_expected_readings(self):
        cases = {
            "长大成人": "zhǎng",
            "万里长江": "cháng",
            "尊敬师长": "zhǎng",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                index = text.index("长")
                self.assertEqual(pinyin_for(text)[index], expected)

    def test_repeated_phrase_is_overridden_every_time(self):
        text = "浩浩汤汤，浩浩汤汤"
        result = pinyin_for(text)
        starts = [0, text.index("浩浩汤汤", 1)]
        for start in starts:
            self.assertEqual(result[start:start + 4], ["hào", "hào", "shāng", "shāng"])

    def test_work_rule_does_not_leak_to_other_titles(self):
        text = "临帝子之长洲"
        baseline = [[f"base-{index}"] for index, _char in enumerate(text)]
        with patch("server.pinyin", return_value=baseline):
            result = pinyin_for(text, "其他作品")
        self.assertEqual(result[text.index("长")], f"base-{text.index('长')}")

    def test_automatic_pinyin_is_unchanged_without_matching_rule(self):
        text = "不在覆盖表"
        baseline = [[f"base-{index}"] for index, _char in enumerate(text)]
        with patch("server.pinyin", return_value=baseline):
            result = pinyin_for(text, "测试作品")
        self.assertEqual(result, [item[0] for item in baseline])

    def test_scope_priority_and_longest_match_are_deterministic(self):
        text = "长洲长"
        overrides = {
            "global": {
                "长": ["global-short"],
                "长洲": ["global-long", "global-zhou"],
            },
            "works": {
                "测试作品": {
                    "长": ["work-short"],
                }
            },
        }
        baseline = [[f"base-{index}"] for index, _char in enumerate(text)]
        with patch.object(server, "PRONUNCIATION_OVERRIDES", overrides), patch("server.pinyin", return_value=baseline):
            global_result = pinyin_for(text)
            work_result = pinyin_for(text, "测试作品")
        self.assertEqual(global_result, ["global-long", "global-zhou", "global-short"])
        self.assertEqual(work_result, ["work-short", "base-1", "work-short"])

    def test_invalid_pronunciation_count_is_skipped(self):
        raw = {
            "global": {"长洲": ["cháng"]},
            "works": {},
        }
        with self.assertWarnsRegex(RuntimeWarning, "拼音数量"):
            normalized = server.normalize_pronunciation_overrides(raw, "test")
        self.assertNotIn("长洲", normalized["global"])

    def test_punctuation_and_note_positions_stay_aligned(self):
        text = "临帝子之长洲，"
        lines = server.build_annotated_lines(
            [text],
            [{"term": "长洲", "index": 7}],
            "滕王阁序",
        )
        self.assertEqual("".join(item["char"] for item in lines[0]), text)
        self.assertEqual(len(lines[0]), len(text))
        self.assertEqual(lines[0][text.index("长")]["pinyin"], "cháng")
        self.assertEqual(lines[0][text.index("洲")]["noteNumbers"], [7])
        self.assertEqual(lines[0][-1]["char"], "，")

    def test_build_payload_contains_corrected_line_tokens(self):
        result = SimpleNamespace(
            title="滕王阁序",
            author="王勃",
            dynasty="唐",
            content=["临帝子之长洲"],
            source="测试正文",
        )
        with (
            patch("server.resolve_lookup_result", return_value=("滕王阁序", result)),
            patch("server.database_entry_for", return_value={}),
            patch("server.get_auto_supplement_entry", return_value={}),
            patch("server.load_external_translation", return_value=[]),
            patch("server.author_views", return_value=(["王", "勃"], ["wáng", "bó"])),
            patch("server.schedule_enrichment", return_value={"status": "not_needed"}),
        ):
            payload = server.build_payload("滕王阁序", "王勃")

        line = payload["lines"][0]
        text = "".join(item["char"] for item in line)
        self.assertEqual(text, "临帝子之长洲")
        self.assertEqual(line[text.index("长")]["pinyin"], "cháng")


if __name__ == "__main__":
    unittest.main()
