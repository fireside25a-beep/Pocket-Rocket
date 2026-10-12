import unittest

from neuro_inverse.flat32_accounting import (
    B, RECALLED_RAW, RECALLED_REGISTERED, RECALLED_TOTAL, estimate_flat32,
)


class Flat32AccountingTests(unittest.TestCase):
    def test_recalled_counts_and_formula(self):
        estimate = estimate_flat32(RECALLED_TOTAL, RECALLED_REGISTERED, dictionary_entries=256)
        self.assertEqual(B, 32)
        self.assertEqual(estimate.raw_blocks, RECALLED_RAW)
        self.assertEqual(estimate.bitmap_bytes, (RECALLED_TOTAL + 7) // 8)
        self.assertEqual(estimate.token_bytes, RECALLED_REGISTERED)
        self.assertEqual(estimate.raw_bytes, 32 * RECALLED_RAW)
        self.assertEqual(estimate.dictionary_bytes, 32 * 256)
        self.assertAlmostEqual(estimate.stream_ratio, 4.7446745365, places=9)
        self.assertAlmostEqual(estimate.dictionary_inclusive_ratio, 4.7379578029, places=9)
        self.assertGreaterEqual(estimate.break_even_total_blocks_stream, RECALLED_TOTAL)
        self.assertGreaterEqual(estimate.break_even_total_blocks_dictionary, RECALLED_TOTAL)

    def test_break_even_coverage_is_explicit(self):
        estimate = estimate_flat32(1000, 0, dictionary_entries=0, header_bytes=64, tail_bytes=0)
        self.assertGreater(estimate.break_even_registered_stream, 0)
        self.assertLessEqual(estimate.break_even_registered_stream, 1000)
        self.assertGreater(estimate.break_even_coverage_stream, 0.0)
        self.assertLess(estimate.break_even_coverage_stream, 1.0)

    def test_target_dictionary_ratio_is_not_explained_by_32d(self):
        estimate = estimate_flat32(
            RECALLED_TOTAL, RECALLED_REGISTERED, dictionary_entries=256,
            target_stream_ratio=4.744675, target_dictionary_ratio=1.602698,
        )
        self.assertLess(abs(estimate.target_stream_extra_bytes), 1.0)
        self.assertGreater(estimate.target_dictionary_unaccounted_bytes, 11_000_000)
        self.assertGreater(estimate.dictionary_inclusive_ratio, 4.7)

    def test_invalid_counts_rejected(self):
        with self.assertRaises(ValueError):
            estimate_flat32(0, 0)
        with self.assertRaises(ValueError):
            estimate_flat32(10, 11)
        with self.assertRaises(ValueError):
            estimate_flat32(10, 1, dictionary_entries=257)
        with self.assertRaises(ValueError):
            estimate_flat32(10, 1, header_bytes=-1)


if __name__ == "__main__":
    unittest.main()
