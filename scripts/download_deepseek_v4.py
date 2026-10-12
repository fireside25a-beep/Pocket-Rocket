#!/usr/bin/env python3
"""Download and verify the pinned DeepSeek V4 Flash GGUF.

The downloader accepts exactly one immutable revision and one exact file from
the public DwarfStar-compatible repository. It never falls back to another
model file and never publishes a partial download.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.model_target import DEEPSEEK_V4_FLASH, verify_weight_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as exc:
        raise SystemExit("Install first: pip install -e '.[deepseek]'") from exc

    api = HfApi()
    info = api.model_info(DEEPSEEK_V4_FLASH.weight_repository,
                          revision=DEEPSEEK_V4_FLASH.weight_revision,
                          files_metadata=True)
    if info.sha != DEEPSEEK_V4_FLASH.weight_revision:
        raise SystemExit(f"Hub resolved unexpected revision: {info.sha!r}")
    matches = [item for item in info.siblings or []
               if item.rfilename == DEEPSEEK_V4_FLASH.weight_filename]
    if len(matches) != 1:
        raise SystemExit("Pinned DeepSeek GGUF is not present exactly once in the repository")
    sibling = matches[0]
    hub_size = getattr(sibling, "size", None)
    if hub_size is not None and hub_size != DEEPSEEK_V4_FLASH.weight_size_bytes:
        raise SystemExit(f"Hub metadata size mismatch: {hub_size}")
    hub_hash = getattr(getattr(sibling, "lfs", None), "sha256", None)
    if hub_hash is not None and hub_hash != DEEPSEEK_V4_FLASH.weight_sha256:
        raise SystemExit("Hub LFS SHA-256 differs from the pinned source contract")

    destination = args.root / "models" / "DeepSeek-V4-Flash"
    destination.mkdir(parents=True, exist_ok=True)
    path = Path(hf_hub_download(
        repo_id=DEEPSEEK_V4_FLASH.weight_repository,
        filename=DEEPSEEK_V4_FLASH.weight_filename,
        revision=DEEPSEEK_V4_FLASH.weight_revision,
        local_dir=destination,
    ))
    report = verify_weight_file(path)
    manifest = {
        "format": 1,
        "target": DEEPSEEK_V4_FLASH.as_dict(),
        "source": "huggingface_hub",
        "verification": report,
    }
    manifest_path = args.root / "var" / "DeepSeek-V4-Flash-OFFICIAL-SOURCE-MANIFEST.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "NEUROROUTE_OFFICIAL_SOURCE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"VERIFIED {DEEPSEEK_V4_FLASH.model_id} weights")
    print(f"File: {path}\nBytes: {report['size_bytes']}\nSHA-256: {report['sha256']}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
