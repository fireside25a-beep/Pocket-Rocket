#!/usr/bin/env python3
"""Build the smallest measured exact NPRQ stage package.

For each page directory this converter measures three real candidates: raw
NPRQ, Pocket Pack, and one shared Flat32 dictionary across the page's stages.
It commits the smallest byte total and records the decision in the manifest.
The source package is verified first and never modified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.flat_dictionary import encode_file, serialize_dictionary, train_dictionary_bounded
from neuro_inverse.nprq import meta_from_dict, verify_tensor
from neuro_inverse.pocket_pack import pack

VALID_CODECS = ("raw", "flat32", "pocket")


def _relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"unsafe package path: {value!r}")
    return path


def _inside(root: Path, relative: str) -> Path:
    """Resolve a manifest path and reject lexical or symlink escapes."""
    path = (root / _relative(relative)).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"unsafe package path: {relative!r}") from exc
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_source(path: Path, expected_size: int, expected_sha256: str) -> None:
    """Recheck a source immediately around candidate generation/copying."""
    try:
        before = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"source stage is not readable: {path}") from exc
    if before != expected_size:
        raise ValueError(f"source stage changed: {path}")
    actual = _file_sha256(path)
    after = path.stat().st_size
    if before != after or actual != expected_sha256:
        raise ValueError(f"source stage changed: {path}")


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


def convert_package(source: str | Path, output: str | Path, *,
                    codecs: tuple[str, ...] = VALID_CODECS,
                    chunk_size: int = 1 * 1024 * 1024) -> dict:
    """Create a verified mixed-container package using measured byte minima."""
    if not codecs or len(set(codecs)) != len(codecs) or any(codec not in VALID_CODECS for codec in codecs):
        raise ValueError("codecs must be a unique non-empty subset of raw, flat32, pocket")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    source_root = Path(source).resolve()
    output_root = Path(output).resolve()
    if not source_root.is_dir():
        raise SystemExit("source NPRQ package must be a directory")
    if output_root == source_root or source_root in output_root.parents:
        raise SystemExit("output must be separate from and outside source package")
    if Path(output).is_symlink():
        raise SystemExit("output path must not be a symlink")
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit("refusing to write into a non-empty output directory")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = source_root / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("source package is missing manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("complete"):
        raise SystemExit("refusing to convert an incomplete NPRQ package")
    converted = copy.deepcopy(manifest)

    pages: dict[Path, list[tuple[dict, dict, object]]] = defaultdict(list)
    referenced: set[Path] = set()
    for record, output_record in _record_pairs(manifest, converted):
        if not isinstance(record, dict) or not isinstance(record.get("directory"), str):
            raise SystemExit("malformed NPRQ page record")
        directory = _relative(record["directory"])
        meta = meta_from_dict(record["meta"])
        page_root = _inside(source_root, directory.as_posix())
        if page_root.is_symlink() or not page_root.is_dir():
            raise SystemExit(f"unsafe or missing NPRQ page directory: {directory}")
        verify_tensor(page_root, meta)
        for filename in meta.stage_files:
            if Path(filename).suffix != ".nprq":
                raise SystemExit("adaptive source must contain raw .nprq stages")
            path = _inside(page_root, filename)
            if path.is_symlink() or not path.is_file():
                raise SystemExit(f"unsafe or missing NPRQ stage: {filename}")
            if path in referenced:
                raise SystemExit(f"duplicate manifest stage reference: {path}")
            referenced.add(path)
        pages[directory].append((record, output_record, meta))

    decisions: dict[str, dict] = {}
    for directory in sorted(pages, key=lambda item: item.as_posix()):
        entries = pages[directory]
        stages: list[tuple[Path, str, str, int]] = []
        for _record, _output_record, meta in entries:
            page_root = _inside(source_root, directory.as_posix())
            for filename, expected in zip(meta.stage_files, meta.stage_sha256):
                path = _inside(page_root, filename)
                size = path.stat().st_size
                _assert_source(path, size, expected)
                stages.append((path, filename, expected, size))
        raw_bytes = sum(size for _path, _filename, _expected, size in stages)
        candidates: dict[str, tuple[int, Path | None, bytes | None]] = {}
        if "raw" in codecs:
            candidates["raw"] = (raw_bytes, None, None)
        with tempfile.TemporaryDirectory(prefix=".adaptive-", dir=output_root) as temp:
            candidate_root = Path(temp)
            if "flat32" in codecs:
                dictionary = train_dictionary_bounded((path for path, _filename, _expected, _size in stages))
                dictionary_bytes = serialize_dictionary(dictionary)
                flat_root = candidate_root / "flat32"
                flat_root.mkdir()
                for path, filename, expected, size in stages:
                    _assert_source(path, size, expected)
                    encode_file(path, flat_root / Path(filename).with_suffix(".f32"), dictionary)
                total = len(dictionary_bytes) + sum(path.stat().st_size for path in flat_root.iterdir())
                candidates["flat32"] = (total, flat_root, dictionary_bytes)
            if "pocket" in codecs:
                pocket_root = candidate_root / "pocket"
                pocket_root.mkdir()
                for path, filename, expected, size in stages:
                    _assert_source(path, size, expected)
                    info = pack(path, pocket_root / Path(filename).with_suffix(".prk"), chunk_size=chunk_size)
                    if info.source_bytes != size or info.source_sha256 != expected:
                        raise ValueError(f"source stage changed during Pocket Pack: {path}")
                total = sum(path.stat().st_size for path in pocket_root.iterdir())
                candidates["pocket"] = (total, pocket_root, None)

            tie_rank = {"raw": 0, "pocket": 1, "flat32": 2}
            selected = min(candidates, key=lambda name: (candidates[name][0], tie_rank[name]))
            selected_bytes, selected_root, dictionary_bytes = candidates[selected]
            for path, _filename, expected, size in stages:
                _assert_source(path, size, expected)
            destination = output_root / directory
            destination.mkdir(parents=True, exist_ok=True)
            if selected == "flat32":
                assert selected_root is not None and dictionary_bytes is not None
                (destination / "_flat32.dict").write_bytes(dictionary_bytes)
            for _record, output_record, meta in entries:
                rewritten: list[str] = []
                for filename in meta.stage_files:
                    if selected == "raw":
                        target_name = filename
                        shutil.copy2(_inside(source_root / directory, filename), destination / target_name)
                    elif selected == "pocket":
                        target_name = Path(filename).with_suffix(".prk").name
                        assert selected_root is not None
                        shutil.copy2(selected_root / target_name, destination / target_name)
                    else:
                        target_name = Path(filename).with_suffix(".f32").name
                        assert selected_root is not None
                        shutil.copy2(selected_root / target_name, destination / target_name)
                    rewritten.append(target_name)
                output_record["meta"]["stage_files"] = rewritten
                verify_tensor(destination, meta_from_dict(output_record["meta"]))
            decisions[directory.as_posix()] = {
                "selected": selected,
                "raw_bytes": raw_bytes,
                "stored_bytes": selected_bytes,
                "ratio": raw_bytes / selected_bytes if selected_bytes else 1.0,
                "candidates": {name: size for name, (size, _root, _dictionary) in candidates.items()},
            }

    for path in source_root.rglob("*"):
        if path.is_symlink():
            raise SystemExit(f"source package contains unsupported symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if relative.as_posix() in {"manifest.json", "BUILD_STATE.json"}:
            continue
        if path.suffix in {".nprq", ".prk", ".f32"}:
            continue
        if relative.parts and relative.parts[0] == "pages" and path.suffix == ".json":
            continue
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    converted["stage_container"] = "adaptive-exact-v1"
    converted["stage_container_codecs"] = list(codecs)
    converted["stage_container_chunk_size"] = chunk_size
    converted["stage_container_decisions"] = decisions
    _atomic_json(output_root / "manifest.json", converted)
    return converted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--codecs", default=",".join(VALID_CODECS))
    parser.add_argument("--chunk-size", type=int, default=1 * 1024 * 1024)
    args = parser.parse_args()
    codecs = tuple(item.strip() for item in args.codecs.split(",") if item.strip())
    converted = convert_package(args.package, args.output, codecs=codecs, chunk_size=args.chunk_size)
    counts: dict[str, int] = defaultdict(int)
    for decision in converted["stage_container_decisions"].values():
        counts[decision["selected"]] += 1
    print(f"ADAPTIVE COMPLETE output={args.output.resolve()} decisions={dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
