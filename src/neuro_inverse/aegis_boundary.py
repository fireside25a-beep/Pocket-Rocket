"""Capability-gated boundary for an optional Aegis toolchain.

This adapter does not emulate the real bundled Aegis language suite. The
known language/tool boundary is:

* DXL: typed systems, compiled by ``dxlc``;
* DXS: deterministic scripting, compiled by ``dxscc`` (or ``dxs24cc``);
* DXASM: explicit assembly, assembled by ``dxasm``;
* DXS/DXASM programs target the DXB3 VM (``dxvm`` or ``dxvm24``).

Only executable files discovered from an explicit toolchain directory or the
process ``PATH`` are usable.  The adapter never turns a model or Flat32 file
into source.  Pocket Rocket and Flat32 are storage/transport concerns: their
bytes may be verified and hashed, but they are not interpreted by Aegis.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from .pocket_pack import PocketRocketError, PocketRocketReader


class AegisBoundaryError(ValueError):
    """Raised when an input crosses the Aegis/storage boundary incorrectly."""


class AegisUnavailable(AegisBoundaryError):
    """Raised when a requested Aegis executable is not installed."""


class InputKind(str, Enum):
    DXL_SOURCE = "DXL_SOURCE"
    DXS_SOURCE = "DXS_SOURCE"
    DXASM_SOURCE = "DXASM_SOURCE"
    POCKET_ROCKET_STORAGE = "POCKET_ROCKET_STORAGE"
    FLAT32_STORAGE = "FLAT32_STORAGE"
    MODEL_WEIGHTS = "MODEL_WEIGHTS"
    UNKNOWN = "UNKNOWN"


# Names are based on the pinned Aegis 2.4.3 tool roles.  Alternative VM and
# DXS compiler names are selected only when a real executable is found.
TOOL_NAMES: Mapping[str, tuple[str, ...]] = {
    "dxlc": ("dxlc",),
    "dxscc": ("dxscc", "dxs24cc"),
    "dxasm": ("dxasm",),
    "dxvm": ("dxvm", "dxvm24"),
    "dxaudit": ("dxaudit",),
}
STAGE_TO_TOOL = {
    "dxl": "dxlc",
    "dxs": "dxscc",
    "dxasm": "dxasm",
    "dxb3": "dxvm",
    "audit": "dxaudit",
}

_SOURCE_SUFFIXES = {
    ".dxl": InputKind.DXL_SOURCE,
    ".dxs": InputKind.DXS_SOURCE,
    ".dxasm": InputKind.DXASM_SOURCE,
}
_STORAGE_SUFFIXES = {".pkr", ".pocket", ".pocket-rocket", ".flat32", ".f32"}
_MODEL_SUFFIXES = {
    ".safetensors",
    ".gguf",
    ".bin",
    ".pt",
    ".pth",
    ".onnx",
    ".ckpt",
}


def classify_input(path: str | Path) -> InputKind:
    """Classify a path without opening or interpreting its contents.

    Unknown extensions are intentionally not treated as source.  Callers must
    opt into a known source kind before invoking an Aegis compiler.
    """

    suffix = Path(path).suffix.lower()
    if suffix in _SOURCE_SUFFIXES:
        return _SOURCE_SUFFIXES[suffix]
    if suffix in _STORAGE_SUFFIXES:
        return (
            InputKind.FLAT32_STORAGE
            if suffix in {".flat32", ".f32"}
            else InputKind.POCKET_ROCKET_STORAGE
        )
    if suffix in _MODEL_SUFFIXES:
        return InputKind.MODEL_WEIGHTS
    return InputKind.UNKNOWN


def require_aegis_source(path: str | Path, *, expected: InputKind | None = None) -> Path:
    """Return a validated Aegis source path; reject storage and model bytes."""

    candidate = Path(path)
    kind = classify_input(candidate)
    if kind not in {InputKind.DXL_SOURCE, InputKind.DXS_SOURCE, InputKind.DXASM_SOURCE}:
        raise AegisBoundaryError(
            f"{candidate} is {kind.value}; only DXL/DXS/DXASM source may enter Aegis"
        )
    if expected is not None and kind is not expected:
        raise AegisBoundaryError(f"expected {expected.value}, got {kind.value}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


@dataclass(frozen=True)
class AegisCapabilities:
    """Observed executable capabilities, not a claim that the toolchain works."""

    search_root: str | None
    tools: Mapping[str, str | None]
    missing: tuple[str, ...]

    @property
    def available(self) -> bool:
        return not self.missing

    def path_for(self, tool: str) -> str:
        if tool not in TOOL_NAMES:
            raise AegisBoundaryError(f"unknown Aegis tool: {tool}")
        path = self.tools.get(tool)
        if path is None:
            names = ", ".join(TOOL_NAMES[tool])
            raise AegisUnavailable(f"Aegis tool unavailable ({names})")
        return path

    def require_stage(self, stage: str) -> str:
        try:
            tool = STAGE_TO_TOOL[stage.lower()]
        except KeyError as exc:
            raise AegisBoundaryError(f"unknown Aegis stage: {stage}") from exc
        return self.path_for(tool)


def _executable(path: Path) -> str | None:
    if path.is_file() and os.access(path, os.X_OK):
        return str(path.resolve())
    return None


def discover_aegis(*, toolchain_root: str | Path | None = None) -> AegisCapabilities:
    """Discover real Aegis executables without downloading or fabricating them.

    With ``toolchain_root`` set, only ``root`` and ``root/bin`` are searched;
    this makes an empty test directory an honest unavailable capability report.
    Without it, each canonical/alternate name is resolved through ``PATH``.
    """

    root = Path(toolchain_root).expanduser() if toolchain_root is not None else None
    tools: dict[str, str | None] = {}
    for role, names in TOOL_NAMES.items():
        found: str | None = None
        if root is not None:
            for directory in (root, root / "bin"):
                for name in names:
                    found = _executable(directory / name)
                    if found is not None:
                        break
                if found is not None:
                    break
        else:
            for name in names:
                found = shutil.which(name)
                if found is not None:
                    found = str(Path(found).resolve())
                    break
        tools[role] = found
    missing = tuple(role for role in TOOL_NAMES if tools[role] is None)
    return AegisCapabilities(
        str(root.resolve()) if root is not None and root.exists() else (str(root) if root else None),
        tools,
        missing,
    )


@dataclass(frozen=True)
class ToolRun:
    """Measured result of one actual subprocess invocation."""

    role: str
    executable: str
    argv: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_ms: float


@dataclass(frozen=True)
class PocketStorageInspection:
    path: str
    format: str
    verified: bool
    source_bytes: int
    container_bytes: int
    source_sha256: str
    storage_only: bool
    interpretation_forbidden: bool
    hash_computed: bool


class AegisBoundary:
    """Safe adapter joining real Aegis capabilities to Pocket Rocket storage."""

    def __init__(self, capabilities: AegisCapabilities) -> None:
        self.capabilities = capabilities

    def inspect_pocket_rocket(self, path: str | Path) -> PocketStorageInspection:
        """Verify a Pocket Rocket container; never pass its bytes to Aegis."""

        candidate = Path(path)
        if classify_input(candidate) is not InputKind.POCKET_ROCKET_STORAGE:
            raise AegisBoundaryError("Pocket Rocket inspection requires a .pkr/.pocket file")
        try:
            with PocketRocketReader(candidate) as reader:
                info = reader.info
                reader.verify()
        except (OSError, PocketRocketError) as exc:
            raise AegisBoundaryError(f"Pocket Rocket verification failed: {candidate}") from exc
        return PocketStorageInspection(
            path=str(candidate),
            format="Pocket Rocket lossless container",
            verified=True,
            source_bytes=info.source_bytes,
            container_bytes=info.container_bytes,
            source_sha256=info.source_sha256,
            storage_only=True,
            interpretation_forbidden=True,
            hash_computed=True,
        )

    def inspect_flat32_storage(self, path: str | Path) -> PocketStorageInspection:
        """Hash a Flat32 file as storage; no Flat32 decoding or interpretation."""

        candidate = Path(path)
        if classify_input(candidate) is not InputKind.FLAT32_STORAGE:
            raise AegisBoundaryError("Flat32 inspection requires a .flat32/.f32 file")
        try:
            size = candidate.stat().st_size
            with candidate.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
        except OSError as exc:
            raise AegisBoundaryError(f"Flat32 storage inspection failed: {candidate}") from exc
        return PocketStorageInspection(
            path=str(candidate),
            format="Flat32 lossless storage encoding (not interpreted)",
            # A digest is computed for identity, but without a trusted
            # expected digest or a Flat32 structural parser this is not a
            # format/integrity verification claim.
            verified=False,
            source_bytes=size,
            container_bytes=size,
            source_sha256=digest,
            storage_only=True,
            interpretation_forbidden=True,
            hash_computed=True,
        )

    def run_stage(
        self,
        stage: str,
        args: Sequence[str] = (),
        *,
        cwd: str | Path | None = None,
        timeout: float = 60.0,
    ) -> ToolRun:
        """Run one real Aegis stage with shell execution disabled.

        This method intentionally performs no source synthesis and no model
        loading.  The caller must provide a source path validated by
        :func:`require_aegis_source` when compiling source.
        """

        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout must be positive")
        if any(not isinstance(value, str) for value in args):
            raise TypeError("Aegis arguments must be strings")
        if any(
            classify_input(value)
            in {
                InputKind.MODEL_WEIGHTS,
                InputKind.POCKET_ROCKET_STORAGE,
                InputKind.FLAT32_STORAGE,
            }
            for value in args
        ):
            raise AegisBoundaryError(
                "model weights and Pocket Rocket/Flat32 storage cannot be Aegis inputs"
            )
        executable = self.capabilities.require_stage(stage)
        argv = (executable, *tuple(args))
        start = time.perf_counter()
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(cwd) if cwd is not None else None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
                timeout=float(timeout),
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            raise AegisBoundaryError(f"Aegis stage timed out: {stage}") from exc
        except OSError as exc:
            raise AegisBoundaryError(f"Aegis stage could not start: {stage}") from exc
        return ToolRun(
            role=stage.lower(),
            executable=executable,
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_ms=elapsed_ms,
        )


__all__ = [
    "AegisBoundary",
    "AegisBoundaryError",
    "AegisCapabilities",
    "AegisUnavailable",
    "InputKind",
    "PocketStorageInspection",
    "STAGE_TO_TOOL",
    "TOOL_NAMES",
    "ToolRun",
    "classify_input",
    "discover_aegis",
    "require_aegis_source",
]
