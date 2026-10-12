import tempfile
import unittest
from pathlib import Path

from neuro_inverse.aegis_boundary import (
    AegisBoundary,
    AegisBoundaryError,
    AegisUnavailable,
    InputKind,
    classify_input,
    discover_aegis,
    require_aegis_source,
)
from neuro_inverse.pocket_pack import pack


class AegisBoundaryTests(unittest.TestCase):
    def test_empty_explicit_toolchain_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            capabilities = discover_aegis(toolchain_root=Path(temp) / "not-installed")
        self.assertFalse(capabilities.available)
        self.assertEqual(
            {"dxlc", "dxscc", "dxasm", "dxvm", "dxaudit"},
            set(capabilities.missing),
        )
        with self.assertRaises(AegisUnavailable):
            capabilities.require_stage("dxb3")

    def test_classification_does_not_treat_weights_or_storage_as_source(self):
        self.assertEqual(InputKind.DXL_SOURCE, classify_input("program.dxl"))
        self.assertEqual(InputKind.DXS_SOURCE, classify_input("program.dxs"))
        self.assertEqual(InputKind.DXASM_SOURCE, classify_input("program.dxasm"))
        self.assertEqual(InputKind.MODEL_WEIGHTS, classify_input("model.safetensors"))
        self.assertEqual(InputKind.POCKET_ROCKET_STORAGE, classify_input("pages.pkr"))
        self.assertEqual(InputKind.FLAT32_STORAGE, classify_input("pages.flat32"))
        self.assertEqual(InputKind.UNKNOWN, classify_input("program.txt"))

    def test_source_gate_rejects_model_weights_storage_and_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "program.dxs"
            source.write_text("// source is caller-owned\n", encoding="utf-8")
            self.assertEqual(source, require_aegis_source(source, expected=InputKind.DXS_SOURCE))
            for name in ("model.safetensors", "pages.flat32", "pages.pkr", "program.txt"):
                candidate = root / name
                candidate.write_bytes(b"not source")
                with self.assertRaises(AegisBoundaryError):
                    require_aegis_source(candidate)
            with self.assertRaises(AegisBoundaryError):
                require_aegis_source(source, expected=InputKind.DXL_SOURCE)

    def test_pocket_rocket_is_verified_storage_only_and_never_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "stage.pkr"
            source = b"lossless stage payload\x00" * 11
            pack(source, package, chunk_size=13)
            boundary = AegisBoundary(discover_aegis(toolchain_root=root / "absent"))
            inspection = boundary.inspect_pocket_rocket(package)
            self.assertTrue(inspection.verified)
            self.assertTrue(inspection.storage_only)
            self.assertTrue(inspection.interpretation_forbidden)
            self.assertEqual(len(source), inspection.source_bytes)
            self.assertEqual(package.stat().st_size, inspection.container_bytes)
            with self.assertRaises(AegisBoundaryError):
                boundary.run_stage("dxb3", (str(package),))

    def test_flat32_is_hashed_storage_only_without_decoding(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "weights.flat32"
            raw = b"Flat32 bytes are storage, not Aegis source."
            path.write_bytes(raw)
            boundary = AegisBoundary(discover_aegis(toolchain_root=Path(temp) / "absent"))
            inspection = boundary.inspect_flat32_storage(path)
            self.assertEqual(len(raw), inspection.source_bytes)
            self.assertEqual(len(raw), inspection.container_bytes)
            self.assertFalse(inspection.verified)
            self.assertTrue(inspection.hash_computed)
            self.assertTrue(inspection.storage_only)
            self.assertTrue(inspection.interpretation_forbidden)
            with self.assertRaises(AegisBoundaryError):
                boundary.inspect_pocket_rocket(path)

    def test_run_stage_rejects_storage_before_capability_lookup(self):
        boundary = AegisBoundary(discover_aegis(toolchain_root=Path("/definitely/absent")))
        with self.assertRaises(AegisBoundaryError):
            boundary.run_stage("dxb3", ("pages.flat32",))

    def test_storage_inspection_rejects_invalid_container(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.pkr"
            path.write_bytes(b"not a Pocket Rocket container")
            boundary = AegisBoundary(discover_aegis(toolchain_root=Path(temp) / "absent"))
            with self.assertRaises(AegisBoundaryError):
                boundary.inspect_pocket_rocket(path)


if __name__ == "__main__":
    unittest.main()
