#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/build/bin"
PROOFS="$ROOT/proofs/loops"
EXPECTED="$ROOT/tests/matrix/loops/expected.out"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/scripts/setup.sh" >/dev/null
mkdir -p "$PROOFS"
cd "$ROOT"

pass=0
check() {
  local name="$1"
  shift
  if timeout 30s "$@"; then
    printf 'PASS  %s\n' "$name"
    pass=$((pass+1))
  else
    printf 'FAIL  %s\n' "$name" >&2
    exit 1
  fi
}

DXL_SOURCE="examples/loops/dxl/counter.dxl"
DXL_NATIVE_SOURCE="examples/loops/dxl/native_counter.dxl"
DXS_SOURCE="examples/loops/dxs/counter.dxs"
DXASM_SOURCE="examples/loops/dxasm/counter.dxasm"
POLICY="examples/policy_all.bin"

check 'matrix case inventory' awk -F '\t' '
  NR == 1 { ok = ($1 == "language" && $2 == "source" && $3 == "verification" && $4 == "expected") }
  NR > 1 { seen[$1]++; expected[$1] = $4 }
  END {
    exit !(ok && NR == 5 && seen["DXL"] == 1 && seen["DXL-native"] == 1 &&
      seen["DXS"] == 1 && seen["DXASM"] == 1 && expected["DXL"] == "10" &&
      expected["DXL-native"] == "10" && expected["DXS"] == "10" && expected["DXASM"] == "10")
  }
' tests/matrix/loops/cases.tsv

check 'DXL source check A' bash -c '"$1" check "$2" >"$3" 2>&1' _ "$BIN/dxlc" "$DXL_SOURCE" "$PROOFS/dxl-counter.check"
check 'DXL source check B' bash -c '"$1" check "$2" >"$3" 2>&1' _ "$BIN/dxlc" "$DXL_SOURCE" "$TMP/dxl-counter-repeat.check"
check 'DXL check identity' cmp "$PROOFS/dxl-counter.check" "$TMP/dxl-counter-repeat.check"
check 'DXL TIR A' "$BIN/dxlc" emit-tir "$DXL_SOURCE" -o "$PROOFS/dxl-counter.tir"
check 'DXL TIR B' "$BIN/dxlc" emit-tir "$DXL_SOURCE" -o "$TMP/dxl-counter-repeat.tir"
check 'DXL TIR identity' cmp "$PROOFS/dxl-counter.tir" "$TMP/dxl-counter-repeat.tir"
check 'DXL loop result represented' grep -Fq 'const loop_result : i64' "$PROOFS/dxl-counter.tir"

check 'DXL native build A' "$BIN/dxlc" build "$DXL_NATIVE_SOURCE" -o "$PROOFS/dxl-native-counter.bin"
check 'DXL native build B' "$BIN/dxlc" build "$DXL_NATIVE_SOURCE" -o "$TMP/dxl-native-counter-repeat.bin"
check 'DXL native executable identity' cmp "$PROOFS/dxl-native-counter.bin" "$TMP/dxl-native-counter-repeat.bin"
check 'DXL native static ELF' bash -c '
  file "$1" | grep -q "ELF 64-bit LSB executable.*statically linked.*no section header" &&
  [[ $(readelf -W -l "$1" | grep -c "^[[:space:]]*LOAD") -eq 1 ]] &&
  readelf -W -l "$1" | awk '\''$1 == "GNU_STACK" { found = 1; if ($7 != "RW") exit 1 } END { if (!found) exit 1 }'\'' &&
  ! readelf -l "$1" | grep -q INTERP &&
  ! readelf -d "$1" 2>&1 | grep -q NEEDED
' _ "$PROOFS/dxl-native-counter.bin"
check 'DXL native execute A' bash -c '"$1" >"$2"' _ "$PROOFS/dxl-native-counter.bin" "$PROOFS/dxl-native-counter.out"
check 'DXL native execute B' bash -c '"$1" >"$2"' _ "$TMP/dxl-native-counter-repeat.bin" "$TMP/dxl-native-counter-repeat.out"
check 'DXL native repeat-output identity' cmp "$PROOFS/dxl-native-counter.out" "$TMP/dxl-native-counter-repeat.out"
check 'DXL native expected output' cmp "$PROOFS/dxl-native-counter.out" "$EXPECTED"

native_sha256="$(sha256sum "$PROOFS/dxl-native-counter.bin" | awk '{print $1}')"
{
  printf 'artifact\tdxl-native-counter.bin\n'
  printf 'format\tELF64 little-endian\n'
  printf 'type\tET_EXEC\n'
  printf 'machine\tx86-64\n'
  printf 'load_segments\t1\n'
  printf 'interpreter\tnone\n'
  printf 'dynamic_dependencies\tnone\n'
  printf 'stack\tread-write non-executable\n'
  printf 'sha256\t%s\n' "$native_sha256"
} >"$PROOFS/dxl-native-counter.audit"
check 'DXL native evidence audit' awk -F '\t' '
  $1 == "format" && $2 == "ELF64 little-endian" { format = 1 }
  $1 == "type" && $2 == "ET_EXEC" { type = 1 }
  $1 == "machine" && $2 == "x86-64" { machine = 1 }
  $1 == "interpreter" && $2 == "none" { interpreter = 1 }
  $1 == "dynamic_dependencies" && $2 == "none" { dynamic = 1 }
  $1 == "stack" && $2 == "read-write non-executable" { stack = 1 }
  END { exit !(format && type && machine && interpreter && dynamic && stack) }
' "$PROOFS/dxl-native-counter.audit"

check 'DXS compile A' "$BIN/dxscc" "$DXS_SOURCE" "$PROOFS/dxs-counter.dxb"
check 'DXS compile B' "$BIN/dxscc" "$DXS_SOURCE" "$TMP/dxs-counter-repeat.dxb"
check 'DXS bytecode identity' cmp "$PROOFS/dxs-counter.dxb" "$TMP/dxs-counter-repeat.dxb"
check 'DXS audit' bash -c '"$1" "$2" >"$3"' _ "$BIN/dxaudit" "$PROOFS/dxs-counter.dxb" "$PROOFS/dxs-counter.audit"
check 'DXS execute A' bash -c '"$1" "$2" "$3" "$4" >"$5"' _ "$BIN/dxvm" "$PROOFS/dxs-counter.dxb" "$POLICY" "$PROOFS/dxs-counter.proof" "$PROOFS/dxs-counter.out"
check 'DXS execute B' bash -c '"$1" "$2" "$3" "$4" >"$5"' _ "$BIN/dxvm" "$TMP/dxs-counter-repeat.dxb" "$POLICY" "$TMP/dxs-counter-repeat.proof" "$TMP/dxs-counter-repeat.out"
check 'DXS proof identity' cmp "$PROOFS/dxs-counter.proof" "$TMP/dxs-counter-repeat.proof"
check 'DXS repeat-output identity' cmp "$PROOFS/dxs-counter.out" "$TMP/dxs-counter-repeat.out"
check 'DXS expected output' cmp "$PROOFS/dxs-counter.out" "$EXPECTED"

check 'DXASM assemble A' "$BIN/dxasm" "$DXASM_SOURCE" "$PROOFS/dxasm-counter.dxb"
check 'DXASM assemble B' "$BIN/dxasm" "$DXASM_SOURCE" "$TMP/dxasm-counter-repeat.dxb"
check 'DXASM bytecode identity' cmp "$PROOFS/dxasm-counter.dxb" "$TMP/dxasm-counter-repeat.dxb"
check 'DXASM audit' bash -c '"$1" "$2" >"$3"' _ "$BIN/dxaudit" "$PROOFS/dxasm-counter.dxb" "$PROOFS/dxasm-counter.audit"
check 'DXASM execute A' bash -c '"$1" "$2" "$3" "$4" >"$5"' _ "$BIN/dxvm" "$PROOFS/dxasm-counter.dxb" "$POLICY" "$PROOFS/dxasm-counter.proof" "$PROOFS/dxasm-counter.out"
check 'DXASM execute B' bash -c '"$1" "$2" "$3" "$4" >"$5"' _ "$BIN/dxvm" "$TMP/dxasm-counter-repeat.dxb" "$POLICY" "$TMP/dxasm-counter-repeat.proof" "$TMP/dxasm-counter-repeat.out"
check 'DXASM proof identity' cmp "$PROOFS/dxasm-counter.proof" "$TMP/dxasm-counter-repeat.proof"
check 'DXASM repeat-output identity' cmp "$PROOFS/dxasm-counter.out" "$TMP/dxasm-counter-repeat.out"
check 'DXASM expected output' cmp "$PROOFS/dxasm-counter.out" "$EXPECTED"

check 'DXS and DXASM semantic output identity' cmp "$PROOFS/dxs-counter.out" "$PROOFS/dxasm-counter.out"
check 'DXL native and DXB3 semantic output identity' cmp "$PROOFS/dxl-native-counter.out" "$PROOFS/dxs-counter.out"
check 'DXS and DXASM payload identity' cmp --ignore-initial=40 "$PROOFS/dxs-counter.dxb" "$PROOFS/dxasm-counter.dxb"
check 'DXS and DXASM proof identity' cmp "$PROOFS/dxs-counter.proof" "$PROOFS/dxasm-counter.proof"

printf 'language\tsource\tresult\tevidence\n' >"$PROOFS/MATRIX_RESULTS.tsv"
printf 'DXL\texamples/loops/dxl/counter.dxl\tPASS\tdxl-counter.check + dxl-counter.tir\n' >>"$PROOFS/MATRIX_RESULTS.tsv"
printf 'DXL-native\texamples/loops/dxl/native_counter.dxl\tPASS\tdxl-native-counter.bin + .audit + .out\n' >>"$PROOFS/MATRIX_RESULTS.tsv"
printf 'DXS\texamples/loops/dxs/counter.dxs\tPASS\tdxs-counter.proof\n' >>"$PROOFS/MATRIX_RESULTS.tsv"
printf 'DXASM\texamples/loops/dxasm/counter.dxasm\tPASS\tdxasm-counter.proof\n' >>"$PROOFS/MATRIX_RESULTS.tsv"

(
  cd "$PROOFS"
  sha256sum \
    ../../examples/loops/dxl/counter.dxl \
    ../../examples/loops/dxl/native_counter.dxl \
    ../../examples/loops/dxs/counter.dxs \
    ../../examples/loops/dxasm/counter.dxasm \
    ../../tests/matrix/loops/cases.tsv \
    ../../tests/matrix/loops/expected.out \
    dxl-counter.check \
    dxl-counter.tir \
    dxl-native-counter.bin \
    dxl-native-counter.audit \
    dxl-native-counter.out \
    dxs-counter.dxb \
    dxs-counter.audit \
    dxs-counter.proof \
    dxs-counter.out \
    dxasm-counter.dxb \
    dxasm-counter.audit \
    dxasm-counter.proof \
    dxasm-counter.out \
    MATRIX_RESULTS.tsv >SHA256SUMS.txt
)

check 'proof manifest verification' bash -c 'cd "$1" && sha256sum -c SHA256SUMS.txt >/dev/null' _ "$PROOFS"

printf 'RESULT: %d PASS / 0 FAIL\n' "$pass"
