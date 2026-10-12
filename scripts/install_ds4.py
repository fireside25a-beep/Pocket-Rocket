#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.ds4_runtime import install_ds4


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the pinned DwarfStar runtime")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--target", default="auto", choices=("auto", "cpu"))
    parser.add_argument("--skip-upstream-tests", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install_ds4(args.root, target=args.target, run_tests=not args.skip_upstream_tests), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
