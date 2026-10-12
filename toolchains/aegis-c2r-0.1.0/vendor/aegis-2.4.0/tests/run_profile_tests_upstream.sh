#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TOP=$(cd "$ROOT/.." && pwd)
C="$ROOT/c"
N="$ROOT/native"
DXLC="$TOP/01_Aegis_C_Bootstrap/build/bin/dxlc"
TMP=${TMPDIR:-/tmp}/aegis-aegis-test-$$
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP" "$ROOT/proofs/logs" "$ROOT/proofs/cross-target"
PASS=0; FAIL=0
pass(){ printf 'PASS %s\n' "$1"; PASS=$((PASS+1)); }
fail(){ printf 'FAIL %s\n' "$1"; FAIL=$((FAIL+1)); }
expect_ok(){ local name=$1;shift;if "$@";then pass "$name";else fail "$name";fi; }
expect_fail(){ local name=$1;shift;if "$@";then fail "$name";else pass "$name";fi; }

printf '== strict builds ==\n'
mkdir -p "$TOP/01_Aegis_C_Bootstrap/build/bin"
expect_ok stage0_strict_rebuild make -C "$TOP/01_Aegis_C_Bootstrap" clean compiler
expect_ok c_strict_build make -C "$C" clean all
expect_ok c_sanitizer_build make -C "$C" sanitize
mkdir -p "$N/build" "$N/build-sanitize" "$N/generated-c"
for tool in aegis_dxs_compiler aegis_dxasm_compiler aegis_vm; do
  expect_ok "native_check_$tool" "$DXLC" check "$N/src/$tool.dxl"
  expect_ok "native_build_$tool" "$DXLC" build "$N/src/$tool.dxl" -o "$N/build/${tool/aegis_/}"
  expect_ok "native_emit_c_$tool" "$DXLC" emit-c "$N/src/$tool.dxl" -o "$N/generated-c/$tool.c"
  expect_ok "native_sanitize_$tool" clang -std=c11 -O1 -g -Wall -Wextra -Wpedantic -Werror -Wno-unused-function -Wno-unused-const-variable -fsanitize=address,undefined -fno-omit-frame-pointer "$N/generated-c/$tool.c" -o "$N/build-sanitize/${tool/aegis_/}"
done

C_DXS="$C/build/dxs3cc"; C_ASM="$C/build/dxasm3"; C_VM="$C/build/dxvm3"; C_AUDIT="$C/build/dxaudit3"
N_DXS="$N/build/dxs_compiler"; N_ASM="$N/build/dxasm_compiler"; N_VM="$N/build/vm"
CS_DXS="$C/build-sanitize/dxs3cc"; CS_VM="$C/build-sanitize/dxvm3"
NS_DXS="$N/build-sanitize/dxs_compiler"; NS_VM="$N/build-sanitize/vm"
POLICY="$ROOT/examples/policy_print.bin"; DENY="$ROOT/examples/policy_none.bin"

printf '== canonical examples and four-way conformance ==\n'
for name in arithmetic memory ifzero; do
  expect_ok "c_compile_$name" "$C_DXS" "$ROOT/examples/$name.dxs" "$TMP/$name.c.dxb"
  expect_ok "n_compile_$name" "$N_DXS" "$ROOT/examples/$name.dxs" "$TMP/$name.n.dxb"
  expect_ok "byte_identical_$name" cmp "$TMP/$name.c.dxb" "$TMP/$name.n.dxb"
  expect_ok "audit_$name" "$C_AUDIT" "$TMP/$name.c.dxb"
  expect_ok "cvm_c_$name" bash -c '"$0" "$1" "$2" "$3" > "$4"' "$C_VM" "$TMP/$name.c.dxb" "$POLICY" "$TMP/$name.cc.proof" "$TMP/$name.cc.out"
  expect_ok "nvm_c_$name" bash -c '"$0" "$1" "$2" "$3" > "$4"' "$N_VM" "$TMP/$name.c.dxb" "$POLICY" "$TMP/$name.cn.proof" "$TMP/$name.cn.out"
  expect_ok "cvm_n_$name" bash -c '"$0" "$1" "$2" "$3" > "$4"' "$C_VM" "$TMP/$name.n.dxb" "$POLICY" "$TMP/$name.nc.proof" "$TMP/$name.nc.out"
  expect_ok "nvm_n_$name" bash -c '"$0" "$1" "$2" "$3" > "$4"' "$N_VM" "$TMP/$name.n.dxb" "$POLICY" "$TMP/$name.nn.proof" "$TMP/$name.nn.out"
  expect_ok "outputs_identical_$name" cmp "$TMP/$name.cc.out" "$TMP/$name.cn.out"
  expect_ok "cross_outputs_identical_$name" cmp "$TMP/$name.cc.out" "$TMP/$name.nn.out"
  expect_ok "proofs_identical_$name" cmp "$TMP/$name.cc.proof" "$TMP/$name.cn.proof"
  expect_ok "cross_proofs_identical_$name" cmp "$TMP/$name.cc.proof" "$TMP/$name.nn.proof"
  expect_ok "c_asm_$name" "$C_ASM" "$ROOT/examples/$name.dxasm" "$TMP/$name.ca.dxb"
  expect_ok "n_asm_$name" "$N_ASM" "$ROOT/examples/$name.dxasm" "$TMP/$name.na.dxb"
  expect_ok "asm_byte_identical_$name" cmp "$TMP/$name.ca.dxb" "$TMP/$name.na.dxb"
done
expect_fail capability_denied_c "$C_VM" "$TMP/arithmetic.c.dxb" "$DENY" "$TMP/deny-c.proof"
expect_fail capability_denied_native "$N_VM" "$TMP/arithmetic.c.dxb" "$DENY" "$TMP/deny-n.proof"

printf '== C API unit tests ==\n'
expect_ok c_api_unit_compile cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror "$C/dxaegis.c" "$ROOT/tests/test_dxaegis.c" -o "$TMP/test_dxaegis"
expect_ok c_api_unit_run "$TMP/test_dxaegis"
expect_ok c_api_sanitize_compile clang -std=c11 -O1 -g -Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined -fno-omit-frame-pointer "$C/dxaegis.c" "$ROOT/tests/test_dxaegis.c" -o "$TMP/test_dxaegis_san"
expect_ok c_api_sanitize_run env ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$TMP/test_dxaegis_san"

printf '== deterministic generated differential corpus ==\n'
expect_ok corpus_generator_compile cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror "$ROOT/tests/generate_corpus.c" -o "$TMP/generate_corpus"
expect_ok corpus_generate "$TMP/generate_corpus" "$TMP/corpus" 512
corpus_ok=1
for src in "$TMP"/corpus/*.dxs; do
  base=${src%.dxs}; exp=$base.expected
  "$C_DXS" "$src" "$TMP/c.dxb" >/dev/null 2>&1 || { corpus_ok=0; break; }
  "$N_DXS" "$src" "$TMP/n.dxb" >/dev/null 2>&1 || { corpus_ok=0; break; }
  cmp "$TMP/c.dxb" "$TMP/n.dxb" || { corpus_ok=0; break; }
  "$C_VM" "$TMP/c.dxb" "$POLICY" "$TMP/c.proof" > "$TMP/c.out" 2>/dev/null || { corpus_ok=0; break; }
  "$N_VM" "$TMP/c.dxb" "$POLICY" "$TMP/n.proof" > "$TMP/n.out" 2>/dev/null || { corpus_ok=0; break; }
  cmp "$TMP/c.out" "$exp" || { corpus_ok=0; break; }
  cmp "$TMP/c.out" "$TMP/n.out" || { corpus_ok=0; break; }
  cmp "$TMP/c.proof" "$TMP/n.proof" || { corpus_ok=0; break; }
done
if [ "$corpus_ok" -eq 1 ];then pass differential_512_programs;else fail differential_512_programs;fi

printf '== malformed bytecode mutation rejection ==\n'
expect_ok mutator_compile cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror "$ROOT/tests/mutate_dxb3.c" -o "$TMP/mutate_dxb3"
expect_ok mutations_generate "$TMP/mutate_dxb3" "$TMP/memory.c.dxb" "$TMP/mutations" 512
mutation_ok=1
for bad in "$TMP"/mutations/*.dxb; do
  if "$C_VM" "$bad" "$POLICY" "$TMP/bad-c.proof" >/dev/null 2>&1;then mutation_ok=0;break;fi
  if "$N_VM" "$bad" "$POLICY" "$TMP/bad-n.proof" >/dev/null 2>&1;then mutation_ok=0;break;fi
done
if [ "$mutation_ok" -eq 1 ];then pass mutations_512_rejected_by_both;else fail mutations_512_rejected_by_both;fi

printf '== source parser differential fuzz ==\n'
expect_ok fuzz_generator_compile cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror "$ROOT/tests/generate_fuzz.c" -o "$TMP/generate_fuzz"
expect_ok fuzz_generate "$TMP/generate_fuzz" "$TMP/fuzz" 1024
fuzz_ok=1; accepted=0
for src in "$TMP"/fuzz/*.dxs; do
  set +e
  "$C_DXS" "$src" "$TMP/fc.dxb" >/dev/null 2>&1; cr=$?
  "$N_DXS" "$src" "$TMP/fn.dxb" >/dev/null 2>&1; nr=$?
  set -e
  if [ "$cr" -ne "$nr" ];then fuzz_ok=0;break;fi
  if [ "$cr" -eq 0 ];then accepted=$((accepted+1));cmp "$TMP/fc.dxb" "$TMP/fn.dxb" || { fuzz_ok=0;break; };fi
done
printf 'fuzz accepted=%s/1024\n' "$accepted"
if [ "$fuzz_ok" -eq 1 ];then pass fuzz_1024_acceptance_and_bytes_match;else fail fuzz_1024_acceptance_and_bytes_match;fi

printf '== explicit safety negatives ==\n'
compile_fail='stack_loop_mismatch stack_if_mismatch unclosed_repeat excess_fuel excess_nesting'
for name in $compile_fail;do
 expect_fail "c_compile_reject_$name" "$C_DXS" "$ROOT/tests/negative/$name.dxs" "$TMP/$name.c.dxb"
 expect_fail "n_compile_reject_$name" "$N_DXS" "$ROOT/tests/negative/$name.dxs" "$TMP/$name.n.dxb"
done
runtime_fail='use_after_free double_free oob_read oob_write leak oversized_alloc assert_fail divzero'
for name in $runtime_fail;do
 expect_ok "c_compile_runtime_$name" "$C_DXS" "$ROOT/tests/negative/$name.dxs" "$TMP/$name.c.dxb"
 expect_ok "n_compile_runtime_$name" "$N_DXS" "$ROOT/tests/negative/$name.dxs" "$TMP/$name.n.dxb"
 expect_ok "negative_bytes_$name" cmp "$TMP/$name.c.dxb" "$TMP/$name.n.dxb"
 expect_fail "c_runtime_reject_$name" "$C_VM" "$TMP/$name.c.dxb" "$POLICY" "$TMP/$name.c.proof"
 expect_fail "n_runtime_reject_$name" "$N_VM" "$TMP/$name.c.dxb" "$POLICY" "$TMP/$name.n.proof"
done

printf '== sanitizer execution matrix ==\n'
for name in arithmetic memory ifzero;do
 expect_ok "cs_compile_$name" env ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$CS_DXS" "$ROOT/examples/$name.dxs" "$TMP/$name.cs.dxb"
 expect_ok "ns_compile_$name" env ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$NS_DXS" "$ROOT/examples/$name.dxs" "$TMP/$name.ns.dxb"
 expect_ok "cs_vm_$name" env ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$CS_VM" "$TMP/$name.cs.dxb" "$POLICY" "$TMP/$name.cs.proof"
 expect_ok "ns_vm_$name" env ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 "$NS_VM" "$TMP/$name.cs.dxb" "$POLICY" "$TMP/$name.ns.proof"
done

printf '== deterministic repeat ==\n'
repeat_ok=1
for i in $(seq 1 20);do
 "$C_DXS" "$ROOT/examples/memory.dxs" "$TMP/repeat-c-$i.dxb" || repeat_ok=0
 "$N_DXS" "$ROOT/examples/memory.dxs" "$TMP/repeat-n-$i.dxb" || repeat_ok=0
 cmp "$TMP/repeat-c-1.dxb" "$TMP/repeat-c-$i.dxb" || repeat_ok=0
 cmp "$TMP/repeat-c-1.dxb" "$TMP/repeat-n-$i.dxb" || repeat_ok=0
done
if [ "$repeat_ok" -eq 1 ];then pass deterministic_20_compiles;else fail deterministic_20_compiles;fi

printf '== cross-target DXL-native objects ==\n'
for target in x86_64-linux aarch64-linux x86_64-windows wasm32;do
 mkdir -p "$ROOT/proofs/cross-target/$target"
 ext=o;[ "$target" = x86_64-windows ]&&ext=obj
 for tool in aegis_dxs_compiler aegis_dxasm_compiler aegis_vm;do
  expect_ok "cross_${tool}_${target}" "$DXLC" build "$N/src/$tool.dxl" -o "$ROOT/proofs/cross-target/$target/$tool.$ext" --target "$target" --emit obj
 done
done

printf '== baseline dual-path regression ==\n'
expect_ok baseline_dualpath_166 "$TOP/tests/run_dualpath_tests.sh"

printf '== summary ==\nPASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
