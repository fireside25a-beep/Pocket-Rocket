import tempfile
import unittest
from pathlib import Path

from neuro_inverse.model_target import DEEPSEEK_V4_FLASH, verify_weight_file


class ModelTargetTests(unittest.TestCase):
    def test_target_contract_is_pinned(self):
        DEEPSEEK_V4_FLASH.validate()
        self.assertEqual(DEEPSEEK_V4_FLASH.routed_experts, 256)
        self.assertEqual(DEEPSEEK_V4_FLASH.active_experts, 6)
        self.assertEqual(DEEPSEEK_V4_FLASH.layers, 43)

    def test_wrong_file_fails_before_hash_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / DEEPSEEK_V4_FLASH.weight_filename
            path.write_bytes(b"GGUF")
            with self.assertRaises(ValueError):
                verify_weight_file(path)

    def test_wrong_name_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "alternate.gguf"
            path.write_bytes(b"GGUF")
            with self.assertRaises(ValueError):
                verify_weight_file(path)


if __name__ == "__main__":
    unittest.main()
