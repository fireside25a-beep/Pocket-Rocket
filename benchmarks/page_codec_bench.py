#!/usr/bin/env python3
"""Measure the real Pocket page-codec competition on deterministic fixtures."""
from __future__ import annotations

import argparse
import random
import struct
import time
import zlib

from neuro_inverse.model_pages import PAGE_HEADER, byte_unshuffle, select_page_encoding


def _fixture(kind: str, byte_count: int) -> bytes:
    if kind == "structured32":
        words = (byte_count + 3) // 4
        return b"".join(struct.pack("<I", index) for index in range(words))[:byte_count]
    if kind == "pattern":
        pattern = b"Pocket-Rocket-page-codec-v2\0"
        return (pattern * ((byte_count + len(pattern) - 1) // len(pattern)))[:byte_count]
    if kind == "entropy":
        return random.Random(0x5020).randbytes(byte_count)
    raise ValueError(kind)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--megabytes", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.megabytes < 1 or args.repeats < 1:
        raise SystemExit("--megabytes and --repeats must be positive")
    byte_count = args.megabytes * 1024 * 1024
    for kind in ("structured32", "pattern", "entropy"):
        raw = _fixture(kind, byte_count)
        durations: list[float] = []
        selected = None
        for _ in range(args.repeats):
            started = time.perf_counter()
            selected = select_page_encoding(raw)
            durations.append(time.perf_counter() - started)
        assert selected is not None
        payload = selected.payload
        if selected.codec == 0:
            reconstructed = payload
        else:
            reconstructed = zlib.decompress(payload)
            if selected.codec in (2, 3, 4):
                reconstructed = byte_unshuffle(reconstructed, {2: 2, 3: 4, 4: 8}[selected.codec])
        if reconstructed != raw:
            raise RuntimeError("selected codec failed lossless round trip")
        stored = PAGE_HEADER.size + len(payload)
        exact_ratio = f"{len(raw)}/{stored}"
        mib_per_second = (len(raw) / (1024 * 1024)) / min(durations)
        candidate_text = ",".join(f"{name}:{size}" for name, size in selected.candidates)
        print(
            f"fixture={kind} codec={selected.codec} source_bytes={len(raw)} "
            f"stored_bytes={stored} exact_source_to_stored={exact_ratio} "
            f"best_mib_per_s={mib_per_second:.3f} candidates={candidate_text}"
        )
    print("lossless_verification=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
