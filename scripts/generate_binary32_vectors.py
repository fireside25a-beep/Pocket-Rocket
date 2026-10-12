#!/usr/bin/env python3
"""Generate deterministic exact-reference IEEE-754 binary32 vectors."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.binary32_vectors import (  # noqa: E402
    DEFAULT_RANDOM_COUNT,
    DEFAULT_SEED,
    vector_sha256,
    write_vectors,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("tests/data/binary32_vectors.json"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--random-count", type=int, default=DEFAULT_RANDOM_COUNT)
    args = parser.parse_args()
    data = write_vectors(args.output, seed=args.seed, random_count=args.random_count)
    print(f"vectors={args.output} bytes={len(data)} sha256={vector_sha256(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
