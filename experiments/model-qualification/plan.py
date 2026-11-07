#!/usr/bin/env python3
"""Read-only candidate/storage preflight. Never downloads or certifies inference."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neuro_inverse.ds4_runtime import DEFAULT_RSS_CAP, DS4_REVISION
from neuro_inverse.model_target import DEEPSEEK_V4_FLASH

REVIEWED_DS4 = "84cc882352757baf628a1776badf7cc54d584e28"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disk-path", type=Path, default=ROOT)
    args = parser.parse_args()
    manifest = json.loads((HERE / "candidates.json").read_text())
    free = shutil.disk_usage(args.disk_path).free
    reserve = 4 * 1024**3  # Explicit planning allowance, not a runtime measurement.
    target = DEEPSEEK_V4_FLASH.as_dict()
    rows = []
    for candidate in manifest["candidates"]:
        reasons = []
        exact_target = all(candidate[key] == target[target_key] for key, target_key in (
            ("model_id", "model_id"), ("repository", "weight_repository"),
            ("revision", "weight_revision"), ("filename", "weight_filename"),
            ("size_bytes", "weight_size_bytes"), ("sha256", "weight_sha256"),
        ))
        if DS4_REVISION != REVIEWED_DS4:
            reasons.append("ENGINE_REVISION_REQUIRES_NEW_REVIEW")
        elif candidate["id"] != "deepseek-v4-flash-pinned":
            reasons.append("ARCHITECTURE_NOT_SUPPORTED_BY_REVIEWED_DS4")
        if not exact_target:
            reasons.append("NOT_POCKET_ROCKET_PINNED_MODEL")
        if candidate["total_parameters_billions"] <= 90:
            reasons.append("DOES_NOT_MEET_STRICT_OVER_90B_REQUEST")
        if not 25_000_000_000 <= candidate["size_bytes"] <= 35_000_000_000:
            reasons.append("OUTSIDE_PLANNING_BAND_25_TO_35_DECIMAL_GB")
        if candidate["size_bytes"] + reserve > free:
            reasons.append("INSUFFICIENT_DISK_WITH_4_GIB_RESERVE")
        rows.append({
            "candidate": candidate["id"],
            "size_bytes": candidate["size_bytes"],
            "fits_disk_with_reserve": candidate["size_bytes"] + reserve <= free,
            "matches_production_model_pin": exact_target,
            "status": "BLOCKED" if reasons else "NEEDS_MEASUREMENT",
            "blockers": reasons,
            "memory_8gb": "NOT_MEASURED",
            "inference": "NOT_RUN",
            "download_started": False,
        })
    print(json.dumps({
        "kind": "experimental_preflight_not_an_inference_certificate",
        "ds4_revision": DS4_REVISION,
        "requested_total_memory_bytes": 8_000_000_000,
        "production_default_process_rss_cap_bytes": DEFAULT_RSS_CAP,
        "free_disk_bytes": free,
        "disk_reserve_bytes": reserve,
        "planning_assumptions": {
            "minimum_total_parameters_billions_exclusive": 90,
            "roughly_30gb_range_bytes": [25_000_000_000, 35_000_000_000],
            "memory_budget_uses_decimal_gb": True,
        },
        "candidates": rows,
    }, indent=2, sort_keys=True))
    # A preflight is never a successful inference/8-GB qualification.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
