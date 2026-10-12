#!/usr/bin/env python3
"""Make a runnable one-stage base ZIP plus an overlay residual ZIP."""
from __future__ import annotations

import argparse
import copy
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.nprq import meta_from_dict, verify_tensor


def trim_record(record: dict) -> None:
    meta = record["meta"]
    meta["stages"] = 1
    meta["stage_files"] = meta["stage_files"][:1]
    meta["stage_sha256"] = meta["stage_sha256"][:1]
    meta["rmse"] = meta["rmse"][:1]


def _relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"Unsafe package path: {value!r}")
    return path


def _records(manifest: dict):
    for record in manifest.get("common", {}).values():
        yield record, int(manifest["common_stages"]), "common"
    for layer in manifest.get("layers", {}).values():
        for expert in layer.get("experts", {}).values():
            for name in ("gate", "up", "down"):
                yield expert[name], int(manifest["ffn_stages"]), name


def referenced_stage_paths(package: Path, manifest: dict) -> set[Path]:
    """Validate all manifest pages and return only referenced stage files."""
    paths: set[Path] = set()
    for record, expected_stages, _ in _records(manifest):
        if not isinstance(record, dict) or not isinstance(record.get("directory"), str):
            raise SystemExit("Malformed NPRQ page record")
        directory = _relative_path(record["directory"])
        try:
            meta = meta_from_dict(record["meta"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"Malformed NPRQ page metadata: {exc}") from exc
        if meta.stages != expected_stages:
            raise SystemExit("Manifest stage count does not match page metadata")
        try:
            verify_tensor(package / directory, meta)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"NPRQ page verification failed in {directory}: {exc}") from exc
        for filename in meta.stage_files:
            relative = directory / _relative_path(filename)
            if relative in paths:
                raise SystemExit(f"Duplicate NPRQ stage reference: {relative}")
            if not (package / relative).is_file():
                raise SystemExit(f"Missing NPRQ stage: {relative}")
            paths.add(relative)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, default=Path("releases"))
    args = parser.parse_args()
    manifest = json.loads((args.package / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete"):
        raise SystemExit("Refusing to package an incomplete build")
    if not args.package.is_dir():
        raise SystemExit("Package must be a directory")
    referenced = referenced_stage_paths(args.package, manifest)
    base_stage_paths = {path for path in referenced if ".s0." in path.name}
    residual_stage_paths = referenced - base_stage_paths
    base_manifest = copy.deepcopy(manifest)
    base_manifest["ffn_stages"] = base_manifest["common_stages"] = 1
    for record in base_manifest["common"].values():
        trim_record(record)
    for layer in base_manifest["layers"].values():
        for expert in layer["experts"].values():
            for name in ("gate", "up", "down"):
                trim_record(expert[name])
    args.output.mkdir(parents=True, exist_ok=True)
    base = args.output / "DeepSeek-V4-Flash-NeuroRoute-NPRQ-base-s0.zip"
    residual = args.output / "DeepSeek-V4-Flash-NeuroRoute-NPRQ-residual-s1plus.zip"
    with zipfile.ZipFile(base, "w", allowZip64=True) as archive:
        archive.writestr("manifest.json", json.dumps(base_manifest, indent=2, sort_keys=True) + "\n")
        for path in sorted(args.package.rglob("*")):
            if not path.is_file() or path.name in {"manifest.json", "BUILD_STATE.json"}:
                continue
            relative = path.relative_to(args.package)
            if path.suffix in {".nprq", ".prk", ".f32"} and relative not in base_stage_paths:
                continue
            archive.write(path, relative, compress_type=zipfile.ZIP_STORED)
    with zipfile.ZipFile(residual, "w", allowZip64=True) as archive:
        archive.write(args.package / "manifest.json", "manifest.json", compress_type=zipfile.ZIP_DEFLATED)
        for relative in sorted(residual_stage_paths):
            archive.write(args.package / relative, relative, compress_type=zipfile.ZIP_STORED)
    print(f"BASE {base} bytes={base.stat().st_size}")
    print(f"OVERLAY {residual} bytes={residual.stat().st_size}")
    print("Extract the overlay onto the base to enable all residual stages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
