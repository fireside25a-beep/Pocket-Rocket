#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if find "$ROOT" \
    -path "$ROOT/build" -prune -o \
    -path "$ROOT/dist" -prune -o \
    -type l -print -quit | grep -q .; then
  printf 'release verification failed: symbolic link found\n' >&2
  exit 1
fi

if find "$ROOT" \
    -path "$ROOT/build" -prune -o \
    -path "$ROOT/dist" -prune -o \
    -type f \( -name '*.c' -o -name '*.h' -o -name '*.cc' -o -name '*.cpp' -o \
    -name '*.py' -o -name '*.pyc' -o -name '*.rs' -o -name '*.zig' -o \
    -name '*.go' -o -name '*.java' -o -name '*.js' -o -name '*.ts' \) \
    -print -quit | grep -q .; then
  printf 'release verification failed: foreign implementation source found\n' >&2
  exit 1
fi

if find "$ROOT" \
    -path "$ROOT/build" -prune -o \
    -path "$ROOT/dist" -prune -o \
    -type f \( -iname '*.zip' -o -iname '*.7z' -o -iname '*.rar' -o -iname '*.tar' -o -iname '*.tgz' -o -iname '*.gz' -o -iname '*.bz2' -o -iname '*.xz' \) \
    -print -quit | grep -q .; then
  printf 'release verification failed: nested archive found\n' >&2
  exit 1
fi

test "$(tr -d '\r\n' < "$ROOT/VERSION")" = '2.4.3'

for tool in dxlc dxscc dxasm dxvm dxaudit dxs24cc dxvm24; do
  test -x "$ROOT/toolchain/linux-x86_64/bin/$tool"
done
test -x "$ROOT/toolchain/linux-x86_64/libexec/dxlc-front"
test -x "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native"
test -f "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native-diagnostics.tsv"

test -f "$ROOT/compiler/dxs/aegis_dxs_compiler.dxl"
test -f "$ROOT/compiler/dxasm/aegis_dxasm_compiler.dxl"
test -f "$ROOT/runtime/dxb3/aegis_vm.dxl"
test -f "$ROOT/compiler/dxl/selfhost/lexer.dxl"
test -f "$ROOT/compiler/dxl/selfhost/parser/parser.dxl"
test -f "$ROOT/compiler/dxl/selfhost/backend/elf64_x86_64.dxl"
test -f "$ROOT/compiler/dxl/selfhost/full/main.dxl"
test -f "$ROOT/compiler/dxl/selfhost/full/PROFILE.md"
test -f "$ROOT/compiler/dxl/native/dxl_native_compiler.dxl"
test -f "$ROOT/compiler/dxl/native/diagnostics.tsv"
test -f "$ROOT/runtime/native/elf64_executable.dxl"
test -x "$ROOT/tests/selfhost/run_lexer_tests.sh"
test -x "$ROOT/tests/selfhost/parser/test_parser.sh"
test -x "$ROOT/tests/selfhost/backend/test_backend.sh"
test -x "$ROOT/tests/selfhost/full/test_full_frontend.sh"
test -x "$ROOT/tests/native/test_native.sh"
test -f "$ROOT/docs/DXB3_SPECIFICATION.md"
test -f "$ROOT/docs/SELF_HOSTING.md"
test -f "$ROOT/docs/IMPLEMENTATION_STATUS.md"
test -f "$ROOT/docs/GETTING_STARTED.md"
test -f "$ROOT/docs/TOOLCHAIN.md"
test -f "$ROOT/docs/SUPPORT.md"
test -f "$ROOT/docs/TESTING.md"
test -f "$ROOT/docs/NATIVE_PROFILE.md"
test -f "$ROOT/proofs/loops/SHA256SUMS.txt"
test -f "$ROOT/proofs/loops/dxl-native-counter.bin"
test -f "$ROOT/proofs/loops/dxl-native-counter.audit"
test -f "$ROOT/proofs/loops/dxl-native-counter.out"
test -x "$ROOT/scripts/static_check.sh"
test -x "$ROOT/scripts/test_loop_matrix.sh"
test -x "$ROOT/scripts/reproduce_toolchain.sh"
test -x "$ROOT/scripts/package_release.sh"
test -x "$ROOT/scripts/update_manifest.sh"
test -f "$ROOT/.github/workflows/ci.yml"
test -f "$ROOT/RELEASE_NOTES.md"
test -f "$ROOT/CHANGELOG.md"
test -f "$ROOT/CONTRIBUTING.md"
test -f "$ROOT/SECURITY.md"
test -f "$ROOT/SHA256SUMS.txt"
test -f "$ROOT/LICENSE"
test -f "$ROOT/CITATION.cff"

cmp "$ROOT/compiler/dxl/native/diagnostics.tsv" \
  "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native-diagnostics.tsv" >/dev/null

printf 'release structure: PASS\n'
printf 'source-language hygiene: PASS\n'
printf 'toolchain inventory: PASS\n'
printf 'foundation inventory: PASS\n'
