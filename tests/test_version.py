from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

import neuro_inverse


class VersionTests(unittest.TestCase):
    def test_runtime_and_distribution_versions_match(self) -> None:
        project = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], neuro_inverse.__version__)
        self.assertEqual("0.4.2", neuro_inverse.__version__)


if __name__ == "__main__":
    unittest.main()
