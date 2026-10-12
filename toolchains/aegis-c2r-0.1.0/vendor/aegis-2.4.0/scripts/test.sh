#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/build/bin"
"$ROOT/scripts/build_toolchain.sh"

pass=0
fail=0
run() {
  local name="$1"; shift
  if "$@" >/tmp/aegis-test.out 2>/tmp/aegis-test.err; then
    printf 'PASS  %s\n' "$name"; pass=$((pass+1))
  else
    printf 'FAIL  %s\n' "$name"; cat /tmp/aegis-test.out; cat /tmp/aegis-test.err >&2; fail=$((fail+1))
  fi
}

run 'DXL check' "$BIN/dxlc" check "$ROOT/examples/dxl/hello.dxl"
run 'DXL run' "$BIN/dxlc" run "$ROOT/examples/dxl/hello.dxl"

mkdir -p "$ROOT/build/tests"
run 'DXS compile via DXL-authored compiler' "$BIN/dxscc" "$ROOT/examples/dxs/arithmetic.dxs" "$ROOT/build/tests/dxs.dxb"
run 'DXS bytecode audit via DXL-authored auditor' "$BIN/dxaudit" "$ROOT/build/tests/dxs.dxb"
run 'DXS execute via DXL-authored VM' "$BIN/dxvm" "$ROOT/build/tests/dxs.dxb" "$ROOT/examples/policy_all.bin" "$ROOT/build/tests/dxs.proof"
run 'DXASM assemble via DXL-authored assembler' "$BIN/dxasm" "$ROOT/examples/dxasm/arithmetic.dxasm" "$ROOT/build/tests/dxasm.dxb"
run 'DXASM execute via DXL-authored VM' "$BIN/dxvm" "$ROOT/build/tests/dxasm.dxb" "$ROOT/examples/policy_all.bin" "$ROOT/build/tests/dxasm.proof"

# Determinism: repeat compilation and compare exact bytecode.
run 'DXS deterministic recompile' "$BIN/dxscc" "$ROOT/examples/dxs/arithmetic.dxs" "$ROOT/build/tests/dxs-2.dxb"
if cmp -s "$ROOT/build/tests/dxs.dxb" "$ROOT/build/tests/dxs-2.dxb"; then printf 'PASS  DXS byte identity\n'; pass=$((pass+1)); else printf 'FAIL  DXS byte identity\n'; fail=$((fail+1)); fi
run 'DXASM deterministic reassemble' "$BIN/dxasm" "$ROOT/examples/dxasm/arithmetic.dxasm" "$ROOT/build/tests/dxasm-2.dxb"
if cmp -s "$ROOT/build/tests/dxasm.dxb" "$ROOT/build/tests/dxasm-2.dxb"; then printf 'PASS  DXASM byte identity\n'; pass=$((pass+1)); else printf 'FAIL  DXASM byte identity\n'; fail=$((fail+1)); fi

printf '\n%d PASS / %d FAIL\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
