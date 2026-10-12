#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DXLC="${DXLC:-$ROOT/build/bin/dxlc}"
SOURCE="$ROOT/compiler/dxl/selfhost/backend/backend_fixture.dxl"
SMALL_BUFFER="$ROOT/tests/selfhost/backend/backend_small_buffer.dxl"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$DXLC" check "$SOURCE"
"$DXLC" build "$SOURCE" -o "$TMP/backend-fixture"
"$DXLC" run "$SMALL_BUFFER"
"$TMP/backend-fixture" "$TMP/a.o"
"$TMP/backend-fixture" "$TMP/b.o"

set +e
bad_arguments_output="$("$TMP/backend-fixture" 2>&1)"
bad_arguments_rc=$?
write_failure_output="$("$TMP/backend-fixture" "$TMP/missing/output.o" 2>&1)"
write_failure_rc=$?
set -e
test "$bad_arguments_rc" -eq 2
test "$bad_arguments_output" = '2503'
test "$write_failure_rc" -eq 1
test "$write_failure_output" = '2502'

cmp "$TMP/a.o" "$TMP/b.o"
file "$TMP/a.o" | grep -Eq 'ELF 64-bit LSB relocatable, x86-64'
readelf -h "$TMP/a.o" | grep -Eq 'Type:[[:space:]]+REL'
readelf -h "$TMP/a.o" | grep -Eq 'Machine:[[:space:]]+Advanced Micro Devices X86-64'

for section in .text .rodata .rela.text .symtab .strtab .shstrtab .debug_line .rela.debug_line .note.GNU-stack; do
    readelf -SW "$TMP/a.o" | grep -Fq "$section"
done

readelf -sW "$TMP/a.o" | grep -Eq 'FUNC[[:space:]]+GLOBAL.*main$'
readelf -rW "$TMP/a.o" | grep -Fq 'R_X86_64_64'
readelf -rW "$TMP/a.o" | grep -Fq '.text + 0'
readelf --debug-dump=decodedline "$TMP/a.o" | grep -Fq 'backend_fixture.dxl'
objdump -dr "$TMP/a.o" | grep -Eq 'xor[[:space:]]+%eax,%eax'
objdump -dr "$TMP/a.o" | grep -Eq 'ret'

sha256sum "$TMP/a.o" | awk '{print $1}' > "$TMP/a.sha"
sha256sum "$TMP/b.o" | awk '{print $1}' > "$TMP/b.sha"
cmp "$TMP/a.sha" "$TMP/b.sha"
test "$(cat "$TMP/a.sha")" = 'e118c1526abd2e1d99e684d4c524c0df68de0e240cc734570ea5f26ab33d7c78'

printf 'backend DXL check: PASS\n'
printf 'backend diagnostics: PASS (AEG2501, AEG2502, AEG2503)\n'
printf 'backend deterministic bytes: PASS (%s)\n' "$(cat "$TMP/a.sha")"
printf 'backend ELF64 sections/symbol/relocation: PASS\n'
printf 'backend minimal DWARF line table: PASS\n'
