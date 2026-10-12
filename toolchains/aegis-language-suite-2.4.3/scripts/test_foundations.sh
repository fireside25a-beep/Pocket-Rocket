#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DXLC="$ROOT/toolchain/linux-x86_64/libexec/dxlc-front"

suites=(
  "tests/selfhost/run_lexer_tests.sh"
  "tests/selfhost/parser/test_parser.sh"
  "tests/selfhost/backend/test_backend.sh"
)

for suite in "${suites[@]}"; do
  path="$ROOT/$suite"
  if [[ ! -x "$path" ]]; then
    printf 'foundation gate missing executable runner: %s\n' "$suite" >&2
    exit 1
  fi
  printf '\n== %s ==\n' "$suite"
  timeout 60s "$path"
done

printf '\nselfhost foundation suites: PASS\n'
