import unittest

from neuro_inverse.contracts import Contract


class ContractTests(unittest.TestCase):
    def test_accept_and_reject(self):
        contract = Contract(max_output_chars=20, forbidden_fragments=("secret",), required_fragments=("ok",))
        self.assertTrue(contract.verify("OK result")[0])
        accepted, failures = contract.verify("secret")
        self.assertFalse(accepted)
        self.assertIn("output.forbidden:secret", failures)
        self.assertIn("output.missing:ok", failures)


if __name__ == "__main__":
    unittest.main()

