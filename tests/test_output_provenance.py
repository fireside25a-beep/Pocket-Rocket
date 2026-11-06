"""Output-channel and receipt-identity regressions using real local processes."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from neuro_inverse.attest import create_receipt
from neuro_inverse.agent_fabric import FabricLimits, execute_recursive
from neuro_inverse.cli import main
from neuro_inverse.ds4_runtime import _execute_guarded
from neuro_inverse.envelope import canonical_sha256


class TransportOutputContract(unittest.TestCase):
    def execute(self, code):
        with tempfile.TemporaryDirectory() as folder:
            return _execute_guarded(
                [sys.executable, "-c", code], cwd=Path(folder),
                env=os.environ.copy(), rss_cap_bytes=256 * 1024 * 1024,
                timeout=3, term_grace_seconds=0.2,
            )

    def test_stdout_answer_control(self):
        text, _, _ = self.execute("print('answer-42', flush=True)")
        self.assertEqual(text, "answer-42\n")

    def test_diagnostics_must_not_be_returned_as_answer(self):
        text, _, _ = self.execute(
            "import sys; print('diagnostic-only', file=sys.stderr, flush=True); "
            "print('answer-42', flush=True)"
        )
        self.assertEqual(text, "answer-42\n")

    def test_stderr_only_must_not_count_as_inference_output(self):
        with self.assertRaisesRegex(RuntimeError, "no inference output"):
            self.execute("import sys; print('diagnostic-only', file=sys.stderr, flush=True)")

    def test_nonzero_exit_control(self):
        with self.assertRaisesRegex(RuntimeError, r"inference failed \(7\)"):
            self.execute("print('answer-42'); raise SystemExit(7)")

    def test_large_stderr_is_drained_without_answer_contamination(self):
        text, _, _ = self.execute(
            "import sys; sys.stderr.write('x' * 1048576); "
            "sys.stderr.flush(); print('answer-42', flush=True)"
        )
        self.assertEqual(len(text), len("answer-42\n"))
        self.assertEqual(text, "answer-42\n")

    def test_failure_preserves_bounded_diagnostic_tail(self):
        with self.assertRaises(RuntimeError) as caught:
            self.execute(
                "import sys; sys.stderr.write('x' * 1048576 + 'diagnostic-tail'); "
                "raise SystemExit(7)"
            )
        self.assertIn("diagnostic-tail", str(caught.exception))
        self.assertLessEqual(len(str(caught.exception)), 12050)

    def test_whitespace_stdout_with_diagnostics_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "no inference output"):
            self.execute("import sys; print('ready', file=sys.stderr); print('   ')")

    def test_unterminated_unicode_stdout_is_preserved(self):
        text, _, _ = self.execute(
            "import sys; sys.stderr.write('diagnostic'); "
            "sys.stdout.write('answer-\\u03a9')"
        )
        self.assertEqual(text, "answer-\u03a9")

    def test_both_large_pipes_are_drained(self):
        text, _, _ = self.execute(
            "import sys, threading; "
            "t=threading.Thread(target=lambda: "
            "sys.stderr.write('d' * 1048576)); t.start(); "
            "sys.stdout.write('a' * 1048576); sys.stdout.flush(); t.join()"
        )
        self.assertEqual(len(text), 1048576)
        self.assertEqual(hashlib.sha256(text.encode()).digest(),
                         hashlib.sha256(b'a' * 1048576).digest())

    def test_recursive_proposal_and_answer_hash_exclude_diagnostics(self):
        def generate(_prompt, *, max_new_tokens):
            return self.execute(
                "import sys; print('native diagnostic', file=sys.stderr); "
                "print('answer-42')"
            )[0]
        result = execute_recursive(
            "check output identity", FabricLimits(max_depth=0, max_nodes=2,
                quorum=2, max_new_tokens=8, max_model_calls=2),
            generate, model_root="a" * 64,
        )
        self.assertEqual(result.answer, "answer-42\n")
        self.assertEqual(result.transcript["answer_root"],
                         hashlib.sha256(b"answer-42\n").hexdigest())


class ReceiptIdentityContract(unittest.TestCase):
    def setUp(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main([
                "decide", "--criterion", "safety:1:0", "--reject-below", "0:0",
                "--accept-at", "1:0", "--model-root", "a" * 64,
                "--request-root", "b" * 64,
            ])
        self.assertEqual(status, 0)
        self.record = json.loads(out.getvalue())

    def receipt(self, model="a" * 64, request="b" * 64):
        return create_receipt(
            source_kind="decide", transcript=self.record["transcript"],
            certificate=self.record["certificate"], model_root=model,
            request_root=request, arithmetic_mode="integer_oracle",
        )

    def test_matching_identity_control(self):
        receipt = self.receipt().as_dict()
        self.assertTrue(receipt["source_certificate_verified"])
        self.assertEqual(receipt["model_root"], receipt["transcript"]["model_root"])
        self.assertEqual(receipt["request_root"], receipt["transcript"]["request_root"])

    def test_model_relabel_must_be_rejected(self):
        with self.assertRaises(ValueError):
            self.receipt(model="c" * 64)

    def test_request_relabel_must_be_rejected(self):
        with self.assertRaises(ValueError):
            self.receipt(request="d" * 64)

    def test_transcript_tamper_control(self):
        self.record["transcript"]["status"] = -1
        with self.assertRaises(ValueError):
            self.receipt()

    def test_cli_root_overrides_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decision.json"
            path.write_text(json.dumps(self.record), encoding="utf-8")
            for flag in ("--model-root", "--request-root"):
                with self.subTest(flag=flag):
                    with contextlib.redirect_stdout(io.StringIO()), \
                            contextlib.redirect_stderr(io.StringIO()), \
                            self.assertRaises(SystemExit) as caught:
                        main(["attest", str(path), "--source-kind", "decide",
                              "--arithmetic-mode", "integer_oracle", flag, "c" * 64])
                    self.assertEqual(caught.exception.code, 2)

    def test_cli_inferred_roots_remain_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decision.json"
            path.write_text(json.dumps(self.record), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["attest", str(path), "--source-kind", "decide",
                               "--arithmetic-mode", "integer_oracle"])
            self.assertEqual(status, 0)
            receipt = json.loads(output.getvalue())
            self.assertEqual(receipt["model_root"], "a" * 64)
            self.assertEqual(receipt["request_root"], "b" * 64)

    def test_absent_roots_can_still_be_supplied(self):
        transcript = {k: v for k, v in self.record["transcript"].items()
                      if k not in ("model_root", "request_root")}
        receipt = create_receipt(source_kind="decide", transcript=transcript,
            certificate=canonical_sha256(transcript), model_root="a" * 64,
            request_root="b" * 64, arithmetic_mode="integer_oracle")
        self.assertTrue(receipt.as_dict()["source_certificate_verified"])


if __name__ == "__main__":
    unittest.main()
