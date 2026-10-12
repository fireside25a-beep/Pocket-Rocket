#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DXLC="$ROOT/build/bin/dxlc"
[[ -x "$DXLC" ]] || "$ROOT/scripts/bootstrap.sh"
mkdir -p "$ROOT/build/bin" "$ROOT/build/bootstrap-src"

build_group() {
  local name="$1" entry="$2" out="$3"; shift 3
  local dir="$ROOT/build/bootstrap-src/$name"
  rm -rf "$dir"; mkdir -p "$dir"
  local f
  for f in "$@"; do cp "$f" "$dir/"; done
  "$DXLC" build "$dir/$entry" -o "$ROOT/build/bin/$out"
}

# DXS compiler written in DXL
build_group dxs aegis_dxs_compiler.dxl dxscc \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/compiler/dxs/aegis_dxs_core.dxl" \
  "$ROOT/compiler/dxs/aegis_dxs_compiler.dxl"

# DXASM assembler written in DXL
build_group dxasm aegis_dxasm_compiler.dxl dxasm \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/compiler/dxasm/aegis_dxasm_core.dxl" \
  "$ROOT/compiler/dxasm/aegis_dxasm_compiler.dxl"

# DXB3 VM and auditor written in DXL
build_group vm aegis_vm.dxl dxvm \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/runtime/dxb3/aegis_vm_core.dxl" \
  "$ROOT/runtime/dxb3/aegis_vm.dxl"

build_group audit aegis_audit_native.dxl dxaudit \
  "$ROOT/runtime/dxb3/aegis_common.dxl" \
  "$ROOT/runtime/dxb3/aegis_audit_native.dxl"

# Extended 2.4 DXS compiler + VM foundation, also authored in DXL
build_group dxs24 aegis24_compiler.dxl dxs24cc \
  "$ROOT/compiler/dxl/aegis24_common.dxl" \
  "$ROOT/compiler/dxl/aegis24_compiler.dxl"

build_group vm24 aegis24_vm.dxl dxvm24 \
  "$ROOT/compiler/dxl/aegis24_common.dxl" \
  "$ROOT/runtime/dxb3/aegis24_vm.dxl"

printf 'toolchain built in %s\n' "$ROOT/build/bin"
