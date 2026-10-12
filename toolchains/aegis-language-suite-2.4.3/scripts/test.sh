#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/build/bin"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

ok() {
  local name="$1"; shift
  if timeout 10s "$@" >"$TMP/out" 2>"$TMP/err"; then
    printf 'PASS  %s\n' "$name"
    pass=$((pass+1))
  else
    printf 'FAIL  %s\n' "$name"
    cat "$TMP/out"
    cat "$TMP/err" >&2
    fail=$((fail+1))
  fi
}

bad() {
  local name="$1"; shift
  local status
  set +e
  timeout 10s "$@" >"$TMP/out" 2>"$TMP/err"
  status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    printf 'FAIL  %s (unexpected success)\n' "$name"
    fail=$((fail+1))
  elif [[ "$status" -eq 124 ]]; then
    printf 'FAIL  %s (timeout)\n' "$name"
    fail=$((fail+1))
  else
    printf 'PASS  %s (rejected)\n' "$name"
    pass=$((pass+1))
  fi
}

reject_with_message() {
  local name="$1" expected="$2"; shift 2
  local status
  set +e
  timeout 10s "$@" >"$TMP/out" 2>"$TMP/err"
  status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    printf 'FAIL  %s (unexpected success)\n' "$name"
    fail=$((fail+1))
  elif [[ "$status" -eq 124 ]]; then
    printf 'FAIL  %s (timeout)\n' "$name"
    fail=$((fail+1))
  elif grep -Fqx "$expected" "$TMP/err"; then
    printf 'PASS  %s (exact diagnostic)\n' "$name"
    pass=$((pass+1))
  else
    printf 'FAIL  %s (diagnostic mismatch)\n' "$name"
    cat "$TMP/err" >&2
    fail=$((fail+1))
  fi
}

ok 'DXL check' "$BIN/dxlc" check "$ROOT/examples/dxl/hello.dxl"
ok 'DXL TIR A' "$BIN/dxlc" emit-tir "$ROOT/examples/dxl/hello.dxl" -o "$TMP/hello-a.tir"
ok 'DXL TIR B' "$BIN/dxlc" emit-tir "$ROOT/examples/dxl/hello.dxl" -o "$TMP/hello-b.tir"
ok 'DXL TIR byte identity' cmp "$TMP/hello-a.tir" "$TMP/hello-b.tir"
ok 'DXL format check' "$BIN/dxlc" fmt "$ROOT/examples/dxl/hello.dxl" --check
ok 'DXL native build A' "$BIN/dxlc" build "$ROOT/examples/loops/dxl/native_counter.dxl" -o "$TMP/native-a"
ok 'DXL native build B' "$BIN/dxlc" build "$ROOT/examples/loops/dxl/native_counter.dxl" -o "$TMP/native-b" --target x86_64-linux
ok 'DXL native byte identity' cmp "$TMP/native-a" "$TMP/native-b"
ok 'DXL native execute' bash -c '"$1" >"$2"' _ "$TMP/native-a" "$TMP/native.out"
ok 'DXL native expected output' cmp "$TMP/native.out" "$ROOT/tests/matrix/loops/expected.out"
ok 'DXL native run command' bash -c '"$1" run "$2" >"$3"' _ "$BIN/dxlc" "$ROOT/examples/loops/dxl/native_counter.dxl" "$TMP/native-run.out"
ok 'DXL native run output' cmp "$TMP/native-run.out" "$ROOT/tests/matrix/loops/expected.out"
ok 'DXL native test command' "$BIN/dxlc" test "$ROOT/tests/native/positive/assertions.dxl"
reject_with_message 'DXL native run requires main' \
  'AEG2731: run requires a main function' \
  "$BIN/dxlc" run "$ROOT/tests/native/positive/assertions.dxl"
reject_with_message 'DXL native test requires test blocks' \
  'AEG2732: test requires one or more test blocks' \
  "$BIN/dxlc" test "$ROOT/examples/loops/dxl/native_counter.dxl"
reject_with_message 'DXL native test forbids early return' \
  'AEG2733: return is not allowed in a test block' \
  "$BIN/dxlc" test "$ROOT/tests/native/negative/test_early_return.dxl"
mkdir -p "$TMP/native-only/bin" "$TMP/native-only/libexec"
cp "$ROOT/toolchain/linux-x86_64/bin/dxlc" "$TMP/native-only/bin/dxlc"
cp "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native" "$TMP/native-only/libexec/dxlc-native"
cp "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native-diagnostics.tsv" "$TMP/native-only/libexec/dxlc-native-diagnostics.tsv"
ok 'DXL native build without compatibility frontend' env \
  CC=/definitely-unavailable DXLC_CC=/definitely-unavailable \
  "$TMP/native-only/bin/dxlc" build "$ROOT/examples/loops/dxl/native_counter.dxl" -o "$TMP/native-only-program"
ok 'DXL native-only executable output' bash -c '"$1" >"$2"' _ "$TMP/native-only-program" "$TMP/native-only.out"
ok 'DXL native-only expected output' cmp "$TMP/native-only.out" "$ROOT/tests/matrix/loops/expected.out"
reject_with_message 'DXL native exact diagnostic' \
  'AEG2716: unknown or out-of-scope local variable' \
  "$BIN/dxlc" build "$ROOT/tests/native/negative/unknown_variable.dxl" -o "$TMP/native-invalid"
reject_with_message 'DXL native missing input' \
  'AEG2792: source input is not a readable regular file' \
  "$BIN/dxlc" build "$TMP/does-not-exist.dxl" -o "$TMP/native-missing"
head -c 65537 /dev/zero | tr '\0' ' ' >"$TMP/native-oversized.dxl"
reject_with_message 'DXL native source-size preflight' \
  'AEG2728: source exceeds 65536 bytes' \
  "$BIN/dxlc" build "$TMP/native-oversized.dxl" -o "$TMP/native-oversized"
printf 'preserve-me\n' >"$TMP/native-sentinel"
reject_with_message 'DXL native rejected overwrite' \
  'AEG2716: unknown or out-of-scope local variable' \
  "$BIN/dxlc" build "$ROOT/tests/native/negative/unknown_variable.dxl" -o "$TMP/native-sentinel"
ok 'DXL native rejected output preserved' grep -qx 'preserve-me' "$TMP/native-sentinel"
reject_with_message 'DXL native missing output directory' \
  'AEG2793: output directory does not exist' \
  "$BIN/dxlc" build "$ROOT/examples/loops/dxl/native_counter.dxl" -o "$TMP/missing/output"
reject_with_message 'DXL native output path is directory' \
  'AEG2794: output path is a directory' \
  "$BIN/dxlc" build "$ROOT/examples/loops/dxl/native_counter.dxl" -o "$TMP"
reject_with_message 'DXL check unsupported target' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" check "$ROOT/examples/dxl/hello.dxl" --target aarch64-linux
reject_with_message 'DXL TIR unsupported target' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" emit-tir "$ROOT/examples/dxl/hello.dxl" -o "$TMP/unsupported.tir" --target aarch64-linux
reject_with_message 'DXL native unsupported target' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" build "$ROOT/examples/dxl/hello.dxl" -o "$TMP/unsupported" --target aarch64-linux
reject_with_message 'DXL check rejects extra option' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" check "$ROOT/examples/dxl/hello.dxl" --nonsense
reject_with_message 'DXL TIR rejects extra option' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" emit-tir "$ROOT/examples/dxl/hello.dxl" -o "$TMP/extra.tir" --nonsense
reject_with_message 'DXL native build rejects extra option' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" build "$ROOT/examples/loops/dxl/native_counter.dxl" -o "$TMP/extra-native" --nonsense
reject_with_message 'DXL native run rejects output option' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" run "$ROOT/examples/loops/dxl/native_counter.dxl" -o "$TMP/not-allowed"
reject_with_message 'DXL format rejects extra option' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" fmt "$ROOT/examples/dxl/hello.dxl" --nonsense
reject_with_message 'DXL targets rejects arguments' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" targets extra
reject_with_message 'DXL version rejects arguments' \
  'AEG2790: invalid command line; run dxlc --help for the accepted form' \
  "$BIN/dxlc" version extra

ok 'DXS compile' "$BIN/dxscc" "$ROOT/examples/dxs/arithmetic.dxs" "$TMP/dxs.dxb"
ok 'DXS audit' "$BIN/dxaudit" "$TMP/dxs.dxb"
ok 'DXS execute' "$BIN/dxvm" "$TMP/dxs.dxb" "$ROOT/examples/policy_all.bin" "$TMP/dxs.proof"
ok 'DXS repeat compile' "$BIN/dxscc" "$ROOT/examples/dxs/arithmetic.dxs" "$TMP/dxs-repeat.dxb"
ok 'DXS byte identity' cmp "$TMP/dxs.dxb" "$TMP/dxs-repeat.dxb"

ok 'DXASM assemble' "$BIN/dxasm" "$ROOT/examples/dxasm/arithmetic.dxasm" "$TMP/dxasm.dxb"
ok 'DXASM audit' "$BIN/dxaudit" "$TMP/dxasm.dxb"
ok 'DXASM execute' "$BIN/dxvm" "$TMP/dxasm.dxb" "$ROOT/examples/policy_all.bin" "$TMP/dxasm.proof"
ok 'DXASM repeat assemble' "$BIN/dxasm" "$ROOT/examples/dxasm/arithmetic.dxasm" "$TMP/dxasm-repeat.dxb"
ok 'DXASM byte identity' cmp "$TMP/dxasm.dxb" "$TMP/dxasm-repeat.dxb"

printf 'Aegis 2.4.3 ternary: ✓ 7\n-8\n' >"$TMP/profile24.expected"
ok 'DXS extended-profile compile A' "$BIN/dxs24cc" "$ROOT/examples/dxs/extended_24.dxs" "$TMP/profile24-a.dxb"
ok 'DXS extended-profile compile B' "$BIN/dxs24cc" "$ROOT/examples/dxs/extended_24.dxs" "$TMP/profile24-b.dxb"
ok 'DXS extended-profile byte identity' cmp "$TMP/profile24-a.dxb" "$TMP/profile24-b.dxb"
ok 'DXB3 extended-profile execute A' bash -c '"$1" "$2" "$3" "$4" >"$5"' _ "$BIN/dxvm24" "$TMP/profile24-a.dxb" "$ROOT/examples/policy_all.bin" "$TMP/profile24-a.proof" "$TMP/profile24-a.out"
ok 'DXB3 extended-profile execute B' bash -c '"$1" "$2" "$3" "$4" >"$5"' _ "$BIN/dxvm24" "$TMP/profile24-b.dxb" "$ROOT/examples/policy_all.bin" "$TMP/profile24-b.proof" "$TMP/profile24-b.out"
ok 'DXB3 extended-profile output identity' cmp "$TMP/profile24-a.out" "$TMP/profile24-b.out"
ok 'DXB3 extended-profile expected output' cmp "$TMP/profile24-a.out" "$TMP/profile24.expected"
ok 'DXB3 extended-profile proof identity' cmp "$TMP/profile24-a.proof" "$TMP/profile24-b.proof"

for source in "$ROOT"/tests/dxl/*.dxl; do
  ok "DXL positive: $(basename "$source")" "$BIN/dxlc" check "$source"
done
for source in "$ROOT"/tests/negative/*.dxl; do
  bad "DXL negative: $(basename "$source")" "$BIN/dxlc" check "$source"
done
bad 'DXL negative: import cycle' "$BIN/dxlc" check "$ROOT/tests/negative/import_cycle/a.dxl"

for source in "$ROOT"/tests/dxs/positive/*.dxs; do
  artifact="$TMP/$(basename "$source").dxb"
  proof="$artifact.proof"
  ok "DXS positive compile: $(basename "$source")" "$BIN/dxscc" "$source" "$artifact"
  ok "DXS positive execute: $(basename "$source")" "$BIN/dxvm" "$artifact" "$ROOT/examples/policy_all.bin" "$proof"
done

for source in "$ROOT"/tests/dxs/negative/*.dxs; do
  artifact="$TMP/negative-$(basename "$source").dxb"
  set +e
  timeout 10s "$BIN/dxscc" "$source" "$artifact" >/dev/null 2>&1
  compile_status=$?
  set -e
  if [[ "$compile_status" -eq 0 ]]; then
    bad "DXS negative runtime: $(basename "$source")" "$BIN/dxvm" "$artifact" "$ROOT/examples/policy_all.bin" "$artifact.proof"
  elif [[ "$compile_status" -eq 124 ]]; then
    printf 'FAIL  DXS negative compile: %s (timeout)\n' "$(basename "$source")"
    fail=$((fail+1))
  else
    printf 'PASS  DXS negative compile: %s (rejected)\n' "$(basename "$source")"
    pass=$((pass+1))
  fi
done

for source in "$ROOT"/tests/dxasm/positive/*.dxasm; do
  artifact="$TMP/$(basename "$source").dxb"
  proof="$artifact.proof"
  ok "DXASM positive assemble: $(basename "$source")" "$BIN/dxasm" "$source" "$artifact"
  ok "DXASM positive execute: $(basename "$source")" "$BIN/dxvm" "$artifact" "$ROOT/examples/policy_all.bin" "$proof"
done
for source in "$ROOT"/tests/dxasm/negative/*.dxasm; do
  bad "DXASM negative: $(basename "$source")" "$BIN/dxasm" "$source" "$TMP/negative-$(basename "$source").dxb"
done

printf '\n%d PASS / %d FAIL\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
