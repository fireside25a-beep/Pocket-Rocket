"""Actual compiler, auditor, and VM integration tests; no simulated tools."""
from __future__ import annotations

import platform
import tempfile
import unittest
from pathlib import Path

from neuro_inverse.aegis_boundary import AegisBoundaryError
from neuro_inverse.aegis_runtime import AegisRuntime

SUITE = Path(__file__).resolve().parents[1] / "toolchains/aegis-language-suite-2.4.3"


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() == "x86_64", "shipped toolchain is Linux x86-64 only")
class AegisRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = AegisRuntime(timeout=40)
        cls.runtime.prepare()

    def test_real_dxl_native_compiler(self) -> None:
        source = SUITE / "examples/loops/dxl/native_counter.dxl"
        first = self.runtime.execute(source)
        second = self.runtime.execute(source)
        self.assertEqual(b"10\n", first.stdout)
        self.assertEqual(first.artifact_sha256, second.artifact_sha256)
        self.assertEqual("native-x86_64-linux", first.backend)
        self.assertFalse(first.audited)  # native ELF is NOT DXB3 audited

    def test_real_dxs_verified_vm(self) -> None:
        source = SUITE / "examples/loops/dxs/counter.dxs"
        first = self.runtime.execute(source)
        second = self.runtime.execute(source)
        self.assertEqual(b"10\n", first.stdout)
        self.assertTrue(first.audited)
        self.assertEqual(first.artifact_sha256, second.artifact_sha256)
        self.assertEqual(first.proof_sha256, second.proof_sha256)
        self.assertGreater(first.proof_bytes, 0)

    def test_real_dxasm_verified_vm(self) -> None:
        source = SUITE / "examples/loops/dxasm/counter.dxasm"
        first = self.runtime.execute(source)
        second = self.runtime.execute(source)
        self.assertEqual(b"10\n", first.stdout)
        self.assertTrue(first.audited)
        self.assertEqual(first.artifact_sha256, second.artifact_sha256)
        self.assertEqual(first.proof_sha256, second.proof_sha256)

    def test_reject_weights_storage_unknown_and_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            d = Path(dirname)
            for suffix in (".gguf", ".safetensors", ".bin", ".flat32", ".pkr", ".json"):
                f = d / ("payload" + suffix)
                f.write_bytes(b"42")
                with self.subTest(suffix=suffix), self.assertRaises(AegisBoundaryError):
                    self.runtime.execute(f)
            with self.assertRaises(FileNotFoundError):
                self.runtime.execute(d / "missing.dxl")

    def test_real_negative_corpus_rejected(self) -> None:
        source = SUITE / "tests/negative/unknown_name.dxl"
        with self.assertRaises(AegisBoundaryError):
            self.runtime.execute(source)

    def test_source_mutation_changes_output(self) -> None:
        source = (SUITE / "examples/loops/dxs/counter.dxs").read_text()
        # A source mutation must not be mistaken for an immutable canned result.
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / "changed.dxs"
            path.write_text(source.replace("10", "11", 1))
            base = self.runtime.execute(SUITE / "examples/loops/dxs/counter.dxs")
            altered = self.runtime.execute(path)
            self.assertNotEqual(base.artifact_sha256, altered.artifact_sha256)


if __name__ == "__main__":
    unittest.main()
