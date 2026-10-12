#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
SEED=${DXL_NATIVE_SEED:-$ROOT/toolchain/linux-x86_64/libexec/dxlc-front}
MODE=${AEGIS_NATIVE_MODE:-source}
TIMEOUT=$(command -v timeout)
STRACE=$(command -v strace || true)
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT HUP INT TERM

pass_count=0
pass() {
    pass_count=$((pass_count + 1))
    printf 'PASS %02d %s\n' "$pass_count" "$1"
}
fail() {
    printf 'FAIL %s\n' "$1" >&2
    exit 1
}

awk -F '\t' '
    NR==1 { if ($1!="code" || $2!="name" || $3!="message") exit 1; next }
    NF!=3 || $1!~/^[0-9]+$/ || $2=="" || $3=="" || seen[$1]++ { exit 1 }
    END { if (NR<40) exit 1 }
' "$ROOT/compiler/dxl/native/diagnostics.tsv" || fail 'diagnostic map is malformed or has duplicate codes'
pass 'machine-readable diagnostic map is complete and unique'

case "$MODE" in
    source)
        timeout 90s "$SEED" check "$ROOT/compiler/dxl/native/dxl_native_compiler.dxl" >"$WORK/check.log"
        pass 'DXL-authored native compiler source checks'
        timeout 90s "$SEED" build "$ROOT/compiler/dxl/native/dxl_native_compiler.dxl" -o "$WORK/compiler-a" >"$WORK/seed-a.log"
        timeout 90s "$SEED" build "$ROOT/compiler/dxl/native/dxl_native_compiler.dxl" -o "$WORK/compiler-b" >"$WORK/seed-b.log"
        cmp -s "$WORK/compiler-a" "$WORK/compiler-b" || fail 'seeded compiler builds differ'
        pass 'two seeded compiler builds are byte-identical'
        cmp -s "$WORK/compiler-a" "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native" || fail 'shipped native compiler differs from source rebuild'
        pass 'source rebuild matches shipped native compiler'
        ;;
    shipped)
        cp "$ROOT/toolchain/linux-x86_64/libexec/dxlc-native" "$WORK/compiler-a"
        chmod 755 "$WORK/compiler-a"
        pass 'checksum-pinned shipped native compiler selected'
        ;;
    *) fail 'AEGIS_NATIVE_MODE must be source or shipped' ;;
esac

compile_profile() {
    local source=$1
    local output=$2
    PATH=/definitely-unavailable CC=/definitely-unavailable DXLC_CC=/definitely-unavailable \
        "$TIMEOUT" 30s "$WORK/compiler-a" "$source" "$output"
}

compile_profile "$ROOT/tests/native/positive/counter.dxl" "$WORK/counter-a"
compile_profile "$ROOT/tests/native/positive/counter.dxl" "$WORK/counter-b"
cmp -s "$WORK/counter-a" "$WORK/counter-b" || fail 'repeated native output differs'
pass 'repeated native output is byte-identical'

compile_profile "$ROOT/tests/native/positive/branches.dxl" "$WORK/branches"
if cmp -s "$WORK/counter-a" "$WORK/branches"; then fail 'distinct sources generated identical output'; fi
pass 'distinct sources generate distinct executables'

for name in counter branches signed; do
    if [[ ! -f $WORK/$name ]]; then compile_profile "$ROOT/tests/native/positive/$name.dxl" "$WORK/$name"; fi
    chmod 755 "$WORK/$name"
    timeout 5s "$WORK/$name" >"$WORK/$name.out"
    diff -u "$ROOT/tests/native/expected/$name.out" "$WORK/$name.out"
    pass "$name native output matches"
done

file "$WORK/counter-a" | grep -q 'ELF 64-bit LSB executable.*statically linked.*no section header' || fail 'unexpected executable format'
if readelf -l "$WORK/counter-a" | grep -q 'INTERP'; then fail 'generated executable has an interpreter'; fi
if readelf -d "$WORK/counter-a" 2>&1 | grep -v 'There is no dynamic section' | grep -q 'NEEDED'; then fail 'generated executable has a dynamic dependency'; fi
[[ $(readelf -l "$WORK/counter-a" | grep -c 'LOAD') -eq 1 ]] || fail 'expected one load segment'
readelf -W -l "$WORK/counter-a" | grep -Eq 'GNU_STACK +0x[0-9a-f]+ +0x[0-9a-f]+ +0x[0-9a-f]+ +0x[0-9a-f]+ +0x[0-9a-f]+ +RW +0x' || fail 'stack is not explicitly non-executable'
pass 'static ELF has one load segment, non-executable stack, and no dynamic loader'

if [[ -n $STRACE ]] && "$STRACE" -qq -e trace=process -o "$WORK/trace-probe" /bin/true 2>/dev/null; then
    PATH=/definitely-unavailable CC=/definitely-unavailable DXLC_CC=/definitely-unavailable \
        "$STRACE" -f -qq -e trace=process -o "$WORK/process.trace" \
        "$WORK/compiler-a" "$ROOT/tests/native/positive/counter.dxl" "$WORK/traced-counter"
    [[ $(grep -c 'execve(' "$WORK/process.trace") -eq 1 ]] || fail 'profile compiler launched a subprocess'
    pass 'process trace contains no child process or external tool launch'
else
    if grep -ERn '\<(exec|system|spawn|popen)\>' "$ROOT/compiler/dxl/native"/*.dxl "$ROOT/runtime/native"/*.dxl >"$WORK/process-primitives"; then
        fail 'native sources reference a process-launch primitive'
    fi
    pass 'poisoned-path compile succeeds; sources contain no process-launch primitive (ptrace unavailable)'
fi

compile_profile "$ROOT/tests/native/positive/assertions.dxl" "$WORK/assertions"
chmod 755 "$WORK/assertions"
timeout 5s "$WORK/assertions"
pass 'multiple native test blocks execute successfully'

expect_runtime_exit() {
    local source=$1
    local expected=$2
    local label=$3
    local output=$WORK/$label
    compile_profile "$source" "$output"
    chmod 755 "$output"
    set +e
    timeout 5s "$output" >"$output.out" 2>&1
    local status=$?
    set -e
    [[ $status -eq $expected ]] || fail "$label returned $status, expected $expected"
    [[ ! -s $output.out ]] || fail "$label produced output before trapping"
    pass "$label exits deterministically with $expected"
}

expect_runtime_exit "$ROOT/tests/native/positive/failing_assertion.dxl" 71 assertion-failure
expect_runtime_exit "$ROOT/tests/native/positive/runtime_overflow.dxl" 70 add-overflow
expect_runtime_exit "$ROOT/tests/native/positive/runtime_sub_overflow.dxl" 70 sub-overflow
expect_runtime_exit "$ROOT/tests/native/positive/runtime_mul_overflow.dxl" 70 mul-overflow
expect_runtime_exit "$ROOT/tests/native/positive/runtime_neg_overflow.dxl" 70 neg-overflow
expect_runtime_exit "$ROOT/tests/native/positive/runtime_cast_overflow.dxl" 70 cast-overflow
expect_runtime_exit "$ROOT/tests/native/positive/fuel_exhaustion.dxl" 72 loop-fuel
expect_runtime_exit "$ROOT/tests/native/positive/fuel_boundary_ok.dxl" 0 loop-fuel-boundary
expect_runtime_exit "$ROOT/tests/native/positive/fuel_boundary_exhaust.dxl" 72 loop-fuel-first-rejection
expect_runtime_exit "$ROOT/tests/native/positive/exit_status_63.dxl" 63 maximum-user-exit
expect_runtime_exit "$ROOT/tests/native/positive/exit_status_64.dxl" 73 first-reserved-user-exit
expect_runtime_exit "$ROOT/tests/native/positive/exit_status_70.dxl" 73 reserved-user-exit
expect_runtime_exit "$ROOT/tests/native/positive/exit_status_negative.dxl" 73 negative-user-exit

expect_compile_error() {
    local source=$1
    local expected=$2
    local label=$3
    local output=$WORK/rejected-$label
    set +e
    PATH=/definitely-unavailable CC=/definitely-unavailable DXLC_CC=/definitely-unavailable \
        "$TIMEOUT" 30s "$WORK/compiler-a" "$source" "$output" >"$WORK/$label.err" 2>&1
    local status=$?
    set -e
    [[ $status -eq 1 ]] || fail "$label compiler status was $status"
    grep -qx "$expected" "$WORK/$label.err" || fail "$label diagnostic was not $expected"
    [[ ! -e $output ]] || fail "$label left an output artifact"
    pass "$label is rejected with diagnostic $expected"
}

expect_compile_error "$ROOT/tests/native/negative/duplicate_variable.dxl" 2715 duplicate-variable
expect_compile_error "$ROOT/tests/native/negative/unknown_variable.dxl" 2716 unknown-variable
expect_compile_error "$ROOT/tests/native/negative/branch_scope.dxl" 2716 branch-scope
expect_compile_error "$ROOT/tests/native/negative/unsupported_function.dxl" 2703 unsupported-entry
expect_compile_error "$ROOT/tests/native/negative/type_mismatch.dxl" 2729 type-mismatch
expect_compile_error "$ROOT/tests/native/negative/non_total_return.dxl" 2724 total-return
expect_compile_error "$ROOT/tests/native/negative/test_early_return.dxl" 2733 test-early-return

printf 'fn main() -> i32 { print_i64(' >"$WORK/deep.dxl"
for _ in $(seq 1 65); do printf '(' >>"$WORK/deep.dxl"; done
printf '1' >>"$WORK/deep.dxl"
for _ in $(seq 1 65); do printf ')' >>"$WORK/deep.dxl"; done
printf '); return as(i32, 0); }\n' >>"$WORK/deep.dxl"
expect_compile_error "$WORK/deep.dxl" 2730 nesting-limit

printf 'test "deep unary" { assert(' >"$WORK/deep-unary.dxl"
for _ in $(seq 1 65); do printf '!' >>"$WORK/deep-unary.dxl"; done
printf 'true); }\n' >>"$WORK/deep-unary.dxl"
expect_compile_error "$WORK/deep-unary.dxl" 2730 unary-nesting-limit

head -c 65537 /dev/zero | tr '\0' ' ' >"$WORK/oversized.dxl"
expect_compile_error "$WORK/oversized.dxl" 2728 source-size-limit

sha256sum "$WORK/counter-a" "$WORK/branches" "$WORK/signed" >"$WORK/native-output-sha256.txt"
printf 'Native profile matrix: %d checks passed\n' "$pass_count"
