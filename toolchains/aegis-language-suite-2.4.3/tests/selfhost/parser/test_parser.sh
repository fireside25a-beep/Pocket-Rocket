#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DXLC="${DXLC:-$ROOT/build/bin/dxlc}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

run_case() {
  local source="$1"
  local expected="$2"
  "$DXLC" check "$source" >/dev/null
  "$DXLC" run "$source" >"$TMP/out"
  if [[ "$(tr -d '\r' <"$TMP/out")" != "$expected" ]]; then
    printf 'FAIL %s\n' "$(basename "$source")" >&2
    cat "$TMP/out" >&2
    return 1
  fi
  printf 'PASS %s\n' "$(basename "$source")"
}

run_case "$ROOT/tests/selfhost/parser/positive_foundation.dxl" $'5\n2\n0\n986115\ntrue'
run_case "$ROOT/tests/selfhost/parser/negative_declaration_recovery.dxl" $'2\n1202\n1205\n5\n1134078\ntrue'
run_case "$ROOT/tests/selfhost/parser/negative_statement_recovery.dxl" $'2\n1203\n1205\n6\n31612256\ntrue'
run_case "$ROOT/tests/selfhost/parser/synchronization_progress.dxl" $'2\n2\ntrue'
run_case "$ROOT/tests/selfhost/parser/arena_bounds.dxl" $'3201\n3101\n3005'

repeat_source="$ROOT/tests/selfhost/parser/positive_foundation.dxl"
"$DXLC" build "$repeat_source" -o "$TMP/positive-a" >/dev/null
"$DXLC" build "$repeat_source" -o "$TMP/positive-b" >/dev/null
cmp "$TMP/positive-a" "$TMP/positive-b"
"$TMP/positive-a" >"$TMP/positive-a.out"
"$TMP/positive-b" >"$TMP/positive-b.out"
cmp "$TMP/positive-a.out" "$TMP/positive-b.out"
printf 'PASS deterministic_repeat_build\n'

printf 'RESULT: 6 PASS / 0 FAIL\n'
