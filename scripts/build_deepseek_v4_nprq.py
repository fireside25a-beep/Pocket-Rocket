#!/usr/bin/env python3
"""Validate a DeepSeek V4 Flash source before native conversion.

The pinned input is GGUF and is intentionally not decoded as an unpacked
checkpoint. This gate re-verifies the downloader manifest and existing NPRQ
page records; native ds4 remains the executable model path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.nprq import meta_from_dict, stage_filenames, verify_tensor
from neuro_inverse.model_target import DEEPSEEK_V4_FLASH


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_source_member(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SystemExit(f"Unsafe source manifest path: {relative!r}")
    path = (root / candidate).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"Source manifest path escapes snapshot: {relative!r}") from exc
    return path


def verify_official_source(source: Path) -> tuple[dict, str]:
    """Re-hash every file listed by the immutable DeepSeek source manifest."""
    manifest_path = source / "NEUROROUTE_OFFICIAL_SOURCE_MANIFEST.json"
    if not manifest_path.is_file():
        raise SystemExit("Missing NEUROROUTE_OFFICIAL_SOURCE_MANIFEST.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid official source manifest: {exc}") from exc
    target = manifest.get("target", {})
    if target.get("model_id") != DEEPSEEK_V4_FLASH.model_id:
        raise SystemExit("Source manifest is not for DeepSeek V4 Flash")
    if target.get("weight_revision") != DEEPSEEK_V4_FLASH.weight_revision:
        raise SystemExit("Source manifest is not pinned to the expected revision")
    entries = manifest.get("files") or manifest.get("verification")
    if isinstance(entries, dict):
        entries = [{"path": target.get("weight_filename"), "size": entries.get("size_bytes"), "sha256": entries.get("sha256")}]
    if not isinstance(entries, list) or not entries:
        raise SystemExit("Source manifest has no file inventory")
    seen: set[str] = set()
    failures: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            failures.append("malformed inventory entry")
            continue
        relative = item.get("path")
        if not isinstance(relative, str) or relative in seen:
            failures.append(f"duplicate or invalid inventory path: {relative!r}")
            continue
        seen.add(relative)
        path = _safe_source_member(source, relative)
        if not path.is_file():
            failures.append(f"missing:{relative}")
            continue
        expected_size, expected_hash = item.get("size"), item.get("sha256")
        if isinstance(expected_size, int) and path.stat().st_size != expected_size:
            failures.append(f"size:{relative}")
        if isinstance(expected_hash, str) and re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash) and sha256(path) != expected_hash:
            failures.append(f"sha256:{relative}")
    if failures:
        raise SystemExit("OFFICIAL SOURCE RE-VERIFICATION FAILED\n" + "\n".join(failures))
    return manifest, sha256(manifest_path)


def valid_record(record: object, output: Path, expected_name: str, stages: int,
                 expected_shape: tuple[int, ...] | None = None) -> bool:
    try:
        if not isinstance(record, dict) or not isinstance(record.get("directory"), str):
            return False
        relative = Path(record["directory"])
        if relative.is_absolute() or ".." in relative.parts:
            return False
        meta = meta_from_dict(record["meta"])
        if meta.stages != stages or tuple(meta.stage_files) != stage_filenames(expected_name, stages):
            return False
        if expected_shape is not None and tuple(meta.shape) != tuple(expected_shape):
            return False
        verify_tensor(output / relative, meta)
        return True
    except (KeyError, TypeError, ValueError, OSError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the immutable model source and any existing NPRQ pages"
    )
    project = Path(__file__).resolve().parents[1]
    parser.add_argument("source", nargs="?", type=Path,
                        default=project / "models" / "DeepSeek-V4-Flash")
    args = parser.parse_args(argv)
    manifest, manifest_sha256 = verify_official_source(args.source.resolve())
    print(json.dumps({
        "status": "VERIFIED",
        "model_id": manifest["target"]["model_id"],
        "revision": manifest["target"]["weight_revision"],
        "manifest_sha256": manifest_sha256,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
