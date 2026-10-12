from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from neuro_inverse.cli import main


class TernaryCliTests(unittest.TestCase):
    def invoke(self, arguments: list[str], *, root: Path | None = None) -> dict[str, object]:
        output = io.StringIO()
        environment = {} if root is None else {"NEURO_ROOT": str(root)}
        with patch.dict(os.environ, environment, clear=False), contextlib.redirect_stdout(output):
            self.assertEqual(0, main(arguments))
        return json.loads(output.getvalue())

    def invoke_error(self, arguments: list[str]) -> str:
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(arguments)
        self.assertEqual(2, raised.exception.code)
        return error.getvalue()

    def test_dot_and_gate_are_machine_readable(self) -> None:
        dot = self.invoke(["ternary-dot", "--", "-0++", "+0+-"])
        self.assertEqual(-1, dot["dot"])
        gate = self.invoke([
            "decide", "--criterion", "safety:2:1", "--criterion", "quality:1:1:2:0",
            "--reject-below=-1:0", "--accept-at=1:0",
            "--model-root", "0" * 64, "--request-root", "1" * 64,
        ])
        self.assertEqual("accept", gate["status"])
        self.assertEqual(64, len(gate["certificate"]))

        score = self.invoke([
            "score", "--level", "low:1:0", "--level", "medium:2:0",
            "--level", "high:6:0", "--minimum-confidence", "1:3",
            "--model-root", "0" * 64, "--request-root", "1" * 64,
        ])
        self.assertEqual("accept", score["status"])
        self.assertEqual("high", score["level"])
        self.assertEqual({"numerator": 14, "denominator": 9}, score["expected_score"])
        self.assertEqual({"numerator": 4, "denominator": 9}, score["confidence"])

    def test_manifest_demand_read_and_static_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.gguf"
            source.write_bytes(b"GGUF" + b"abc123" * 30000)
            manifest = root / "model.pages.json"
            demand_store = root / "demand"
            static_store = root / "static"
            output = root / "slice.bin"
            made = self.invoke([
                "model-manifest", str(source), str(manifest), "--page-bytes", str(64 * 1024)
            ])
            analysis = self.invoke(["model-analyze", str(manifest), str(source)])
            self.assertEqual(made["model_root"], analysis["model_root"])
            self.assertEqual(made["pages"], analysis["pages"])
            self.assertEqual(64, len(analysis["decision_root"]))
            self.assertEqual(made["pages"], sum(analysis["codecs"].values()))
            attached = self.invoke([
                "model-import", str(manifest), str(source), str(demand_store), "--mode", "demand"
            ])
            self.assertEqual(made["model_root"], attached["model_root"])
            self.assertEqual(0, attached["materialized_pages"])
            read = self.invoke([
                "model-read", str(manifest), str(source), str(demand_store), "10", "1000", str(output)
            ])
            self.assertEqual(source.read_bytes()[10:1010], output.read_bytes())
            static = self.invoke([
                "model-import", str(manifest), str(source), str(static_store), "--mode", "static"
            ])
            self.assertEqual(made["model_root"], static["model_root"])
            self.assertEqual(static["total_pages"], static["materialized_pages"])
            self.assertEqual(1000, read["bytes"])

    def test_model_outputs_cannot_overwrite_inputs_or_enter_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.gguf"
            original = b"GGUF" + b"protected" * 10000
            source.write_bytes(original)
            manifest = root / "model.pages.json"
            store = root / "store"
            self.invoke([
                "model-manifest", str(source), str(manifest), "--page-bytes", str(64 * 1024)
            ])
            self.assertIn("protected input", self.invoke_error([
                "model-read", str(manifest), str(source), str(store), "0", "4", str(source)
            ]))
            self.assertEqual(original, source.read_bytes())
            manifest_before = manifest.read_bytes()
            self.assertIn("protected input", self.invoke_error([
                "model-read", str(manifest), str(source), str(store), "0", "4", str(manifest)
            ]))
            self.assertEqual(manifest_before, manifest.read_bytes())
            self.assertIn("model-page store", self.invoke_error([
                "model-read", str(manifest), str(source), str(store), "0", "4",
                str(store / "output.bin")
            ]))
            self.assertIn("protected input", self.invoke_error([
                "model-manifest", str(source), str(source), "--page-bytes", str(64 * 1024)
            ]))
            self.assertEqual(original, source.read_bytes())

    def test_route_decision_binds_local_router_to_certificate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"NEURO_ROOT": str(root)}, clear=False), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["init-store"]))
            result = self.invoke(
                ["route-decide", "review the parser", "--minimum-margin", "1"], root=root
            )
            self.assertIn(result["status_name"], {"accept", "abstain"})
            self.assertEqual(64, len(result["certificate"]))
            self.assertGreaterEqual(len(result["routes"]), 2)


if __name__ == "__main__":
    unittest.main()
