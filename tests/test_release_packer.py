import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

from neuro_inverse.nprq import encode_tensor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pack_nprq_release import main as pack_main


class ReleasePackerTests(unittest.TestCase):
    def test_archives_only_manifest_referenced_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            pages = package / "pages" / "common"
            meta = encode_tensor(np.arange(32, dtype=np.float32), pages, "common.weight", stages=2, block_size=16)
            record = {
                "directory": "pages/common",
                "meta": {key: list(value) if isinstance(value, tuple) else value for key, value in meta.__dict__.items()},
            }
            (pages / "orphan.s0.nprq").write_bytes(b"orphan")
            (pages / "orphan.s1.nprq").write_bytes(b"orphan")
            manifest = {
                "complete": True,
                "common_stages": 2,
                "ffn_stages": 2,
                "common": {"common.weight": record},
                "layers": {},
            }
            package.mkdir(parents=True, exist_ok=True)
            (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "releases"
            old_argv = sys.argv
            try:
                sys.argv = ["pack_nprq_release.py", str(package), "--output", str(output)]
                self.assertEqual(0, pack_main())
            finally:
                sys.argv = old_argv
            with zipfile.ZipFile(output / "DeepSeek-V4-Flash-NeuroRoute-NPRQ-base-s0.zip") as archive:
                names = set(archive.namelist())
                self.assertIn("pages/common/" + meta.stage_files[0], names)
                self.assertNotIn("pages/common/" + meta.stage_files[1], names)
                self.assertNotIn("pages/common/orphan.s0.nprq", names)
                base_manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(1, base_manifest["common_stages"])
            with zipfile.ZipFile(output / "DeepSeek-V4-Flash-NeuroRoute-NPRQ-residual-s1plus.zip") as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("pages/common/" + meta.stage_files[1], names)
                self.assertNotIn("pages/common/orphan.s1.nprq", names)


if __name__ == "__main__":
    unittest.main()
