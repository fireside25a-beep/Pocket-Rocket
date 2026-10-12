import unittest
from pathlib import Path

from neuro_inverse.ds4_runtime import (
    DEFAULT_RSS_CAP,
    DS4_REPOSITORY,
    DS4_REVISION,
    GateReport,
    PRODUCT_CONTEXT_TOKENS,
    PRODUCT_MAX_NEW_TOKENS,
    QUALIFICATION_LADDER,
    SMOKE_CONTEXT_TOKENS,
    SMOKE_OUTPUT_TOKENS,
    _origin_matches,
    choose_build_target,
    build_ds4_command,
    validate_token_profile,
)


class DS4RuntimeTests(unittest.TestCase):
    def test_runtime_identity_and_ram_cap_are_exact(self):
        self.assertEqual(DS4_REPOSITORY, "https://github.com/antirez/ds4.git")
        self.assertEqual(DS4_REVISION, "84cc882352757baf628a1776badf7cc54d584e28")
        self.assertEqual(DEFAULT_RSS_CAP, int(14.5 * 1024**3))
        self.assertEqual((SMOKE_CONTEXT_TOKENS, SMOKE_OUTPUT_TOKENS), (512, 16))
        self.assertEqual((PRODUCT_CONTEXT_TOKENS, PRODUCT_MAX_NEW_TOKENS), (8192, 2048))
        self.assertEqual(QUALIFICATION_LADDER,
                         ((512, 16), (2048, 128), (4096, 512), (8192, 2048)))

    def test_origin_normalization_is_narrow(self):
        self.assertTrue(_origin_matches("https://github.com/antirez/ds4.git\n"))
        self.assertTrue(_origin_matches("https://github.com/antirez/ds4/"))
        self.assertFalse(_origin_matches("https://example.invalid/antirez/ds4.git"))
        self.assertFalse(_origin_matches("git@github.com:antirez/ds4.git"))

    def test_build_target_and_report_are_fail_closed_types(self):
        self.assertEqual(choose_build_target("cpu"), "cpu")
        self.assertEqual(choose_build_target("auto"), "cpu")
        with self.assertRaises(ValueError):
            choose_build_target("fastest")
        with self.assertRaises(ValueError):
            choose_build_target("cuda-generic")
        report = GateReport("PASS", "a" * 64, DS4_REVISION, "b" * 64, "c" * 64,
                            0, 1, DEFAULT_RSS_CAP, 512, 16, "1GB", 1.25)
        self.assertEqual(report.as_dict()["peak_rss_bytes"], 1)

    def test_token_profiles_are_bounded_and_reserve_prompt_space(self):
        for context, output in QUALIFICATION_LADDER:
            validate_token_profile(context, output)
        for context, output in ((1, 1), (8193, 1), (8192, 2049), (512, 512),
                                (True, 1), (512, False)):
            with self.assertRaises(ValueError):
                validate_token_profile(context, output)

    def test_product_command_is_exact_cpu_ssd_8k_2k(self):
        command = build_ds4_command(
            Path("/runtime/ds4"), Path("/model.gguf"), Path("/prompt.txt"),
            system="Pocket Rocket", context_tokens=8192, output_tokens=2048,
        )
        self.assertEqual(command[command.index("--ctx") + 1], "8192")
        self.assertEqual(command[command.index("--tokens") + 1], "2048")
        self.assertIn("--ssd-streaming", command)
        self.assertEqual(command[command.index("--ssd-streaming-cache-experts") + 1], "1GB")
        self.assertNotIn("--cuda", command)


if __name__ == "__main__":
    unittest.main()
