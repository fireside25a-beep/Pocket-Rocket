#!/usr/bin/env python3
"""Report flat32 arithmetic without reading or modifying codec files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.flat32_accounting import (
    RECALLED_REGISTERED, RECALLED_RAW, RECALLED_TOTAL, estimate_flat32,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", type=int, default=RECALLED_TOTAL)
    parser.add_argument("--registered", type=int, default=RECALLED_REGISTERED)
    parser.add_argument("--dictionary", type=int, default=256)
    parser.add_argument("--header-bytes", type=int, default=32)
    parser.add_argument("--tail-bytes", type=int, default=32)
    parser.add_argument("--target-stream-ratio", type=float, default=4.744675)
    parser.add_argument("--target-dictionary-ratio", type=float, default=1.602698)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        estimate = estimate_flat32(
            args.blocks, args.registered, dictionary_entries=args.dictionary,
            header_bytes=args.header_bytes, tail_bytes=args.tail_bytes,
            target_stream_ratio=args.target_stream_ratio,
            target_dictionary_ratio=args.target_dictionary_ratio,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    if args.as_json:
        print(json.dumps(estimate.as_dict(), indent=2, sort_keys=True))
        return 0
    print(f"N={estimate.total_blocks:,} R={estimate.registered_blocks:,} F={estimate.raw_blocks:,} D={estimate.dictionary_entries}")
    print(f"stream bytes: {estimate.stream_bytes:,}; ratio: {estimate.stream_ratio:.9f}x")
    print(f"dictionary-inclusive bytes: {estimate.dictionary_inclusive_bytes:,}; ratio: {estimate.dictionary_inclusive_ratio:.9f}x")
    print(f"coverage: {estimate.registered_coverage:.6%}")
    print(f"break-even registered blocks: stream={estimate.break_even_registered_stream:,} "
          f"({estimate.break_even_coverage_stream:.6%}), dictionary={estimate.break_even_registered_dictionary:,} "
          f"({estimate.break_even_coverage_dictionary:.6%})")
    print(f"with R fixed, largest break-even N: stream={estimate.break_even_total_blocks_stream:,}, "
          f"dictionary={estimate.break_even_total_blocks_dictionary:,}")
    print(f"target stream {estimate.target_stream_ratio:.6f}x requires extra bytes beyond formula: {estimate.target_stream_extra_bytes:.3f}")
    print(f"target dictionary {estimate.target_dictionary_ratio:.6f}x requires extra bytes beyond stream: {estimate.target_dictionary_extra_bytes:.3f}")
    print(f"after 32D dictionary bytes, unaccounted bytes: {estimate.target_dictionary_unaccounted_bytes:.3f}")
    print("No codec framing or dictionary bytes beyond the stated formula are assumed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
