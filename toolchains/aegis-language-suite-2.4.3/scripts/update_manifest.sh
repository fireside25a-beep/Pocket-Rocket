#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$ROOT/SHA256SUMS.txt.new"

(
  cd "$ROOT"
  find . \
    -path './build' -prune -o \
    -path './dist' -prune -o \
    -path './.git' -prune -o \
    -path './SHA256SUMS.txt' -prune -o \
    -path './SHA256SUMS.txt.new' -prune -o \
    -type f -print0 |
    LC_ALL=C sort -z |
    xargs -0 sha256sum
) >"$temporary"

mv "$temporary" "$ROOT/SHA256SUMS.txt"
printf 'repository manifest updated: %s\n' "$ROOT/SHA256SUMS.txt"
