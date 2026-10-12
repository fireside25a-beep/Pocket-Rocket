#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.ds4_runtime import DEFAULT_RSS_CAP, run_context_ladder


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify Pocket Rocket context frontiers from smoke to 8K product"
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--rss-cap-bytes", type=int, default=DEFAULT_RSS_CAP)
    parser.add_argument("--timeout", type=int, default=7200,
                        help="per-frontier timeout in seconds")
    args = parser.parse_args()
    reports = run_context_ladder(args.root, rss_cap_bytes=args.rss_cap_bytes,
                                 timeout=args.timeout)
    print(json.dumps([report.as_dict() for report in reports], indent=2,
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
