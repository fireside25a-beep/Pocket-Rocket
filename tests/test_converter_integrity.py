import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from neuro_inverse.nprq import encode_tensor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_deepseek_v4_nprq import valid_record, verify_official_source


class ConverterIntegrityTests(unittest.TestCase):
    def test_official_source_inventory_is_rehashed(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            payload = source / "model.safetensors.index.json"
            payload.write_bytes(b"index")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            manifest = {
                "target": {
                    "model_id": "deepseek-ai/DeepSeek-V4-Flash",
                    "weight_revision": "b0c3326275d2207e25e42bc8ac0704952466b5bb",
                },
                "files": [{"path": payload.name, "size": payload.stat().st_size, "sha256": digest}],
            }
            manifest_path = source / "NEUROROUTE_OFFICIAL_SOURCE_MANIFEST.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            verify_official_source(source)
            payload.write_bytes(b"tampered")
            with self.assertRaises(SystemExit):
                verify_official_source(source)

    def test_resume_record_requires_hashes_and_expected_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            page = root / "pages"
            meta = encode_tensor(np.arange(32, dtype=np.float32), page, "weight", stages=2, block_size=16)
            record = {
                "directory": "pages",
                "meta": {key: list(value) if isinstance(value, tuple) else value for key, value in meta.__dict__.items()},
            }
            self.assertTrue(valid_record(record, root, "weight", 2, (32,)))
            (page / meta.stage_files[0]).write_bytes(b"corrupt")
            self.assertFalse(valid_record(record, root, "weight", 2, (32,)))


if __name__ == "__main__":
    unittest.main()
