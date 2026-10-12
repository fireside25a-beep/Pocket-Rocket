from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from neuro_inverse.attest import create_receipt
from neuro_inverse.cli import main
from neuro_inverse.envelope import canonical_sha256
from neuro_inverse.nprq import encode_tensor
from neuro_inverse.nprq_verify import prove_monotone


class AttestationAndNPRQVerifyTests(unittest.TestCase):
    def test_decide_output_can_be_verified_and_attested(self) -> None:
        model_root = "a" * 64
        request_root = "b" * 64
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(0, main([
                "decide", "--criterion", "safety:1:0", "--reject-below", "0:0",
                "--accept-at", "1:0", "--model-root", model_root,
                "--request-root", request_root,
            ]))
        result = json.loads(stream.getvalue())
        self.assertEqual(result["certificate"], canonical_sha256(result["transcript"]))
        receipt = create_receipt(
            source_kind="decide", transcript=result["transcript"],
            certificate=result["certificate"], model_root=model_root,
            request_root=request_root, arithmetic_mode="integer_oracle",
        )
        self.assertTrue(receipt.as_dict()["source_certificate_verified"])
        tampered = dict(result["transcript"]); tampered["status"] = -1
        with self.assertRaises(ValueError):
            create_receipt(source_kind="decide", transcript=tampered,
                           certificate=result["certificate"], model_root=model_root,
                           request_root=request_root, arithmetic_mode="integer_oracle")

    def test_nprq_monotonicity_is_recomputed_from_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = np.linspace(-3.0, 3.0, 257, dtype=np.float32)
            source_path = root / "source.npy"
            np.save(source_path, source, allow_pickle=False)
            meta = encode_tensor(source, root, "proof", stages=3, block_size=64)
            proof = prove_monotone(root, meta, source_path)
            self.assertTrue(proof["monotone_non_increasing"])
            self.assertEqual(3, len(proof["sse"]))
            self.assertEqual(proof["certificate"], canonical_sha256({k: v for k, v in proof.items() if k != "certificate"}))

    def test_real_npz_ssm_checkpoint_comparison_is_connected(self) -> None:
        from neuro_inverse.ternary_ssm import load_diagonal_checkpoint, compare_checkpoint
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkpoint_path = root / "checkpoint.npz"
            input_path = root / "input.npy"
            np.savez(checkpoint_path, A=np.array([0.75, 0.1], dtype=np.float32),
                     B=np.array([0.9, -0.8], dtype=np.float32),
                     output_weight=np.array([1.0, 0.5], dtype=np.float32))
            np.save(input_path, np.array([[1, 2], [2, -1], [0, 1]], dtype=np.int32), allow_pickle=False)
            report = compare_checkpoint(load_diagonal_checkpoint(checkpoint_path),
                                        np.load(input_path, allow_pickle=False))
            self.assertEqual(2, report["hidden_dim"])
            self.assertEqual(3, report["tokens"])
            self.assertGreaterEqual(report["max_abs_divergence"], 0.0)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(0, main(["ssm-compare", str(checkpoint_path), str(input_path)]))
            self.assertEqual(report["checkpoint_sha256"], json.loads(stream.getvalue())["checkpoint_sha256"])


if __name__ == "__main__":
    unittest.main()
