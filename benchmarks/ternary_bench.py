#!/usr/bin/env python3
"""Deterministic integer-only timing harness for 256-trit dot products."""
from __future__ import annotations

import argparse
import statistics
import time

from neuro_inverse.ternary_exact import TernaryVector


def _vectors(count: int) -> tuple[list[tuple[int, ...]], list[TernaryVector]]:
    state = 0x9E3779B97F4A7C15
    scalar: list[tuple[int, ...]] = []
    packed: list[TernaryVector] = []
    for _ in range(count * 2):
        values = []
        for _ in range(256):
            state ^= (state << 13) & ((1 << 64) - 1)
            state ^= state >> 7
            state ^= (state << 17) & ((1 << 64) - 1)
            values.append((state % 3) - 1)
        frozen = tuple(values)
        scalar.append(frozen)
        packed.append(TernaryVector.from_trits(frozen))
    return scalar, packed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.pairs < 1 or args.repeats < 1:
        parser.error("pairs and repeats must be positive")
    scalar, packed = _vectors(args.pairs)
    scalar_times: list[int] = []
    packed_times: list[int] = []
    expected = None
    for _ in range(args.repeats):
        started = time.perf_counter_ns()
        scalar_sum = sum(
            sum(a * b for a, b in zip(scalar[2 * index], scalar[2 * index + 1], strict=True))
            for index in range(args.pairs)
        )
        scalar_times.append(time.perf_counter_ns() - started)
        started = time.perf_counter_ns()
        packed_sum = sum(
            packed[2 * index].dot(packed[2 * index + 1]) for index in range(args.pairs)
        )
        packed_times.append(time.perf_counter_ns() - started)
        if scalar_sum != packed_sum or (expected is not None and packed_sum != expected):
            raise RuntimeError("ternary dot implementations disagree")
        expected = packed_sum
    scalar_median = int(statistics.median(scalar_times))
    packed_median = int(statistics.median(packed_times))
    speed_milli = scalar_median * 1000 // packed_median
    print(f"pairs={args.pairs} trits=256 repeats={args.repeats} checksum={expected}")
    print(f"scalar_median_ns={scalar_median}")
    print(f"sign_plane_median_ns={packed_median}")
    print(f"speedup_milli_x={speed_milli}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
