import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from neuro_inverse.binary32 import (
    CANONICAL_NAN,
    MAX_FINITE,
    MIN_NORMAL,
    MIN_SUBNORMAL,
    add_bits,
    divide_bits,
    dot_product_bits,
    evaluate_candidate,
    evaluate_unary_candidate,
    multiply_bits,
    sqrt_bits,
)
from neuro_inverse.binary32_vectors import (
    DEFAULT_RANDOM_COUNT,
    DEFAULT_SEED,
    EDGE_CASES,
    UNARY_EDGE_CASES,
    generate_vectors,
    serialize_vectors,
    write_vectors,
)


VECTOR_PATH = Path(__file__).parent / "data" / "binary32_vectors.json"
VECTOR_SHA256 = "3413975bda7eb16c1d9a006e3ce379e056f7bb1b624eed0838ca54e47b0534ce"


class Binary32Tests(unittest.TestCase):
    def test_stable_vector_file_and_exact_reference_results(self):
        data = VECTOR_PATH.read_bytes()
        self.assertEqual(VECTOR_SHA256, hashlib.sha256(data).hexdigest())
        payload = json.loads(data)
        self.assertEqual("neuro-inverse-binary32-conformance-v2", payload["format"])
        self.assertEqual(DEFAULT_SEED, payload["seed"])
        self.assertEqual(DEFAULT_RANDOM_COUNT, payload["random_count"])
        self.assertEqual(len(EDGE_CASES) + len(UNARY_EDGE_CASES) + DEFAULT_RANDOM_COUNT, len(payload["vectors"]))
        operations = {"add": add_bits, "multiply": multiply_bits, "divide": divide_bits, "sqrt": sqrt_bits}
        for vector in payload["vectors"]:
            left = int(vector["left"], 16)
            expected = int(vector["expected"], 16)
            if vector["operation"] == "sqrt":
                actual = operations[vector["operation"]](left)
            else:
                right = int(vector["right"], 16)
                actual = operations[vector["operation"]](left, right)
            self.assertEqual(expected, actual, vector["label"])

        regenerated = serialize_vectors(generate_vectors(seed=DEFAULT_SEED, random_count=DEFAULT_RANDOM_COUNT))
        self.assertEqual(data, regenerated)

    def test_edge_case_labels_cover_required_ieee_branches(self):
        labels = {vector["label"] for vector in generate_vectors(random_count=0)["vectors"]}
        for required in {
            "nan_payload", "invalid_infinity", "invalid_infinity_zero", "signed_zero",
            "max_finite_overflow", "min_normal_subnormal_boundary", "min_normal_to_subnormal",
            "min_subnormal_halfway_to_zero", "one_plus_half_ulp_tie_even",
            "one_plus_three_half_ulp_tie_even",
            "division_invalid_infinity", "division_min_subnormal_halfway",
            "sqrt_negative_invalid", "sqrt_min_subnormal",
        }:
            self.assertIn(required, labels)
        self.assertEqual(CANONICAL_NAN, add_bits(0x7FA00001, 0x3F800000))
        self.assertEqual(CANONICAL_NAN, multiply_bits(0x7F800000, 0x00000000))
        self.assertEqual(0x7F800000, add_bits(MAX_FINITE, MAX_FINITE))
        self.assertEqual(MIN_SUBNORMAL, add_bits(MIN_NORMAL, 0x807FFFFF))
        self.assertEqual(0x3EAAAAAB, divide_bits(0x3F800000, 0x40400000))
        self.assertEqual(0x20000000, sqrt_bits(MIN_NORMAL))
        self.assertEqual(0x7FC00000, sqrt_bits(0xBF800000))

    def test_candidate_acceptance_and_exact_fallback(self):
        exact = evaluate_candidate("add", 0x3F800000, 0x3F800000, add_bits)
        self.assertTrue(exact.hardware_accepted)
        self.assertFalse(exact.mismatch)
        self.assertEqual(0x40000000, exact.result_bits)

        mismatch = evaluate_candidate("add", 0x3F800000, 0x3F800000, lambda _a, _b: 0)
        self.assertFalse(mismatch.hardware_accepted)
        self.assertTrue(mismatch.mismatch)
        self.assertEqual(mismatch.reference_bits, mismatch.result_bits)
        self.assertEqual(0, mismatch.candidate_bits)

        raised = evaluate_candidate("multiply", 0x3F800000, 0x3F800000, lambda _a, _b: 1 / 0)
        self.assertFalse(raised.hardware_accepted)
        self.assertTrue(raised.mismatch)
        self.assertIsNone(raised.candidate_bits)
        self.assertEqual(0x3F800000, raised.result_bits)

        no_candidate = evaluate_candidate("multiply", 0x00000000, 0x80000000, None)
        self.assertFalse(no_candidate.hardware_accepted)
        self.assertFalse(no_candidate.mismatch)
        self.assertEqual(0x80000000, no_candidate.result_bits)

        division = evaluate_candidate("divide", 0x3F800000, 0x40400000, divide_bits)
        self.assertTrue(division.hardware_accepted)
        self.assertEqual(0x3EAAAAAB, division.result_bits)

        sqrt = evaluate_unary_candidate("sqrt", 0x40000000, sqrt_bits)
        self.assertTrue(sqrt.hardware_accepted)
        self.assertEqual(0x3FB504F3, sqrt.result_bits)
        bad_sqrt = evaluate_unary_candidate("sqrt", 0x40000000, lambda _value: 0)
        self.assertTrue(bad_sqrt.mismatch)
        self.assertEqual(bad_sqrt.reference_bits, bad_sqrt.result_bits)

    def test_candidate_bad_bits_and_inputs_are_rejected_to_fallback(self):
        result = evaluate_candidate("add", 0x3F800000, 0x3F800000, lambda _a, _b: 1 << 40)
        self.assertTrue(result.mismatch)
        self.assertIsNone(result.candidate_bits)
        with self.assertRaises(ValueError):
            add_bits(-1, 0)
        with self.assertRaises(ValueError):
            multiply_bits(0, 1 << 32)
        with self.assertRaises(ValueError):
            evaluate_candidate("mod", 0, 0, None)  # type: ignore[arg-type]

    def test_dot_product_order_is_explicit_and_pairwise_is_distinct(self):
        left = [0x3F800000, 0x3F800000, 0x3F800000]
        right = [0x3F800000, 0x33800000, 0xB3800000]
        self.assertEqual(0x3F7FFFFF, dot_product_bits(left, right))
        self.assertEqual(0x3F7FFFFF, dot_product_bits(left, right, pairwise=True))
        self.assertEqual(0, dot_product_bits([], []))
        with self.assertRaises(ValueError):
            dot_product_bits([0], [])

        # Rounded products/sums make accumulation order observable.
        terms_left = [0x3F800000] * 4
        terms_right = [0x3F800000, 0x33800000, 0x33800000, 0x33800000]
        left_to_right = dot_product_bits(terms_left, terms_right)
        balanced = dot_product_bits(terms_left, terms_right, pairwise=True)
        self.assertNotEqual(left_to_right, balanced)

    def test_generator_writes_identical_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "vectors.json"
            data = write_vectors(path)
            self.assertEqual(data, path.read_bytes())
            self.assertEqual(VECTOR_SHA256, hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
