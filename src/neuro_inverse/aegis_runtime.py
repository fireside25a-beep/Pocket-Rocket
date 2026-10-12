"""Real, local Aegis Language Suite 2.4.3 compiler and VM integration.

Aegis is a distinct execution/toolchain domain, not a model backend. Nothing
in this module interprets, modifies, or accepts Pocket Rocket/model payloads.
Only checked source suffixes are admissible and all execution is opt-in.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .aegis_boundary import AegisBoundaryError, InputKind, require_aegis_source


@dataclass(frozen=True)
class AegisResult:
    language: str
    stdout: bytes
    stderr: bytes
    artifact_sha256: str
    artifact_bytes: int
    proof_sha256: str | None
    proof_bytes: int
    audited: bool
    backend: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "stdout": self.stdout.decode("utf-8", errors="replace"),
            "stderr": self.stderr.decode("utf-8", errors="replace"),
            "artifact_sha256": self.artifact_sha256,
            "artifact_bytes": self.artifact_bytes,
            "proof_sha256": self.proof_sha256,
            "proof_bytes": self.proof_bytes,
            "audited": self.audited,
            "backend": self.backend,
        }


def _digest(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


class AegisRuntime:
    """Opt-in, non-network execution of the checksum-verified shipped Aegis suite.

    DXL compiles to a native Linux x86-64 program. DXS and DXASM compile to
    audited DXB3, which executes through dxvm with the one-byte bundled policy.
    The language runtimes do not receive Pocket Rocket storage or GGUF bytes.
    """

    def __init__(self, suite: Path | None = None, *, timeout: float = 30.0) -> None:
        self.suite = (Path(suite) if suite else Path(__file__).resolve().parents[2] /
                      "toolchains/aegis-language-suite-2.4.3").resolve()
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
            raise ValueError("timeout must be in (0, 300] seconds")
        self.timeout = float(timeout)

    def _exec(self, argv: list[str | os.PathLike[str]], *, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
        args = [os.fspath(x) for x in argv]
        try:
            result = subprocess.run(args, cwd=cwd or self.suite, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AegisBoundaryError(f"Aegis execution failed to start or timed out: {args[0]}") from exc
        if result.returncode:
            message = result.stderr.decode("utf-8", "replace")[:4096]
            raise AegisBoundaryError(f"Aegis command exited {result.returncode}: {args[0]}: {message}")
        return result

    def prepare(self) -> Path:
        """Verify the full shipped source manifest before running installation."""
        manifest = self.suite / "SHA256SUMS.txt"
        if not manifest.is_file() or manifest.is_symlink():
            raise AegisBoundaryError("Aegis source release checksum manifest missing")
        # This independently validates setup.sh itself *before* executing it,
        # along with compiler, VM, corpus and binary files. No path escapes.
        expected = manifest.read_text(encoding="ascii").splitlines()
        if len(expected) < 100:
            raise AegisBoundaryError("Aegis source release manifest incomplete")
        for line in expected:
            if len(line) < 68 or line[64:66] != "  ":
                raise AegisBoundaryError("malformed source release manifest entry")
            digest, relative = line[:64], line[66:]
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise AegisBoundaryError("malformed source release digest")
            path = (self.suite / relative).resolve(strict=False)
            if not path.is_relative_to(self.suite) or path.is_symlink() or not path.is_file():
                raise AegisBoundaryError("missing or escaping Aegis source release entry")
            if _digest(path) != digest:
                raise AegisBoundaryError(f"Aegis source release integrity failure: {relative}")
        # The suite also checks host ABI and checksums before installing tools.
        self._exec(["bash", "scripts/setup.sh"])
        bindir = self.suite / "build/bin"
        for name in ("dxlc", "dxscc", "dxasm", "dxaudit", "dxvm"):
            if not (bindir / name).is_file() or not os.access(bindir / name, os.X_OK):
                raise AegisBoundaryError(f"missing Aegis executable: {name}")
        return bindir

    def execute(self, source: Path | str) -> AegisResult:
        """Compile and *really* execute one documented source profile.

        Negative/out-of-profile programs produce an error; they are not
        emulated or silently retargeted. Generated files are private temps.
        """
        source = require_aegis_source(source)
        if source.is_symlink():
            raise AegisBoundaryError("Aegis input cannot be a symbolic link")
        resolved = source.resolve(strict=True)
        if resolved.suffix.lower() != source.suffix.lower():
            raise AegisBoundaryError("Aegis source path changes format through aliasing")
        source = resolved
        kind = {".dxl": InputKind.DXL_SOURCE, ".dxs": InputKind.DXS_SOURCE,
                ".dxasm": InputKind.DXASM_SOURCE}[source.suffix.lower()]
        require_aegis_source(source, expected=kind)
        binroot = self.prepare()
        with tempfile.TemporaryDirectory(prefix="pocket-aegis-") as temp:
            tmp = Path(temp)
            if kind is InputKind.DXL_SOURCE:
                exe = tmp / "program"
                self._exec([binroot / "dxlc", "build", source, "-o", exe])
                if not exe.is_file():
                    raise AegisBoundaryError("Aegis native compiler did not emit executable")
                out = self._exec([exe])
                return AegisResult("DXL", out.stdout, out.stderr, _digest(exe),
                                   exe.stat().st_size, None, 0, False, "native-x86_64-linux")
            bytecode = tmp / "program.dxb"
            compiler = "dxscc" if kind is InputKind.DXS_SOURCE else "dxasm"
            self._exec([binroot / compiler, source, bytecode])
            if not bytecode.is_file():
                raise AegisBoundaryError("Aegis compiler did not emit DXB3")
            self._exec([binroot / "dxaudit", bytecode])
            policy = self.suite / "examples/policy_all.bin"
            if not policy.is_file() or policy.read_bytes() != b"\x03":
                # This explicit byte is Aegis's bundled policy, NOT model data.
                raise AegisBoundaryError("bundled Aegis policy identity mismatch")
            proof = tmp / "execution.proof"
            out = self._exec([binroot / "dxvm", bytecode, policy, proof])
            if not proof.is_file():
                raise AegisBoundaryError("Aegis VM did not emit proof")
            return AegisResult(kind.name.split("_")[0], out.stdout, out.stderr,
                               _digest(bytecode), bytecode.stat().st_size,
                               _digest(proof), proof.stat().st_size, True, "DXB3-VM")


__all__ = ["AegisRuntime", "AegisResult"]
