#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import time

from neuro_inverse.agent_fabric import route_cells


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=int, default=1000)
    args = parser.parse_args()
    if args.queries < 1:
        parser.error("--queries must be positive")
    samples: list[int] = []
    checksum = 0
    roles = ("planner", "analyst", "solver", "critic", "verifier", "optimizer",
             "integrator", "synthesizer")
    for index in range(args.queries):
        started = time.perf_counter_ns()
        routes = route_cells(
            f"query {index} audit parser storage exact evidence", role=roles[index % len(roles)],
            count=3,
        )
        samples.append(time.perf_counter_ns() - started)
        checksum += sum(route.cell.cell_id + route.distance for route in routes)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (len(ordered) * 95) // 100)]
    print(
        f"cells=1024 queries={args.queries} quorum=3 "
        f"median_ns={int(statistics.median(samples))} p95_ns={p95} checksum={checksum}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
