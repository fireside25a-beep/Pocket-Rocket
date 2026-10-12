#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from neuro_inverse.ds4_runtime import (
    DEFAULT_RSS_CAP, PRODUCT_CONTEXT_TOKENS, PRODUCT_MAX_NEW_TOKENS,
    SMOKE_CONTEXT_TOKENS, SMOKE_OUTPUT_TOKENS, run_16gb_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real DeepSeek tokens under the Pocket Rocket RAM gate")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--profile", choices=("smoke", "product"), default="smoke")
    parser.add_argument("--context", type=int)
    parser.add_argument("--tokens", type=int)
    parser.add_argument("--rss-cap-bytes", type=int, default=DEFAULT_RSS_CAP)
    args = parser.parse_args()
    default_context, default_tokens = (
        (SMOKE_CONTEXT_TOKENS, SMOKE_OUTPUT_TOKENS) if args.profile == "smoke"
        else (PRODUCT_CONTEXT_TOKENS, PRODUCT_MAX_NEW_TOKENS)
    )
    context = args.context if args.context is not None else default_context
    tokens = args.tokens if args.tokens is not None else default_tokens
    print(json.dumps(run_16gb_gate(args.root, context_tokens=context, output_tokens=tokens,
                                   rss_cap_bytes=args.rss_cap_bytes).as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
