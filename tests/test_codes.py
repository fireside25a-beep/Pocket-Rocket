import unittest

from neuro_inverse.codes import hamming256, parse_code, simhash256


class CodeTests(unittest.TestCase):
    def test_stable_and_sized(self):
        first = simhash256("deterministic code review")
        self.assertEqual(first, simhash256("deterministic code review"))
        self.assertEqual(len(first), 32)
        self.assertEqual(first, parse_code(first.hex()))

    def test_identity_distance(self):
        code = simhash256("same")
        self.assertEqual(hamming256(code, code), 0)

    def test_one_bit(self):
        left = bytes(32)
        right = bytes([1]) + bytes(31)
        self.assertEqual(hamming256(left, right), 1)


if __name__ == "__main__":
    unittest.main()

