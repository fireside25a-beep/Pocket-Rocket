#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DXLC="$ROOT/build/bin/dxlc"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0

check_file() {
  local label="$1"
  local source="$2"
  timeout 20s "$DXLC" check "$source" >/dev/null
  printf 'PASS  source: %s\n' "$label"
  pass=$((pass+1))
}

check_group() {
  local label="$1"
  local entry="$2"
  shift 2
  local directory="$TMP/$label"
  mkdir -p "$directory"
  local source
  for source in "$@"; do
    cp "$source" "$directory/"
  done
  check_file "$label" "$directory/$entry"
}

check_group dxs aegis_dxs_compiler.dxl \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/compiler/dxs/aegis_dxs_core.dxl" \
  "$ROOT/compiler/dxs/aegis_dxs_compiler.dxl"

check_group dxasm aegis_dxasm_compiler.dxl \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/compiler/dxasm/aegis_dxasm_core.dxl" \
  "$ROOT/compiler/dxasm/aegis_dxasm_compiler.dxl"

check_group dxvm aegis_vm.dxl \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/runtime/dxb3/aegis_vm_core.dxl" \
  "$ROOT/runtime/dxb3/aegis_vm.dxl"

check_group dxaudit aegis_audit_native.dxl \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/runtime/dxb3/aegis_audit_native.dxl"

check_group dxs24 aegis24_compiler.dxl \
  "$ROOT/compiler/dxs/profile24/aegis24_common.dxl" \
  "$ROOT/compiler/dxs/profile24/aegis24_compiler.dxl"

check_group dxvm24 aegis24_vm.dxl \
  "$ROOT/compiler/dxs/profile24/aegis24_common.dxl" \
  "$ROOT/runtime/dxb3/aegis24_vm.dxl"

check_file 'DXL lexer foundation' "$ROOT/compiler/dxl/selfhost/lexer_test_main.dxl"
check_file 'DXL parser foundation' "$ROOT/compiler/dxl/selfhost/parser/parser.dxl"
check_file 'DXL object-writer foundation' "$ROOT/compiler/dxl/selfhost/backend/backend_fixture.dxl"
check_file 'DXL integrated frontend foundation' "$ROOT/compiler/dxl/selfhost/full/main.dxl"
check_file 'DXL native core compiler' "$ROOT/compiler/dxl/native/dxl_native_compiler.dxl"

for source in "$ROOT"/stdlib/*.dxl; do
  check_file "stdlib/$(basename "$source")" "$source"
done

for source in "$ROOT"/examples/dxl/*.dxl "$ROOT"/examples/loops/dxl/*.dxl; do
  check_file "example/$(basename "$source")" "$source"
done

printf 'RESULT: %d DXL source groups PASS / 0 FAIL\n' "$pass"
