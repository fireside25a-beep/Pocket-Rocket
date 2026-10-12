#!/usr/bin/env python3
"""Build a deterministic, source-only Pocket Rocket Codex handoff ZIP."""
from __future__ import annotations

import argparse
import hashlib
import os
import stat
import tempfile
import zipfile
from pathlib import Path


ROOT_FILES = {
    ".gitignore", "LICENSE", "Makefile", "README.md", "STATUS.md",
    "pyproject.toml", "ARCHITECTURE.md", "SECURITY.md", "CONTRIBUTING.md",
    "THIRD_PARTY_NOTICES.md",
}
SOURCE_DIRS = {
    "benchmarks", "config", "docs", "experiments", "native", "scripts",
    "src", "tests", "ui", ".github", "toolchains", "evidence",
}
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "models", "releases", "var", "build", "dist", ".aegis-cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".gguf", ".safetensors", ".pt", ".pth", ".onnx", ".zip"}
ARCHIVE_ROOT = "Pocket_Rocket_0.4.2"
# Keep deterministic ZIP timestamps safely in the past for builders whose UTC
# clocks lag the release-document date; future mtimes make `make` warn about
# clock skew after extraction.
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def _is_source(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if not path.is_file() or any(part in SKIP_PARTS for part in relative.parts):
        return False
    if relative.suffix.casefold() in SKIP_SUFFIXES:
        return False
    if len(relative.parts) == 1:
        return relative.name in ROOT_FILES
    if relative.parts[0] not in SOURCE_DIRS:
        return False
    # Never package a compiler output accidentally left under native/.
    try:
        if relative.parts[0] != "toolchains" and path.read_bytes()[:4] == b"\x7fELF":
            return False
    except OSError:
        return False
    return True


def _entry(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build(root: Path, output: Path) -> tuple[int, str]:
    root = root.resolve(strict=True)
    candidates = list(root.rglob("*"))
    symlinks = sorted(path.relative_to(root).as_posix() for path in candidates if path.is_symlink())
    if symlinks:
        raise RuntimeError(f"release tree contains symbolic links: {symlinks}")
    files = sorted(path for path in candidates if _is_source(path, root))
    if not files:
        raise RuntimeError("release source set is empty")
    manifest_lines: list[str] = []
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                relative = path.relative_to(root).as_posix()
                data = path.read_bytes()
                manifest_lines.append(f"{hashlib.sha256(data).hexdigest()}  {relative}")
                executable = bool(path.stat().st_mode & 0o111) or (relative.startswith("scripts/") and data.startswith(b"#!"))
                archive.writestr(_entry(f"{ARCHIVE_ROOT}/{relative}", executable), data)
            manifest = ("\n".join(manifest_lines) + "\n").encode()
            archive.writestr(_entry(f"{ARCHIVE_ROOT}/RELEASE_MANIFEST.sha256"), manifest)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return len(files) + 1, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    project = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=project)
    parser.add_argument("--output", type=Path,
                        default=project.parent / "Pocket_Rocket_0.4.2_Lumus_ARH_Aegis.zip")
    args = parser.parse_args()
    entries, digest = build(args.root, args.output.resolve())
    print(f"RELEASE {args.output.resolve()}")
    print(f"ENTRIES {entries}")
    print(f"SHA256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
