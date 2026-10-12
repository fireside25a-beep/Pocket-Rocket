#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.router import HammingRouter
from neuro_inverse.store import ExpertStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experts", type=int, default=10000)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        store = ExpertStore(Path(temp))
        definitions = [{"expert_id": f"e{i:08d}", "description": f"domain {i % 100} operation {i} deterministic capability", "payload": "x"} for i in range(args.experts)]
        store.initialize(definitions)
        router = HammingRouter(store.records)
        samples = []
        checksum = 0
        for i in range(args.queries):
            start = time.perf_counter_ns()
            routes = router.route(f"domain {i % 100} deterministic operation", top_k=3)
            samples.append((time.perf_counter_ns() - start) / 1_000_000)
            checksum ^= int(routes[0].expert.expert_id[1:])
    print(f"experts={args.experts} queries={args.queries} median_ms={statistics.median(samples):.3f} p95_ms={sorted(samples)[max(0, int(len(samples)*.95)-1)]:.3f} checksum={checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

