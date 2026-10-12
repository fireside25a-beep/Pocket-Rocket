import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from neuro_inverse.nprq import decode_tensor, encode_tensor, meta_from_dict, verify_tensor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pack_nprq_pocket import convert_package


def _record(meta: object, directory: str) -> dict:
    return {
        "directory": directory,
        "meta": {key: list(value) if isinstance(value, tuple) else value for key, value in meta.__dict__.items()},
    }


class PocketPackConverterTests(unittest.TestCase):
    def _package(self, root: Path) -> tuple[Path, object, bytes]:
        package = root / "source"
        pages = package / "pages" / "common"
        source = np.arange(96, dtype=np.float32).reshape(12, 8)
        meta = encode_tensor(source, pages, "common.weight", stages=2, block_size=16)
        (pages / "unreferenced.nprq").write_bytes(b"stray stage")
        (package / "config.json").write_text('{"model_type":"test"}\n', encoding="utf-8")
        (package / "NEUROROUTE_OFFICIAL_SOURCE_MANIFEST.json").write_text('{"resolved_commit":""}\n', encoding="utf-8")
        manifest = {
            "complete": True,
            "format": "neuroroute-deepseek-v4-flash-nprq-v2",
            "common_stages": 2,
            "ffn_stages": 2,
            "common": {"common.weight": _record(meta, "pages/common")},
            "layers": {},
        }
        manifest_path = package / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return package, meta, manifest_path.read_bytes()

    def test_conversion_preserves_decoded_tensor_and_manifest_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            source, original_meta, original_manifest_bytes = self._package(Path(temp))
            source_stage_bytes = {path: path.read_bytes() for path in (source / "pages" / "common").glob("*.nprq")}
            output = Path(temp) / "packed"
            converted = convert_package(source, output, chunk_size=31)
            self.assertEqual("pocket-pack-v1", converted["stage_container"])
            output_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            record = output_manifest["common"]["common.weight"]
            self.assertTrue(all(name.endswith(".prk") for name in record["meta"]["stage_files"]))
            packed_meta = meta_from_dict(record["meta"])
            verify_tensor(output / record["directory"], packed_meta)
            source_decoded = decode_tensor(source / "pages" / "common", original_meta, stage_count=2)
            packed_decoded = decode_tensor(output / record["directory"], packed_meta, stage_count=2)
            self.assertTrue(np.array_equal(source_decoded, packed_decoded))
            self.assertTrue((output / "config.json").is_file())
            self.assertTrue((output / "NEUROROUTE_OFFICIAL_SOURCE_MANIFEST.json").is_file())
            self.assertFalse(any(path.suffix == ".nprq" for path in output.rglob("*")))
            self.assertFalse(any(path.name == "unreferenced.nprq" for path in output.rglob("*")))
            self.assertEqual(original_manifest_bytes, (source / "manifest.json").read_bytes())
            self.assertEqual(source_stage_bytes, {path: path.read_bytes() for path in source_stage_bytes})

    def test_corrupt_source_stage_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source, meta, _ = self._package(Path(temp))
            stage = source / "pages" / "common" / meta.stage_files[0]
            stage.write_bytes(stage.read_bytes()[:-1] + b"x")
            with self.assertRaises(ValueError):
                convert_package(source, Path(temp) / "packed", chunk_size=31)


if __name__ == "__main__":
    unittest.main()
