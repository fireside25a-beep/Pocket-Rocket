#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if grep -RniE --exclude-dir=.git --exclude-dir=build 'd[e]xr' "$ROOT"; then
  echo 'legacy branding found' >&2
  exit 1
fi
echo 'brand hygiene: PASS'
