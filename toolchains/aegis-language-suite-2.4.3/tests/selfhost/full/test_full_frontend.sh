#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DXLC="${DXLC:-$ROOT/toolchain/linux-x86_64/libexec/dxlc-front}"
ENTRY="$ROOT/compiler/dxl/selfhost/full/main.dxl"
MODEL="$ROOT/compiler/dxl/selfhost/full/model.dxl"
CASES="$ROOT/tests/selfhost/full"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

record_pass() { printf 'PASS  %s\n' "$1"; pass=$((pass+1)); }
record_fail() { printf 'FAIL  %s\n' "$1" >&2; fail=$((fail+1)); }

run_ok() {
  local name="$1" output="$2"
  shift 2
  if timeout 45s "$@" >"$output" 2>"$TMP/stderr"; then
    record_pass "$name"
  else
    record_fail "$name"
    cat "$TMP/stderr" >&2
  fi
}

run_rejected() {
  local name="$1" output="$2" status
  shift 2
  set +e
  timeout 45s "$@" >"$output" 2>"$TMP/stderr"
  status=$?
  set -e
  if [[ "$status" -eq 1 ]]; then
    record_pass "$name"
  else
    record_fail "$name (expected exit 1, got $status)"
    cat "$TMP/stderr" >&2
  fi
}

line_is() {
  local name="$1" file="$2" line="$3" expected="$4" actual
  actual="$(sed -n "${line}p" "$file")"
  if [[ "$actual" == "$expected" ]]; then record_pass "$name"; else record_fail "$name (expected $expected, got $actual)"; fi
}

line_gt() {
  local name="$1" file="$2" line="$3" threshold="$4" actual
  actual="$(sed -n "${line}p" "$file")"
  if [[ "$actual" =~ ^[0-9]+$ ]] && (( actual > threshold )); then record_pass "$name"; else record_fail "$name (expected > $threshold, got $actual)"; fi
}

has_full_diag() {
  local name="$1" file="$2" wanted="$3" lex_count full_count begin end
  lex_count="$(sed -n '3p' "$file")"
  full_count="$(sed -n '10p' "$file")"
  begin=$((14 + lex_count * 3))
  end=$((begin + full_count * 3 - 1))
  if sed -n "${begin},${end}p" "$file" | awk -v wanted="$wanted" '((NR-1)%3)==0 && $0==wanted {found=1} END {exit found ? 0 : 1}'; then
    record_pass "$name"
  else
    record_fail "$name (missing diagnostic $wanted)"
  fi
}

[[ -x "$DXLC" ]] || { printf 'missing compiler engine: %s\n' "$DXLC" >&2; exit 2; }

run_ok 'integrated source closure check' "$TMP/check.out" "$DXLC" check "$ENTRY"
run_ok 'integrated frontend build A' "$TMP/build-a.out" "$DXLC" build "$ENTRY" -o "$TMP/frontend-a"
run_ok 'integrated frontend build B' "$TMP/build-b.out" "$DXLC" build "$ENTRY" -o "$TMP/frontend-b"
if cmp -s "$TMP/frontend-a" "$TMP/frontend-b"; then record_pass 'frontend executable byte identity'; else record_fail 'frontend executable byte identity'; fi

run_ok 'positive pipeline A' "$TMP/positive-a.out" "$TMP/frontend-a" "$CASES/positive_pipeline.dxl"
run_ok 'positive pipeline B' "$TMP/positive-b.out" "$TMP/frontend-b" "$CASES/positive_pipeline.dxl"
if cmp -s "$TMP/positive-a.out" "$TMP/positive-b.out"; then record_pass 'positive canonical output identity'; else record_fail 'positive canonical output identity'; fi
line_is 'record format version' "$TMP/positive-a.out" 1 24301
line_is 'positive token count' "$TMP/positive-a.out" 2 120
line_is 'positive lexer diagnostics' "$TMP/positive-a.out" 3 0
line_is 'positive AST count' "$TMP/positive-a.out" 5 47
line_is 'positive parser diagnostics' "$TMP/positive-a.out" 6 0
line_is 'positive symbol count' "$TMP/positive-a.out" 8 8
line_is 'positive typed expression count' "$TMP/positive-a.out" 9 28
line_is 'positive semantic diagnostics' "$TMP/positive-a.out" 10 0
line_is 'positive TIR count' "$TMP/positive-a.out" 11 45
line_is 'positive TIR digest' "$TMP/positive-a.out" 12 1555426043
line_is 'positive fatal code' "$TMP/positive-a.out" 13 0

run_ok 'source-sensitivity mutant' "$TMP/mutant.out" "$TMP/frontend-a" "$CASES/positive_pipeline_mutant.dxl"
line_is 'mutant TIR digest' "$TMP/mutant.out" 12 1389929611
if cmp -s "$TMP/positive-a.out" "$TMP/mutant.out"; then record_fail 'source sensitivity changes canonical output'; else record_pass 'source sensitivity changes canonical output'; fi

run_ok 'integer boundary pipeline A' "$TMP/boundary-a.out" "$TMP/frontend-a" "$CASES/integer_boundaries.dxl"
run_ok 'integer boundary pipeline B' "$TMP/boundary-b.out" "$TMP/frontend-b" "$CASES/integer_boundaries.dxl"
if cmp -s "$TMP/boundary-a.out" "$TMP/boundary-b.out"; then record_pass 'integer boundary output identity'; else record_fail 'integer boundary output identity'; fi
line_is 'integer boundary lexer diagnostics' "$TMP/boundary-a.out" 3 0
line_is 'integer boundary parser diagnostics' "$TMP/boundary-a.out" 6 0
line_is 'integer boundary semantic diagnostics' "$TMP/boundary-a.out" 10 0
line_gt 'integer boundary TIR is nonempty' "$TMP/boundary-a.out" 11 0

run_ok 'forward inference chain A' "$TMP/forward-a.out" "$TMP/frontend-a" "$CASES/forward_inference_chain.dxl"
run_ok 'forward inference chain B' "$TMP/forward-b.out" "$TMP/frontend-b" "$CASES/forward_inference_chain.dxl"
if cmp -s "$TMP/forward-a.out" "$TMP/forward-b.out"; then record_pass 'forward inference output identity'; else record_fail 'forward inference output identity'; fi
line_is 'forward inference parser diagnostics' "$TMP/forward-a.out" 6 0
line_is 'forward inference semantic diagnostics' "$TMP/forward-a.out" 10 0
line_gt 'forward inference typed expressions' "$TMP/forward-a.out" 9 16

run_rejected 'semantic-negative rejection A' "$TMP/semantic-a.out" "$TMP/frontend-a" "$CASES/negative_semantic.dxl"
run_rejected 'semantic-negative rejection B' "$TMP/semantic-b.out" "$TMP/frontend-b" "$CASES/negative_semantic.dxl"
if cmp -s "$TMP/semantic-a.out" "$TMP/semantic-b.out"; then record_pass 'semantic diagnostics identity'; else record_fail 'semantic diagnostics identity'; fi
line_is 'semantic-negative parser clean' "$TMP/semantic-a.out" 6 0
line_is 'semantic-negative diagnostic count' "$TMP/semantic-a.out" 10 5
has_full_diag 'declared/initializer mismatch diagnostic' "$TMP/semantic-a.out" 1503
has_full_diag 'condition boolean diagnostic' "$TMP/semantic-a.out" 1504
has_full_diag 'unknown assignment diagnostic' "$TMP/semantic-a.out" 1502
has_full_diag 'assert boolean diagnostic' "$TMP/semantic-a.out" 1506
has_full_diag 'return type diagnostic' "$TMP/semantic-a.out" 1505

run_rejected 'syntax-negative rejection A' "$TMP/syntax-a.out" "$TMP/frontend-a" "$CASES/negative_syntax.dxl"
run_rejected 'syntax-negative rejection B' "$TMP/syntax-b.out" "$TMP/frontend-b" "$CASES/negative_syntax.dxl"
if cmp -s "$TMP/syntax-a.out" "$TMP/syntax-b.out"; then record_pass 'syntax diagnostics identity'; else record_fail 'syntax diagnostics identity'; fi
line_is 'syntax-negative parser diagnostic count' "$TMP/syntax-a.out" 6 17
has_full_diag 'expected name diagnostic' "$TMP/syntax-a.out" 1402
has_full_diag 'expected token diagnostic' "$TMP/syntax-a.out" 1403
has_full_diag 'expected expression diagnostic' "$TMP/syntax-a.out" 1405

run_rejected 'deep expression rejection A' "$TMP/deep-a.out" "$TMP/frontend-a" "$CASES/negative_deep_expression.dxl"
run_rejected 'deep expression rejection B' "$TMP/deep-b.out" "$TMP/frontend-b" "$CASES/negative_deep_expression.dxl"
if cmp -s "$TMP/deep-a.out" "$TMP/deep-b.out"; then record_pass 'deep expression diagnostics identity'; else record_fail 'deep expression diagnostics identity'; fi
has_full_diag 'expression nesting limit diagnostic' "$TMP/deep-a.out" 1408

run_rejected 'deep statement rejection A' "$TMP/deep-statement-a.out" "$TMP/frontend-a" "$CASES/negative_deep_statements.dxl"
run_rejected 'deep statement rejection B' "$TMP/deep-statement-b.out" "$TMP/frontend-b" "$CASES/negative_deep_statements.dxl"
if cmp -s "$TMP/deep-statement-a.out" "$TMP/deep-statement-b.out"; then record_pass 'deep statement diagnostics identity'; else record_fail 'deep statement diagnostics identity'; fi
has_full_diag 'statement nesting limit diagnostic' "$TMP/deep-statement-a.out" 1408

run_rejected 'unknown aggregate rejection A' "$TMP/unknown-aggregate-a.out" "$TMP/frontend-a" "$CASES/negative_unknown_struct.dxl"
run_rejected 'unknown aggregate rejection B' "$TMP/unknown-aggregate-b.out" "$TMP/frontend-b" "$CASES/negative_unknown_struct.dxl"
if cmp -s "$TMP/unknown-aggregate-a.out" "$TMP/unknown-aggregate-b.out"; then record_pass 'unknown aggregate diagnostics identity'; else record_fail 'unknown aggregate diagnostics identity'; fi
line_is 'unknown aggregate parser clean' "$TMP/unknown-aggregate-a.out" 6 0
has_full_diag 'unknown aggregate name diagnostic' "$TMP/unknown-aggregate-a.out" 1502
has_full_diag 'unknown aggregate unresolved type diagnostic' "$TMP/unknown-aggregate-a.out" 1508

# A real portion of the frontend source is accepted by the frontend itself.
run_ok 'self-acceptance model source A' "$TMP/model-a.out" "$TMP/frontend-a" "$MODEL"
run_ok 'self-acceptance model source B' "$TMP/model-b.out" "$TMP/frontend-b" "$MODEL"
if cmp -s "$TMP/model-a.out" "$TMP/model-b.out"; then record_pass 'self-acceptance model output identity'; else record_fail 'self-acceptance model output identity'; fi
line_is 'model parser diagnostics' "$TMP/model-a.out" 6 0
line_is 'model semantic diagnostics' "$TMP/model-a.out" 10 0
line_gt 'model typed IR is nonempty' "$TMP/model-a.out" 11 0

# The full driver is syntactically accepted, but semantic import/type closure is
# intentionally required before any self-host claim can pass.
run_rejected 'full-source semantic closure remains guarded A' "$TMP/self-a.out" "$TMP/frontend-a" "$ENTRY"
run_rejected 'full-source semantic closure remains guarded B' "$TMP/self-b.out" "$TMP/frontend-b" "$ENTRY"
if cmp -s "$TMP/self-a.out" "$TMP/self-b.out"; then record_pass 'full-source boundary output identity'; else record_fail 'full-source boundary output identity'; fi
line_is 'full source lexer diagnostics' "$TMP/self-a.out" 3 0
line_is 'full source parser diagnostics' "$TMP/self-a.out" 6 0
line_gt 'full source semantic closure diagnostics' "$TMP/self-a.out" 10 0
has_full_diag 'full source import/builtin resolution gap' "$TMP/self-a.out" 1502
has_full_diag 'full source named-type resolution gap' "$TMP/self-a.out" 1508

run_rejected 'named-structure semantic gap guard' "$TMP/gap.out" "$TMP/frontend-a" "$CASES/self_acceptance_gap.dxl"
line_is 'gap guard parser diagnostics' "$TMP/gap.out" 6 0
has_full_diag 'gap guard unresolved field type' "$TMP/gap.out" 1508

printf '\nRESULT: %d PASS / %d FAIL\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
