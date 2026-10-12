#!/usr/bin/env python3
"""Convert a complete NPRQ package into a separate Pocket Pack package."""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.nprq import meta_from_dict, verify_tensor
from neuro_inverse.pocket_pack import pack


def _relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"unsafe package path: {value!r}")
    return path


def _records(manifest: dict):
    for record in manifest.get("common", {}).values():
        yield record
    for layer in manifest.get("layers", {}).values():
        for expert in layer.get("experts", {}).values():
            for name in ("gate", "up", "down"):
                yield expert[name]


def _record_pairs(source: dict, converted: dict):
    for key, record in source.get("common", {}).items():
        yield record, converted["common"][key]
    for layer_id, layer in source.get("layers", {}).items():
        converted_layer = converted["layers"][layer_id]
        for expert_id, expert in layer.get("experts", {}).items():
            converted_expert = converted_layer["experts"][expert_id]
            for name in ("gate", "up", "down"):
                yield expert[name], converted_expert[name]


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def convert_package(source: str | Path, output: str | Path, *, chunk_size: int = 1 * 1024 * 1024) -> dict:
    """Create a new containerized package without modifying *source*."""
    source_root = Path(source).resolve()
    output_root = Path(output).resolve()
    if not source_root.is_dir():
        raise SystemExit("source NPRQ package must be a directory")
    if output_root == source_root or source_root in output_root.parents:
        raise SystemExit("output must be separate from and outside source package")
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit("refusing to write into a non-empty output directory")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = source_root / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("source package is missing manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("complete"):
        raise SystemExit("refusing to containerize an incomplete NPRQ package")
    converted = copy.deepcopy(manifest)
    converted["stage_container"] = "pocket-pack-v1"
    converted["stage_container_chunk_size"] = chunk_size
    referenced: set[Path] = set()
    for record, output_record in _record_pairs(manifest, converted):
        if not isinstance(record, dict):
            raise SystemExit("malformed NPRQ page record")
        directory = _relative(record["directory"])
        meta = meta_from_dict(record["meta"])
        page_root = source_root / directory
        verify_tensor(page_root, meta)
        rewritten: list[str] = []
        for filename, expected_hash in zip(meta.stage_files, meta.stage_sha256):
            if Path(filename).suffix != ".nprq":
                raise SystemExit("source package must contain raw .nprq stages before conversion")
            source_stage = page_root / _relative(filename)
            if source_stage in referenced:
                raise SystemExit(f"duplicate manifest stage reference: {source_stage}")
            referenced.add(source_stage)
            target_name = Path(filename).with_suffix(".prk").name
            target_relative = directory / target_name
            target = output_root / target_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            info = pack(source_stage, target, chunk_size=chunk_size)
            if info.source_sha256 != expected_hash:
                raise SystemExit(f"raw stage hash changed while packing: {source_stage}")
            rewritten.append(target_name)
        output_record["meta"]["stage_files"] = rewritten

    # Copy configuration, tokenizer, router projection, license, and source
    # provenance.  Never copy any stage page except through the manifest above.
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if relative.as_posix() in {"manifest.json", "BUILD_STATE.json"}:
            continue
        if path.suffix in {".nprq", ".prk"}:
            continue
        if relative.parts and relative.parts[0] == "pages" and path.suffix == ".json":
            continue
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    _atomic_json(output_root / "manifest.json", converted)
    return converted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--chunk-size", type=int, default=1 * 1024 * 1024)
    args = parser.parse_args()
    convert_package(args.package, args.output, chunk_size=args.chunk_size)
    print(f"POCKET PACK COMPLETE output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
