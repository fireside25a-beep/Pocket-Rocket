#!/usr/bin/env bash
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TOP=$(cd "$ROOT/.." && pwd)
B="$ROOT/build"
BS="$ROOT/build-sanitize"
DXLC="$TOP/01_Aegis_C_Bootstrap/build/bin/dxlc"
TMP=${TMPDIR:-/tmp}/aegis24-tests-$$
FILTER=${1:-${DX_TEST_FILTER:-all}}
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP"
PASS=0; FAIL=0
pass(){ printf 'PASS %s\n' "$1"; PASS=$((PASS+1)); }
fail(){ printf 'FAIL %s\n' "$1"; FAIL=$((FAIL+1)); }
ok(){ local n=$1; shift; if "$@"; then pass "$n"; else fail "$n"; fi; }
bad(){ local n=$1; shift; if "$@"; then fail "$n"; else pass "$n"; fi; }
group(){ [[ "$FILTER" == all || "$FILTER" == "$1" ]]; }

if group build; then
  echo '== strict builds =='
  ok c_strict make -C "$ROOT/c" clean all
  ok dxl_compiler_check "$DXLC" check "$ROOT/native/src/aegis24_compiler.dxl"
  ok dxl_vm_check "$DXLC" check "$ROOT/native/src/aegis24_vm.dxl"
  ok dxl_compiler_build "$DXLC" build "$ROOT/native/src/aegis24_compiler.dxl" -o "$ROOT/native/build/compiler"
  ok dxl_vm_build "$DXLC" build "$ROOT/native/src/aegis24_vm.dxl" -o "$ROOT/native/build/vm"
  ok stdlib_check bash -c 'cd "$1/stdlib" && "$2" check validation.dxl' _ "$ROOT" "$DXLC"
  ok stdlib_build bash -c 'cd "$1/stdlib" && "$2" build validation.dxl -o ../build/stdlib_validation' _ "$ROOT" "$DXLC"
  ok stdlib_output bash -c 'test "$("$1/build/stdlib_validation")" = $'"'"'3\n-3\n4\n9\n4'"'"'' _ "$ROOT"
  ok clang_strict clang -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -I"$ROOT/c" "$ROOT/c/dxaegis24.c" "$ROOT/c/dxr24.c" -o "$TMP/aegis2-clang"
  ok gcc_analyzer gcc -std=c11 -O0 -Wall -Wextra -Wpedantic -Werror -fanalyzer -I"$ROOT/c" "$ROOT/c/dxaegis24.c" "$ROOT/c/dxr24.c" -o "$TMP/aegis2-analyzer"
  ok doctor_features bash -c '"$1" doctor | grep -q '"'"'"balanced_ternary":true'"'"' && "$1" doctor | grep -q '"'"'"process_capability":false'"'"'' _ "$B/aegis2"
fi

if group values; then
  echo '== values, modules, errors, UTF-8, spans =='
  ok module_graph "$B/dxresolve24" graph "$ROOT/examples/aegis24_project.dxp"
  ok watch_graph "$B/dxresolve24" watch "$ROOT/examples/aegis24_project.dxp" --once
  ok module_resolve "$B/dxresolve24" resolve "$ROOT/examples/aegis24_project.dxp" -o "$TMP/flat.dxs"
  ok formatter "$B/dxdev24" fmt "$TMP/flat.dxs" -o "$TMP/formatted.dxs"
  ok formatter_idempotent "$B/dxdev24" fmt "$TMP/formatted.dxs" --check
  ok c_compile "$B/dxs24cc" "$TMP/formatted.dxs" "$TMP/c.dxb"
  ok dxl_compile "$ROOT/native/build/compiler" "$TMP/formatted.dxs" "$TMP/n.dxb"
  ok compiler_identity cmp "$TMP/c.dxb" "$TMP/n.dxb"
  printf '\003' > "$TMP/policy"
  ok c_vm bash -c '"$1" "$2" "$3" "$4" > "$5"' _ "$B/dxvm24" "$TMP/c.dxb" "$TMP/policy" "$TMP/c.proof" "$TMP/c.out"
  ok dxl_vm bash -c '"$1" "$2" "$3" "$4" > "$5"' _ "$ROOT/native/build/vm" "$TMP/n.dxb" "$TMP/policy" "$TMP/n.proof" "$TMP/n.out"
  ok output_identity cmp "$TMP/c.out" "$TMP/n.out"
  ok proof_identity cmp "$TMP/c.proof" "$TMP/n.proof"
  if [[ ${UPDATE_SNAPSHOTS:-0} == 1 ]]; then cp "$TMP/c.out" "$ROOT/examples/apps/aegis24_cli.snapshot"; fi
  ok snapshot cmp "$TMP/c.out" "$ROOT/examples/apps/aegis24_cli.snapshot"
  ok exact_heap_28 "$B/aegis2" gate "$TMP/formatted.dxs" --policy all --max-heap 28
  bad heap_27_reject "$B/aegis2" gate "$TMP/formatted.dxs" --policy all --max-heap 27
  ok audit_embedded bash -c '"$1" audit "$2" --json | grep -q '"'"'"embedded_data_bytes":28'"'"'' _ "$B/aegis2" "$TMP/c.dxb"
  ok audit_ternary bash -c '"$1" audit "$2" --json | grep -q '"'"'"ternary_literals":1'"'"'' _ "$B/aegis2" "$TMP/c.dxb"
  printf '1\n2\nunknown_token\n' > "$TMP/span.dxs"
  bad span_compile_reject "$B/aegis2" compile "$TMP/span.dxs" -o "$TMP/span.dxb" --cache "$TMP/cache" --json
  ok span_line_3 bash -c '"$1" compile "$2" -o "$3" --cache "$4" --json 2>&1 | grep -q '"'"'"line":3'"'"'' _ "$B/aegis2" "$TMP/span.dxs" "$TMP/span2.dxb" "$TMP/cache2"
  printf 'TRIT:+0- TNOT PRINT HALT\n' > "$TMP/trit.dxasm"
  ok dxasm_ternary "$B/dxasm24" "$TMP/trit.dxasm" "$TMP/trit.dxb"
  ok dxasm_ternary_output bash -c 'test "$("$1" "$2")" = -8' _ "$B/dxvm24" "$TMP/trit.dxb"
fi

if group negative; then
  echo '== adversarial value and module tests =='
  printf 'text:c0af text::write free\n' > "$TMP/badutf8.dxs"
  bad c_invalid_utf8 "$B/dxs24cc" "$TMP/badutf8.dxs" "$TMP/x.dxb"
  bad dxl_invalid_utf8 "$ROOT/native/build/compiler" "$TMP/badutf8.dxs" "$TMP/y.dxb"
  printf 't:+2 trit::not print\n' > "$TMP/badtrit.dxs"
  bad c_invalid_trit "$B/dxs24cc" "$TMP/badtrit.dxs" "$TMP/x.dxb"
  bad dxl_invalid_trit "$ROOT/native/build/compiler" "$TMP/badtrit.dxs" "$TMP/y.dxb"
  printf 'buffer:41 dup free free\n' > "$TMP/dup_owned.dxs"
  ok owned_dup_compile "$B/dxs24cc" "$TMP/dup_owned.dxs" "$TMP/dup_owned.dxb"
  bad owned_dup_reject "$B/dxvm24" "$TMP/dup_owned.dxb"
  printf 'buffer:41 buffer::freeze 0 65 bytes::set free\n' > "$TMP/mutate_slice.dxs"
  ok immutable_mutation_compile "$B/dxs24cc" "$TMP/mutate_slice.dxs" "$TMP/mutate_slice.dxb"
  bad immutable_mutation_reject "$B/dxvm24" "$TMP/mutate_slice.dxb"
  printf 'buffer:4142 buffer::freeze 1 9 bytes::slice free\n' > "$TMP/badslice.dxs"
  ok badslice_compile "$B/dxs24cc" "$TMP/badslice.dxs" "$TMP/badslice.dxb"
  bad badslice_runtime "$B/dxvm24" "$TMP/badslice.dxb"
  printf 'error:7 error::try\n' > "$TMP/try.dxs"
  ok try_compile "$B/dxs24cc" "$TMP/try.dxs" "$TMP/try.dxb"
  bad try_propagates "$B/dxvm24" "$TMP/try.dxb"
  bad capability_denied "$B/aegis2" run "$ROOT/examples/apps/aegis24_flat.formatted.dxs" --policy print
  mkdir -p "$TMP/cycle"
  printf 'use:b\n' > "$TMP/cycle/a.dxs"; printf 'use:a\n' > "$TMP/cycle/b.dxs"; printf 'use:a\n' > "$TMP/cycle/entry.dxs"
  cat > "$TMP/cycle/p.dxp" <<CYCLE
entry=entry.dxs
module.a=a.dxs
module.b=b.dxs
CYCLE
  bad module_cycle "$B/dxresolve24" resolve "$TMP/cycle/p.dxp" -o "$TMP/cycle/out.dxs"
  printf 'entry=../escape.dxs\n' > "$TMP/traversal.dxp"
  bad manifest_traversal "$B/dxresolve24" graph "$TMP/traversal.dxp"
  bad data_capability_required "$B/dxdev24" data-json "$ROOT/examples/data/values.txt" -o "$TMP/no.json" --cap none
fi

if group tools; then
  echo '== capability-aware utilities =='
  ok lock_1 "$B/dxdev24" lock "$ROOT/examples/package/package.files" -o "$TMP/a.lock"
  ok lock_2 "$B/dxdev24" lock "$ROOT/examples/package/package.files" -o "$TMP/b.lock"
  ok lock_deterministic cmp "$TMP/a.lock" "$TMP/b.lock"
  ok json_serialize "$B/dxdev24" data-json "$ROOT/examples/data/values.txt" -o "$TMP/a.json" --cap file-read,file-write
  ok json_exact bash -c 'test "$(cat "$1")" = '"'"'{"format":"DXJSON1","values":[9,-3,0,27,1]}'"'"'' _ "$TMP/a.json"
  ok bin_serialize_1 "$B/dxdev24" data-bin "$ROOT/examples/data/values.txt" -o "$TMP/a.bin" --cap file-read,file-write
  ok bin_serialize_2 "$B/dxdev24" data-bin "$ROOT/examples/data/values.txt" -o "$TMP/b.bin" --cap file-read,file-write
  ok bin_deterministic cmp "$TMP/a.bin" "$TMP/b.bin"
  ok fixed_time bash -c 'test "$("$1" fixed-time 1700000000 --cap time)" = '"'"'{"format":"DXTIME1","unix_seconds":1700000000}'"'"'' _ "$B/dxdev24"
  ok capabilities_disabled bash -c '"$1" capabilities | grep -q '"'"'"process":"disabled"'"'"' && "$1" capabilities | grep -q '"'"'"network":"disabled"'"'"'' _ "$B/dxdev24"
fi

if group corpus; then
  echo '== generated dual-implementation corpus =='
  if "$ROOT/tests/generate_module_corpus.sh" 128 "$ROOT/proofs/corpus" > "$TMP/corpus.log" 2>&1; then
    pass corpus_128
  else
    cat "$TMP/corpus.log"; fail corpus_128
  fi
  ok corpus_manifest_rows bash -c 'test "$(($(wc -l < "$1")-1))" -eq 128' _ "$ROOT/proofs/corpus/MANIFEST.csv"
fi

if group native; then
  echo '== typed IR and x86-64 ELF foundation =='
  SRC="$ROOT/examples/apps/aegis24_flat.formatted.dxs"
  ok ir_1 "$B/dxnative24" ir "$SRC" -o "$TMP/a.dxir"
  ok ir_2 "$B/dxnative24" ir "$SRC" -o "$TMP/b.dxir"
  ok ir_deterministic cmp "$TMP/a.dxir" "$TMP/b.dxir"
  ok obj_1 "$B/dxnative24" obj "$SRC" -o "$TMP/a.o"
  ok obj_2 "$B/dxnative24" obj "$SRC" -o "$TMP/b.o"
  ok obj_deterministic cmp "$TMP/a.o" "$TMP/b.o"
  ok elf_object bash -c 'file "$1" | grep -q '"'"'ELF 64-bit LSB relocatable'"'"'' _ "$TMP/a.o"
  ok elf_relocation bash -c 'readelf -r "$1" | grep -q R_X86_64_PC32' _ "$TMP/a.o"
  ok debug_line bash -c 'readelf -S "$1" | grep -q .debug_line' _ "$TMP/a.o"
  ok link cc "$TMP/a.o" -o "$TMP/native"
  ok native_run bash -c '"$1" > "$2"' _ "$TMP/native" "$TMP/native.out"
  printf '\003' > "$TMP/policy"
  ok native_vm_compile "$B/dxs24cc" "$SRC" "$TMP/native_suite.dxb"
  ok vm_run bash -c '"$1" "$2" "$3" "$4" > "$5"' _ "$B/dxvm24" "$TMP/native_suite.dxb" "$TMP/policy" "$TMP/vm.proof" "$TMP/vm.out"
  ok native_dxb_output cmp "$TMP/native.out" "$TMP/vm.out"
  ok dxl_direct_ir_1 "$B/dxldirect24" ir "$ROOT/examples/apps/native_controlled.dxl" -o "$TMP/dxl-a.dxir"
  ok dxl_direct_ir_2 "$B/dxldirect24" ir "$ROOT/examples/apps/native_controlled.dxl" -o "$TMP/dxl-b.dxir"
  ok dxl_direct_ir_identity cmp "$TMP/dxl-a.dxir" "$TMP/dxl-b.dxir"
  ok dxl_direct_obj_1 "$B/dxldirect24" obj "$ROOT/examples/apps/native_controlled.dxl" -o "$TMP/dxl-a.o"
  ok dxl_direct_obj_2 "$B/dxldirect24" obj "$ROOT/examples/apps/native_controlled.dxl" -o "$TMP/dxl-b.o"
  ok dxl_direct_obj_identity cmp "$TMP/dxl-a.o" "$TMP/dxl-b.o"
  ok dxl_reference_build "$DXLC" build "$ROOT/examples/apps/native_controlled.dxl" -o "$TMP/dxl-reference"
  ok dxl_direct_link cc "$TMP/dxl-a.o" -o "$TMP/dxl-direct"
  ok dxl_reference_run bash -c '"$1" > "$2"' _ "$TMP/dxl-reference" "$TMP/dxl-reference.out"
  ok dxl_direct_run bash -c '"$1" > "$2"' _ "$TMP/dxl-direct" "$TMP/dxl-direct.out"
  ok dxl_native_semantic_identity cmp "$TMP/dxl-reference.out" "$TMP/dxl-direct.out"
  ok measurements "$ROOT/tests/measure_native.sh"
  if [[ -d "$ROOT/proofs/corpus/case_000" ]]; then
    n_ok=0
    for i in $(seq -w 0 15); do
      d="$ROOT/proofs/corpus/case_0$i"
      "$B/dxnative24" obj "$d/program.dxs" -o "$TMP/n$i.o" || continue
      cc "$TMP/n$i.o" -o "$TMP/n$i" || continue
      "$TMP/n$i" > "$TMP/n$i.out" || continue
      cmp "$TMP/n$i.out" "$d/c.out" || continue
      n_ok=$((n_ok+1))
    done
    if [[ $n_ok -eq 16 ]]; then pass native_differential_16; else fail native_differential_16; fi
  else
    fail native_differential_16
  fi
fi

if group sanitizer; then
  echo '== sanitizers =='
  ok sanitizer_build make -C "$ROOT/c" sanitize
  printf '\003' > "$TMP/policy"
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
    ok sanitizer_compile "$BS/dxs24cc" "$ROOT/examples/apps/aegis24_flat.formatted.dxs" "$TMP/san.dxb"
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
    ok sanitizer_vm bash -c '"$1" "$2" "$3" "$4" >/dev/null' _ "$BS/dxvm24" "$TMP/san.dxb" "$TMP/policy" "$TMP/san.proof"
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
    ok sanitizer_tools "$BS/dxdev24" data-json "$ROOT/examples/data/values.txt" -o "$TMP/san.json" --cap file-read,file-write
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
    ok sanitizer_dxl_backend "$BS/dxldirect24" obj "$ROOT/examples/apps/native_controlled.dxl" -o "$TMP/san-dxl.o"
fi

if group inherited; then
  echo '== inherited regressions =='
  if bash "$TOP/07_Aegis_2.1/tests/run_2_1_tests.sh" > "$ROOT/proofs/logs/inherited_2_1.log" 2>&1; then pass inherited_2_1; else tail -80 "$ROOT/proofs/logs/inherited_2_1.log"; fail inherited_2_1; fi
  if bash "$TOP/06_Aegis_Profile/tests/run_aegis_tests.sh" > "$ROOT/proofs/logs/inherited_aegis.log" 2>&1; then pass inherited_aegis; else tail -80 "$ROOT/proofs/logs/inherited_aegis.log"; fail inherited_aegis; fi
  if bash "$TOP/06_Aegis_Profile/tests/run_aegis_deep_stress.sh" > "$ROOT/proofs/logs/inherited_deep.log" 2>&1; then pass inherited_deep; else tail -80 "$ROOT/proofs/logs/inherited_deep.log"; fail inherited_deep; fi
fi

echo '== summary =='
printf 'PASS=%d FAIL=%d FILTER=%s\n' "$PASS" "$FAIL" "$FILTER"
[[ $FAIL -eq 0 ]]
