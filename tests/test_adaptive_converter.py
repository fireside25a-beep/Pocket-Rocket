import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

from neuro_inverse.nprq import decode_tensor, encode_tensor, meta_from_dict, verify_tensor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pack_nprq_adaptive import convert_package
from pack_nprq_release import main as pack_release_main


def _record(meta: object, directory: str) -> dict:
    return {
        "directory": directory,
        "meta": {key: list(value) if isinstance(value, tuple) else value for key, value in meta.__dict__.items()},
    }


class AdaptiveConverterTests(unittest.TestCase):
    def _package(self, root: Path) -> tuple[Path, object, bytes]:
        package = root / "source"
        pages = package / "pages" / "common"
        source = np.zeros((4096,), dtype=np.float32)
        meta = encode_tensor(source, pages, "common.weight", stages=2, block_size=256)
        manifest = {
            "complete": True,
            "common_stages": 2,
            "ffn_stages": 2,
            "common": {"common.weight": _record(meta, "pages/common")},
            "layers": {},
        }
        (package / "config.json").write_text('{"model_type":"test"}\n', encoding="utf-8")
        (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return package, meta, (package / "manifest.json").read_bytes()

    def test_flat32_only_package_executes_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            source, original_meta, manifest_bytes = self._package(Path(temp))
            output = Path(temp) / "flat"
            converted = convert_package(source, output, codecs=("flat32",), chunk_size=31)
            decision = converted["stage_container_decisions"]["pages/common"]
            self.assertEqual("flat32", decision["selected"])
            record = converted["common"]["common.weight"]
            self.assertTrue(all(name.endswith(".f32") for name in record["meta"]["stage_files"]))
            self.assertTrue((output / "pages/common/_flat32.dict").is_file())
            converted_meta = meta_from_dict(record["meta"])
            verify_tensor(output / record["directory"], converted_meta)
            expected = decode_tensor(source / "pages/common", original_meta)
            actual = decode_tensor(output / record["directory"], converted_meta)
            self.assertTrue(np.array_equal(expected, actual))
            self.assertEqual(manifest_bytes, (source / "manifest.json").read_bytes())
            releases = Path(temp) / "releases"
            old_argv = sys.argv
            try:
                sys.argv = ["pack_nprq_release.py", str(output), "--output", str(releases)]
                self.assertEqual(0, pack_release_main())
            finally:
                sys.argv = old_argv
            with zipfile.ZipFile(releases / "DeepSeek-V4-Flash-NeuroRoute-NPRQ-base-s0.zip") as archive:
                names = set(archive.namelist())
                self.assertTrue(any(name.endswith(".s0.f32") for name in names))
                self.assertFalse(any(name.endswith(".s1.f32") for name in names))
                self.assertIn("pages/common/_flat32.dict", names)

    def test_default_selects_measured_minimum_and_rejects_bad_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            source, _meta, _manifest = self._package(Path(temp))
            output = Path(temp) / "adaptive"
            converted = convert_package(source, output, chunk_size=31)
            decision = converted["stage_container_decisions"]["pages/common"]
            self.assertEqual(min(decision["candidates"].values()), decision["stored_bytes"])
            self.assertLessEqual(decision["stored_bytes"], decision["raw_bytes"])
            with self.assertRaises(ValueError):
                convert_package(source, Path(temp) / "bad", codecs=("unknown",))

    def test_corrupt_source_is_rejected_before_conversion(self):
        with tempfile.TemporaryDirectory() as temp:
            source, meta, _manifest = self._package(Path(temp))
            stage = source / "pages/common" / meta.stage_files[0]
            stage.write_bytes(stage.read_bytes()[:-1] + b"x")
            with self.assertRaises(ValueError):
                convert_package(source, Path(temp) / "adaptive")


if __name__ == "__main__":
    unittest.main()
