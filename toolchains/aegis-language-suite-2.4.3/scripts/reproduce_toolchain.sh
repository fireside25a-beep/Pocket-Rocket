#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEED="$ROOT/toolchain/linux-x86_64/libexec/dxlc-front"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT HUP INT TERM

[[ -x "$SEED" ]] || {
  printf 'toolchain reproduction failed: compatibility frontend is missing\n' >&2
  exit 1
}

pass=0

report_match() {
  local label="$1" built="$2" shipped="$3"
  cmp -s "$built" "$shipped" || {
    printf 'FAIL  %s differs from shipped executable\n' "$label" >&2
    exit 1
  }
  printf 'PASS  %-14s %s\n' "$label" "$(sha256sum "$built" | awk '{print $1}')"
  pass=$((pass + 1))
}

build_group() {
  local label="$1" entry="$2" shipped="$3"
  shift 3
  local directory="$WORK/$label" source output_a output_b
  mkdir -p "$directory"
  for source in "$@"; do cp "$source" "$directory/"; done
  output_a="$WORK/$label-a"
  output_b="$WORK/$label-b"
  timeout 90s "$SEED" build "$directory/$entry" -o "$output_a" >/dev/null
  timeout 90s "$SEED" build "$directory/$entry" -o "$output_b" >/dev/null
  cmp -s "$output_a" "$output_b" || {
    printf 'FAIL  %s repeat builds differ\n' "$label" >&2
    exit 1
  }
  report_match "$label" "$output_a" "$shipped"
}

build_group dxscc aegis_dxs_compiler.dxl "$ROOT/toolchain/linux-x86_64/bin/dxscc" \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/compiler/dxs/aegis_dxs_core.dxl" \
  "$ROOT/compiler/dxs/aegis_dxs_compiler.dxl"

build_group dxasm aegis_dxasm_compiler.dxl "$ROOT/toolchain/linux-x86_64/bin/dxasm" \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/compiler/dxasm/aegis_dxasm_core.dxl" \
  "$ROOT/compiler/dxasm/aegis_dxasm_compiler.dxl"

build_group dxvm aegis_vm.dxl "$ROOT/toolchain/linux-x86_64/bin/dxvm" \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/runtime/dxb3/aegis_vm_core.dxl" \
  "$ROOT/runtime/dxb3/aegis_vm.dxl"

build_group dxaudit aegis_audit_native.dxl "$ROOT/toolchain/linux-x86_64/bin/dxaudit" \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/runtime/dxb3/aegis_audit_native.dxl"

build_group dxs24cc aegis24_compiler.dxl "$ROOT/toolchain/linux-x86_64/bin/dxs24cc" \
  "$ROOT/compiler/dxs/profile24/aegis24_common.dxl" \
  "$ROOT/compiler/dxs/profile24/aegis24_compiler.dxl"

build_group dxvm24 aegis24_vm.dxl "$ROOT/toolchain/linux-x86_64/bin/dxvm24" \
  "$ROOT/compiler/dxs/profile24/aegis24_common.dxl" \
  "$ROOT/runtime/dxb3/aegis24_vm.dxl"

native_a="$WORK/dxlc-native-a"
native_b="$WORK/dxlc-native-b"
timeout 90s "$SEED" build "$ROOT/compiler/dxl/native/dxl_native_compiler.dxl" -o "$native_a" >/dev/null
timeout 90s "$SEED" build "$ROOT/compiler/dxl/native/dxl_native_compiler.dxl" -o "$native_b" >/dev/null
cmp -s "$native_a" "$native_b" || {
  printf 'FAIL  dxlc-native repeat builds differ\n' >&2
  exit 1
}
report_match dxlc-native "$native_a" "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native"

printf 'RESULT: %d DXL-authored tool rebuilds match / 0 mismatches\n' "$pass"
