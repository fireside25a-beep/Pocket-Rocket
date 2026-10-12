"""Live Aegis-C2R translator regression; never replaces source with a mock."""
from __future__ import annotations
import shutil
import tempfile
import unittest
from pathlib import Path

from neuro_inverse.aegis_boundary import AegisBoundaryError
from neuro_inverse.aegis_c2r import AegisC2R

SRC = Path(__file__).resolve().parents[1] / "toolchains/aegis-c2r-0.1.0/tests"


@unittest.skipUnless(shutil.which("make") and shutil.which("cc"), "strict C compiler unavailable")
class C2RLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = AegisC2R()
        cls.tool.build()

    def test_positive_check_and_real_rust_translation(self):
        src = SRC / "positive/basic.c"
        self.tool.check(src)
        with tempfile.TemporaryDirectory() as root:
            a = self.tool.translate(src, Path(root) / "a")
            b = self.tool.translate(src, Path(root) / "b")
            self.assertEqual(a.rust_sha256, b.rust_sha256)
            self.assertEqual(a.proof_sha256, b.proof_sha256)
            rust = (Path(root) / "a/translation.rs").read_text()
            self.assertIn("#![forbid(unsafe_code)]", rust)
            self.assertIn("checked_add", rust)

    def test_negative_rejected(self):
        with self.assertRaises(AegisBoundaryError):
            self.tool.check(SRC / "negative/pointer.c")

    def test_storage_and_collision_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            other = Path(root) / "weights.gguf"
            other.write_bytes(b"GGUF")
            with self.assertRaises(AegisBoundaryError):
                self.tool.check(other)
            output = Path(root) / "nonempty"
            output.mkdir()
            (output / "keep").write_bytes(b"KEEP")
            with self.assertRaises(AegisBoundaryError):
                self.tool.translate(SRC / "positive/basic.c", output)
            self.assertEqual((output / "keep").read_bytes(), b"KEEP")


if __name__ == "__main__": unittest.main()
