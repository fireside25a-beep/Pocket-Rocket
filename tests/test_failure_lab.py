from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import unittest

from neuro_inverse.agent_fabric import FabricLimits, execute_recursive, verify_trace_certificate
from neuro_inverse.ds4_runtime import (
    DS4_REPOSITORY, REQUIRED_FLAGS, REQUIRED_SOURCE,
    _atomic_json, _execute_guarded, _verify_ds4_binary,
    install_ds4, recover_ds4_install,
)


class FailureLabTests(unittest.TestCase):
    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        git = shutil.which("git")
        if git is None:
            self.skipTest("git unavailable")
        return subprocess.run([git, *args], cwd=cwd, text=True, capture_output=True, check=True)

    def _repo(self, path: Path, origin: str) -> str:
        path.mkdir(parents=True)
        self._git("init", "-q", cwd=path)
        self._git("config", "user.email", "failure-lab@example.invalid", cwd=path)
        self._git("config", "user.name", "Failure Lab", cwd=path)
        self._git("remote", "add", "origin", origin, cwd=path)
        (path / "seed.txt").write_text("seed\n", encoding="utf-8")
        self._git("add", ".", cwd=path)
        self._git("commit", "-q", "-m", "seed", cwd=path)
        return self._git("rev-parse", "HEAD", cwd=path).stdout.strip()

    def _git_wrapper(self, directory: Path) -> tuple[Path, Path, str]:
        real_git = shutil.which("git")
        if real_git is None:
            self.skipTest("git unavailable")
        log = directory / "git.log"
        wrapper = directory / "git"
        wrapper.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$GIT_FAILURE_LAB_LOG\"\nexec \"$REAL_GIT\" \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        return wrapper, log, real_git

    def _assert_no_network_git(self, log: Path) -> None:
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertNotIn(" fetch ", f" {text} ")
        self.assertNotIn("clone ", text)

    def test_install_refusals_happen_before_network_mutation(self) -> None:
        original_path = os.environ.get("PATH", "")
        original_log = os.environ.get("GIT_FAILURE_LAB_LOG")
        original_real = os.environ.get("REAL_GIT")
        try:
            for case in ("nongit", "wrong-origin", "dirty"):
                with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    bindir = root / "bin"; bindir.mkdir()
                    _wrapper, log, real_git = self._git_wrapper(bindir)
                    os.environ["PATH"] = str(bindir) + os.pathsep + original_path
                    os.environ["GIT_FAILURE_LAB_LOG"] = str(log)
                    os.environ["REAL_GIT"] = real_git
                    runtime = root / "runtime" / "ds4"
                    if case == "nongit":
                        runtime.mkdir(parents=True)
                        (runtime / "file").write_text("not git", encoding="utf-8")
                    elif case == "wrong-origin":
                        self._repo(runtime, "https://example.invalid/not-ds4.git")
                    else:
                        self._repo(runtime, DS4_REPOSITORY)
                        (runtime / "dirty.txt").write_text("dirty", encoding="utf-8")
                    with self.assertRaises(RuntimeError):
                        install_ds4(root, run_tests=False)
                    self._assert_no_network_git(log)
        finally:
            os.environ["PATH"] = original_path
            if original_log is None: os.environ.pop("GIT_FAILURE_LAB_LOG", None)
            else: os.environ["GIT_FAILURE_LAB_LOG"] = original_log
            if original_real is None: os.environ.pop("REAL_GIT", None)
            else: os.environ["REAL_GIT"] = original_real

    def test_interrupted_install_recovery_and_atomic_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / "runtime"; parent.mkdir()
            previous = parent / "ds4.previous"; previous.mkdir()
            (previous / "sentinel").write_text("old-good", encoding="utf-8")
            staging = parent / "ds4.installing"; staging.mkdir()
            (staging / "partial").write_text("partial", encoding="utf-8")
            report = recover_ds4_install(root)
            self.assertTrue(report["restored_previous"])
            self.assertTrue(report["removed_staging"])
            self.assertEqual("old-good", (parent / "ds4" / "sentinel").read_text())
            manifest = parent / "ds4-install-manifest.json"
            _atomic_json(manifest, {"revision": "abc", "contract_ok": True})
            self.assertEqual({"revision": "abc", "contract_ok": True}, json.loads(manifest.read_text()))
            self.assertEqual([], list(parent.glob("ds4-install-manifest.json.*.tmp")))

    def test_runtime_contract_corruption_cli_and_revision_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp) / "ds4"
            commit = self._repo(runtime, DS4_REPOSITORY)
            for name in REQUIRED_SOURCE:
                path = runtime / name
                if name == "LICENSE": path.write_text("MIT License\n", encoding="utf-8")
                elif name == "Makefile": path.write_text("all:\n\t@true\n", encoding="utf-8")
                else: path.write_text("/* fixture source */\n", encoding="utf-8")
            self._git("add", ".", cwd=runtime); self._git("commit", "-q", "-m", "contract", cwd=runtime)
            commit = self._git("rev-parse", "HEAD", cwd=runtime).stdout.strip()
            binary = runtime / "ds4"
            flags = " ".join(REQUIRED_FLAGS)
            binary.write_text(f"#!/bin/sh\necho '{flags}'\n", encoding="utf-8"); binary.chmod(0o755)
            self.assertEqual(commit, _verify_ds4_binary(runtime, commit))
            binary.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "executable"):
                _verify_ds4_binary(runtime, commit)
            binary.chmod(0o755); self.assertEqual(commit, _verify_ds4_binary(runtime, commit))
            binary.write_text("#!/bin/sh\necho '--ctx --tokens'\n", encoding="utf-8"); binary.chmod(0o755)
            with self.assertRaisesRegex(RuntimeError, "CLI contract"):
                _verify_ds4_binary(runtime, commit)
            binary.write_text(f"#!/bin/sh\necho '{flags}'\n", encoding="utf-8"); binary.chmod(0o755)
            with self.assertRaisesRegex(RuntimeError, "revision mismatch"):
                _verify_ds4_binary(runtime, "0" * 40)
            self.assertEqual(commit, _verify_ds4_binary(runtime, commit))

    def test_real_process_tree_rss_timeout_term_kill_exit_and_empty_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child = root / "tree.py"
            child.write_text(
                "import subprocess,sys\n"
                "p=subprocess.Popen([sys.executable,'-c','import time; x=bytearray(12*1024*1024); time.sleep(0.4)'])\n"
                "print('tree-ok', flush=True)\np.wait()\n",
                encoding="utf-8",
            )
            text, peak, _elapsed = _execute_guarded(
                [sys.executable, str(child)], cwd=root, env=os.environ.copy(),
                rss_cap_bytes=512 * 1024 * 1024, timeout=5,
            )
            self.assertIn("tree-ok", text); self.assertGreater(peak, 8 * 1024 * 1024)

            marker = root / "term.marker"
            stubborn = root / "stubborn.py"
            stubborn.write_text(
                "import os,signal,time\n"
                f"m={str(marker)!r}\n"
                "def h(*_):\n open(m,'w').write('TERM')\n"
                "signal.signal(signal.SIGTERM,h)\n"
                "while True: time.sleep(0.05)\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "timeout exceeded"):
                _execute_guarded([sys.executable, str(stubborn)], cwd=root, env=os.environ.copy(),
                                 rss_cap_bytes=512 * 1024 * 1024, timeout=0.8,
                                 term_grace_seconds=0.15)
            self.assertEqual("TERM", marker.read_text())
            with self.assertRaisesRegex(RuntimeError, r"inference failed \(7\)"):
                _execute_guarded([sys.executable, "-c", "raise SystemExit(7)"], cwd=root,
                                 env=os.environ.copy(), rss_cap_bytes=512 * 1024 * 1024, timeout=2)
            with self.assertRaisesRegex(RuntimeError, "no inference output"):
                _execute_guarded([sys.executable, "-c", "pass"], cwd=root,
                                 env=os.environ.copy(), rss_cap_bytes=512 * 1024 * 1024, timeout=2)
            with self.assertRaisesRegex(RuntimeError, "RSS cap exceeded"):
                _execute_guarded([sys.executable, "-c", "import time; x=bytearray(32*1024*1024); time.sleep(2)"],
                                 cwd=root, env=os.environ.copy(), rss_cap_bytes=2 * 1024 * 1024,
                                 timeout=2, term_grace_seconds=0.1)

    def test_recursion_trace_proves_depth_and_all_budgets(self) -> None:
        def process_generator(_prompt: str, *, max_new_tokens: int) -> str:
            index = process_generator.calls % 3
            process_generator.calls += 1
            word = ("red", "blue", "green")[index]
            completed = subprocess.run(["/bin/printf", "%s", word], text=True,
                                       capture_output=True, check=True)
            return completed.stdout
        process_generator.calls = 0  # type: ignore[attr-defined]

        depth0 = execute_recursive("trace budget", FabricLimits(max_depth=0, max_nodes=3,
                                   quorum=3, max_new_tokens=8, max_model_calls=3), process_generator,
                                   model_root="a" * 64)
        self.assertEqual([0], [row["depth"] for row in depth0.transcript["rounds"]])
        self.assertEqual(3, depth0.transcript["model_calls_used"])

        process_generator.calls = 0  # type: ignore[attr-defined]
        depth3 = execute_recursive("trace budget", FabricLimits(max_depth=3, max_nodes=12,
                                   quorum=3, max_new_tokens=8, max_model_calls=12), process_generator,
                                   model_root="a" * 64)
        self.assertEqual([0, 1, 2, 3], [row["depth"] for row in depth3.transcript["rounds"]])
        self.assertEqual(12, depth3.transcript["nodes_used"])
        self.assertEqual(12, depth3.transcript["model_calls_used"])
        trace = depth3.transcript["recursion_trace"]
        self.assertTrue(verify_trace_certificate(trace, depth3.transcript["recursion_trace_certificate"]))
        edges = trace["edges"]
        self.assertTrue(all(edge["parent_node"] == 0 for edge in edges[:3]))
        self.assertTrue(all(edge["parent_node"] > 0 for edge in edges[3:]))

        process_generator.calls = 0  # type: ignore[attr-defined]
        node_limited = execute_recursive("trace budget", FabricLimits(max_depth=3, max_nodes=5,
                                        quorum=3, max_new_tokens=8, max_model_calls=12), process_generator,
                                        model_root="a" * 64)
        self.assertLessEqual(node_limited.transcript["nodes_used"], 5)
        self.assertLessEqual(node_limited.transcript["model_calls_used"], 12)


if __name__ == "__main__":
    unittest.main()
