"""Independent Aegis-C2R 0.1.0 S0 translator integration (not a model path).

This implementation invokes the actual strict-C11 parser and translator from
its private versioned source tree. It does not substitute Aegis 2.4.3 for the
historically pinned 2.4.0 certificate corpus.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .aegis_boundary import AegisBoundaryError


@dataclass(frozen=True)
class C2RTranslation:
    output_dir: str
    rust_sha256: str
    ast_sha256: str
    proof_sha256: str
    dxl_sha256: str
    dxs_sha256: str
    dxasm_sha256: str

    def as_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class AegisC2R:
    """Run the real C-to-Rust S0 translator, with distinct version provenance."""

    def __init__(self, root: Path | None = None, *, timeout: float = 60.0) -> None:
        self.root = (Path(root) if root else Path(__file__).resolve().parents[2] /
                     "toolchains/aegis-c2r-0.1.0").resolve()
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
            raise ValueError("timeout must be in (0, 300] seconds")
        self.timeout = float(timeout)

    def _exec(self, args: list[str | os.PathLike[str]]) -> subprocess.CompletedProcess[bytes]:
        try:
            p = subprocess.run([os.fspath(a) for a in args], cwd=self.root,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AegisBoundaryError("Aegis-C2R executable failed to start or timed out") from exc
        if p.returncode:
            raise AegisBoundaryError(f"Aegis-C2R rejected input or failed ({p.returncode}): "
                                     + p.stderr.decode("utf8", "replace")[:4096])
        return p

    def build(self) -> Path:
        if not (self.root / "Makefile").is_file() or not (self.root / "src/aegis_c2r.c").is_file():
            raise AegisBoundaryError("Aegis-C2R source tree missing")
        self._exec(["make", "all"])
        executable = self.root / "build/bin/aegis-c2r"
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise AegisBoundaryError("C2R compiler binary missing after build")
        return executable

    @staticmethod
    def _admit_source(source: Path | str) -> Path:
        source = Path(source)
        if source.suffix.lower() != ".c" or source.is_symlink() or not source.is_file():
            raise AegisBoundaryError("Aegis-C2R admits existing non-symlink .c files only")
        return source.resolve(strict=True)

    def check(self, source: Path | str) -> str:
        source = self._admit_source(source)
        return self._exec([self.build(), "check", source]).stdout.decode("utf8", "replace")

    def translate(self, source: Path | str, output_dir: Path | str) -> C2RTranslation:
        source = self._admit_source(source)
        output_dir = Path(output_dir)
        if output_dir.is_symlink() or output_dir.resolve(strict=False) == source:
            raise AegisBoundaryError("C2R output must not alias source or symlink")
        if output_dir.exists():
            if not output_dir.is_dir() or any(output_dir.iterdir()):
                raise AegisBoundaryError("C2R output directory must be empty")
        else:
            output_dir.mkdir(parents=True)
        if output_dir.resolve().is_relative_to(self.root.resolve()):
            raise AegisBoundaryError("C2R generated output must be outside vendored source")
        dest = output_dir.resolve()
        stem = dest / "translation"
        rust, ast, proof = (dest / "translation.rs", dest / "translation.ast", dest / "translation.json")
        self._exec([self.build(), "translate", source, "-o", rust,
                    "--ast", ast, "--proof", proof, "--aegis-prefix", stem])
        dxl, dxs, dxasm = (dest / "translation.dxl", dest / "translation.dxs", dest / "translation.dxasm")
        for path in (rust, ast, proof, dxl, dxs, dxasm):
            if not path.is_file():
                raise AegisBoundaryError(f"C2R missing generated output: {path.name}")
        return C2RTranslation(str(dest), _sha(rust), _sha(ast), _sha(proof),
                              _sha(dxl), _sha(dxs), _sha(dxasm))


__all__ = ["AegisC2R", "C2RTranslation"]
