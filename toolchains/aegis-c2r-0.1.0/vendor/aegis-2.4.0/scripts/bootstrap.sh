#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/build/bin"
CC_BIN="${CC:-cc}"
"$CC_BIN" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  -I"$ROOT/bootstrap" "$ROOT/bootstrap/dxlc_stage0.c" -o "$ROOT/build/bin/dxlc"
printf 'stage-zero DXL compiler: %s\n' "$ROOT/build/bin/dxlc"
