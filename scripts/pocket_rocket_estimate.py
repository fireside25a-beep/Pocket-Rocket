#!/usr/bin/env python3
"""Print DeepSeek V4 Flash Pocket Rocket byte accounting."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.pocket_rocket import (
    DEEPSEEK_V4_FLASH_GEOMETRY, GIB, estimate_deepseek_v4_flash,
    strict_16gb_admission,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bits-per-param", type=float, default=4.0)
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--scale-bytes", type=int, default=2)
    parser.add_argument("--zero-point-bytes", type=int, default=0)
    parser.add_argument("--resident-common-params", type=int, default=0)
    parser.add_argument("--cache-gib", type=float, default=1.0)
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--kv-bytes-per-element", type=int, default=4,
                        help="must be 4 for the pinned ds4 CPU context buffers")
    parser.add_argument("--runtime-overhead-mib", type=float, default=0.0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        if args.cache_gib < 0:
            raise ValueError("--cache-gib must be non-negative")
        if args.runtime_overhead_mib < 0:
            raise ValueError("--runtime-overhead-mib must be non-negative")
        cache_bytes = int(args.cache_gib * GIB)
        overhead_bytes = int(args.runtime_overhead_mib * 1024**2)
        estimate = estimate_deepseek_v4_flash(
            DEEPSEEK_V4_FLASH_GEOMETRY,
            bits_per_param=args.bits_per_param,
            block_size=args.block_size,
            scale_bytes=args.scale_bytes,
            zero_point_bytes=args.zero_point_bytes,
            resident_common_params=args.resident_common_params,
            cache_budget_bytes=cache_bytes,
            context_tokens=args.context,
            batch_size=args.batch_size,
            kv_bytes_per_element=args.kv_bytes_per_element,
            runtime_overhead_bytes=overhead_bytes,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        parser.error(str(exc))
    if args.as_json:
        print(json.dumps(estimate.as_dict(), indent=2, sort_keys=True))
        return 0
    print(f"basis: {estimate.basis}")
    print(f"measurement: {estimate.measurement_status}")
    total = "unknown (not inferred from GGUF)" if estimate.geometry.total_params is None else f"{estimate.geometry.total_params:,}"
    active = "unknown (not inferred from GGUF)" if estimate.geometry.active_params is None else f"{estimate.geometry.active_params:,}"
    print(f"geometry: {total} total / {active} active params; "
          f"{estimate.geometry.expert_count} routed experts, {estimate.geometry.active_experts} active, {estimate.geometry.layers} layers")
    print(f"full SSD estimate: {estimate.full_ssd_bytes / GIB:.2f} GiB")
    print(f"active weight RAM: {estimate.active_weight_ram_bytes / GIB:.2f} GiB")
    print(f"  resident common: {estimate.resident_common_bytes / GIB:.2f} GiB")
    print(f"  active expert pages: {estimate.active_expert_page_bytes / GIB:.2f} GiB")
    print(f"KV cache: {estimate.kv_cache_bytes / GIB:.3f} GiB")
    print(f"context scratch: {estimate.context_scratch_bytes / GIB:.6f} GiB")
    print(f"context buffers: {estimate.context_buffer_bytes / GIB:.3f} GiB")
    print(f"context basis: {estimate.context_memory_basis}")
    print(f"working-set RAM: {estimate.working_set_ram_bytes / GIB:.2f} GiB")
    print(f"active RAM basis: {estimate.active_ram_basis}")
    admission = strict_16gb_admission(estimate)
    print(f"strict 16-GiB admission: {'ADMIT' if admission['admitted'] else 'REJECT'} "
          f"(margin {int(admission['margin_bytes']) / GIB:+.2f} GiB)")
    for budget in estimate.budgets:
        state = "FIT" if budget.fits else "DOES NOT FIT"
        print(f"{budget.budget_gib} GiB RAM: {state} (margin {budget.margin_bytes / GIB:+.2f} GiB)")
    print("No speed, quality, or hardware-measured feasibility is inferred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
