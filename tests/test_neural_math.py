import unittest

from neuro_inverse.binary32 import CANONICAL_NAN, NEGATIVE_INFINITY, POSITIVE_INFINITY
from neuro_inverse.neural_math import (
    DEFAULT_EPSILON,
    attention_bits,
    exp_bits,
    rmsnorm_bits,
    sigmoid_bits,
    silu_bits,
    softmax_bits,
)


class NeuralMathTests(unittest.TestCase):
    def test_exp_and_silu_are_fixed_and_cover_nonfinite_edges(self):
        self.assertEqual(0x3F800000, exp_bits(0x00000000))
        self.assertEqual(0x3F800000, exp_bits(0x80000000))
        self.assertEqual(POSITIVE_INFINITY, exp_bits(POSITIVE_INFINITY))
        self.assertEqual(0x00000000, exp_bits(NEGATIVE_INFINITY))
        self.assertEqual(CANONICAL_NAN, exp_bits(CANONICAL_NAN))
        self.assertEqual(0x3F000000, sigmoid_bits(0x00000000))
        self.assertEqual(0x80000000, silu_bits(NEGATIVE_INFINITY))
        self.assertEqual(POSITIVE_INFINITY, silu_bits(POSITIVE_INFINITY))
        self.assertEqual(CANONICAL_NAN, silu_bits(CANONICAL_NAN))
        # Repeated evaluation has no dependency on host libm or execution order.
        self.assertEqual(exp_bits(0x3F800000), exp_bits(0x3F800000))
        self.assertEqual(silu_bits(0xBF800000), silu_bits(0xBF800000))

    def test_rmsnorm_order_shape_and_signed_zero(self):
        values = [0x3F800000, 0x40000000, 0x80000000]
        result = rmsnorm_bits(values, [0x3F800000] * 3, epsilon=DEFAULT_EPSILON)
        self.assertEqual(3, len(result))
        self.assertEqual(0x80000000, result[2])
        self.assertEqual(result, rmsnorm_bits(values, [0x3F800000] * 3))
        with self.assertRaises(ValueError):
            rmsnorm_bits([])
        with self.assertRaises(ValueError):
            rmsnorm_bits(values, [0x3F800000])
        with self.assertRaises(ValueError):
            rmsnorm_bits(values, epsilon=POSITIVE_INFINITY)

    def test_softmax_mask_nonfinite_and_stable_order(self):
        row = softmax_bits([0x3F800000, 0x40000000])
        self.assertEqual([0x3E89B2B1, 0x3F3B26A8], row)
        self.assertEqual([0x3F800000, 0], softmax_bits([0x3F800000, 0x40000000], [True, False]))
        self.assertEqual([0, 0], softmax_bits([0x3F800000, 0x40000000], [False, False]))
        self.assertEqual([0x3F000000, 0x3F000000], softmax_bits([POSITIVE_INFINITY, POSITIVE_INFINITY]))
        self.assertEqual([0x3F800000, 0], softmax_bits([POSITIVE_INFINITY, 0x3F800000]))
        self.assertEqual([0x3F000000, 0x3F000000], softmax_bits([NEGATIVE_INFINITY, NEGATIVE_INFINITY]))
        self.assertEqual([CANONICAL_NAN, CANONICAL_NAN], softmax_bits([CANONICAL_NAN, 0x3F800000]))
        self.assertEqual([CANONICAL_NAN, 0], softmax_bits([CANONICAL_NAN, 0x3F800000], [True, False]))
        # Exact ties use the binary32 tie-to-even primitive in every sum.
        self.assertEqual([0x3F000000, 0x3F000000], softmax_bits([0, 0]))

    def test_attention_fixed_dot_order_and_mask(self):
        query = [0x3F800000]
        keys = [[0x3F800000], [0x40000000]]
        values = [[0x3F800000, 0x40000000], [0x40400000, 0x40800000]]
        self.assertEqual([0x3F800000, 0x40000000], attention_bits(query, keys, values, mask=[True, False], scale=False))
        self.assertEqual(
            attention_bits(query, keys, values, scale=True),
            attention_bits(query, keys, values, scale=True),
        )
        with self.assertRaises(ValueError):
            attention_bits([], keys, values)
        with self.assertRaises(ValueError):
            attention_bits(query, keys, values, mask=[True])


if __name__ == "__main__":
    unittest.main()
