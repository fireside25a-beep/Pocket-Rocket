#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DXLC="${DXLC:-$ROOT/build/bin/dxlc}"
ENTRY="$ROOT/compiler/dxl/selfhost/lexer_test_main.dxl"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

ok() {
    local name="$1"
    shift
    if timeout 30s "$@" >"$TMP/stdout" 2>"$TMP/stderr"; then
        printf 'PASS  %s\n' "$name"
        pass=$((pass+1))
    else
        printf 'FAIL  %s\n' "$name"
        cat "$TMP/stdout"
        cat "$TMP/stderr" >&2
        fail=$((fail+1))
    fi
}

check_equal() {
    local name="$1" left="$2" right="$3"
    if cmp -s "$left" "$right"; then
        printf 'PASS  %s\n' "$name"
        pass=$((pass+1))
    else
        printf 'FAIL  %s\n' "$name"
        fail=$((fail+1))
    fi
}

check_line() {
    local name="$1" path="$2" line="$3" expected="$4"
    local actual
    actual="$(sed -n "${line}p" "$path")"
    if [[ "$actual" == "$expected" ]]; then
        printf 'PASS  %s\n' "$name"
        pass=$((pass+1))
    else
        printf 'FAIL  %s (expected %s, got %s)\n' "$name" "$expected" "$actual"
        fail=$((fail+1))
    fi
}

check_contains() {
    local name="$1" path="$2" expected="$3"
    if grep -qx "$expected" "$path"; then
        printf 'PASS  %s\n' "$name"
        pass=$((pass+1))
    else
        printf 'FAIL  %s (missing record %s)\n' "$name" "$expected"
        fail=$((fail+1))
    fi
}

check_token_kind() {
    local name="$1" path="$2" expected="$3"
    if awk -v wanted="$expected" 'NR >= 4 && ((NR - 4) % 7) == 0 && $0 == wanted { found=1 } END { exit found ? 0 : 1 }' "$path"; then
        printf 'PASS  %s\n' "$name"
        pass=$((pass+1))
    else
        printf 'FAIL  %s (missing token kind %s)\n' "$name" "$expected"
        fail=$((fail+1))
    fi
}

[[ -x "$DXLC" ]] || { printf 'missing bundled DXL compiler: %s\n' "$DXLC" >&2; exit 2; }

ok 'selfhost lexer source check' "$DXLC" check "$ENTRY"
ok 'selfhost lexer build A' "$DXLC" build "$ENTRY" -o "$TMP/lexer-a"
ok 'selfhost lexer build B' "$DXLC" build "$ENTRY" -o "$TMP/lexer-b"
check_equal 'selfhost lexer executable byte identity' "$TMP/lexer-a" "$TMP/lexer-b"

ok 'positive lex A' "$TMP/lexer-a" "$ROOT/tests/selfhost/positive/all_tokens.dxl"
cp "$TMP/stdout" "$TMP/positive-a.out"
ok 'positive lex B' "$TMP/lexer-b" "$ROOT/tests/selfhost/positive/all_tokens.dxl"
cp "$TMP/stdout" "$TMP/positive-b.out"
check_equal 'positive output identity' "$TMP/positive-a.out" "$TMP/positive-b.out"
check_line 'positive diagnostics empty' "$TMP/positive-a.out" 2 0
check_line 'positive fatal code empty' "$TMP/positive-a.out" 3 0
check_line 'first token kind' "$TMP/positive-a.out" 4 4
check_line 'first token start' "$TMP/positive-a.out" 5 0
check_line 'first token end' "$TMP/positive-a.out" 6 2
check_line 'first token line' "$TMP/positive-a.out" 7 1
check_line 'first token column' "$TMP/positive-a.out" 8 1
check_line 'first token file' "$TMP/positive-a.out" 9 7
for kind in $(seq 0 54); do
    check_token_kind "positive token kind $kind" "$TMP/positive-a.out" "$kind"
done

ok 'multiple diagnostics lex' "$TMP/lexer-a" "$ROOT/tests/selfhost/negative/multiple_errors.dxl"
cp "$TMP/stdout" "$TMP/multiple.out"
check_line 'multiple diagnostics count' "$TMP/multiple.out" 2 9
check_contains 'invalid integer diagnostic' "$TMP/multiple.out" 1006
check_contains 'invalid escape diagnostic' "$TMP/multiple.out" 1004
check_contains 'integer overflow diagnostic' "$TMP/multiple.out" 1005
check_contains 'invalid byte diagnostic' "$TMP/multiple.out" 1001
check_contains 'unterminated string diagnostic' "$TMP/multiple.out" 1002

ok 'unterminated nested comment lex' "$TMP/lexer-a" "$ROOT/tests/selfhost/negative/unterminated_comment.dxl"
cp "$TMP/stdout" "$TMP/comment.out"
check_line 'comment diagnostics count' "$TMP/comment.out" 2 1
check_contains 'unterminated comment diagnostic' "$TMP/comment.out" 1003

printf '\n%d PASS / %d FAIL\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
