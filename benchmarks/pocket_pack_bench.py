#!/usr/bin/env python3
"""Measure Pocket Pack lossless container ratio and local throughput."""
from __future__ import annotations

import argparse
import random
import tempfile
import time
from pathlib import Path

from neuro_inverse.pocket_pack import PocketRocketReader, pack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--megabytes", type=int, default=32)
    parser.add_argument("--chunk-size", type=int, default=1 * 1024 * 1024)
    parser.add_argument("--random", action="store_true", help="Use deterministic pseudo-random bytes")
    args = parser.parse_args()
    if args.megabytes < 1:
        raise SystemExit("--megabytes must be positive")
    source_bytes = args.megabytes * 1024 * 1024
    if args.random:
        # A deterministic stream makes runs comparable without relying on a
        # network/model fixture.  os.urandom is deliberately not used here.
        source = random.Random(20260817).randbytes(source_bytes)
    else:
        pattern = b"Pocket Pack measured lossless NPRQ stage bytes\n"
        source = (pattern * ((source_bytes + len(pattern) - 1) // len(pattern)))[:source_bytes]
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "bench.pkr"
        started = time.perf_counter()
        info = pack(source, output, chunk_size=args.chunk_size)
        pack_seconds = time.perf_counter() - started
        started = time.perf_counter()
        with PocketRocketReader(output) as reader:
            reader.verify()
        read_seconds = time.perf_counter() - started
    ratio = info.container_bytes / max(info.source_bytes, 1)
    source_mb = info.source_bytes / (1024 * 1024)
    print(f"source_mib={source_mb:.3f}")
    print(f"container_mib={info.container_bytes / (1024 * 1024):.3f}")
    print(f"container_to_source_ratio={ratio:.6f}")
    print(f"pack_mib_per_s={source_mb / max(pack_seconds, 1e-12):.3f}")
    print(f"verify_mib_per_s={source_mb / max(read_seconds, 1e-12):.3f}")
    print("lossless_verification=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
