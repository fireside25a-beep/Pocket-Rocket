#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.host_preflight import inspect_host, require_cpu_host


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Pocket Rocket CPU preflight")
    parser.add_argument("--require", action="store_true", help="fail unless Linux x86-64-v1 is available")
    args = parser.parse_args()
    report = inspect_host()
    if args.require:
        require_cpu_host(report)
    payload = report.as_dict()
    payload["certificate_sha256"] = report.certificate_sha256
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
