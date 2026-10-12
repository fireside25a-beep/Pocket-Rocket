# Stable Frontend Diagnostics

Codes are never reused for a different meaning. Parser diagnostics occupy the
`14xx` range, semantic diagnostics occupy `15xx`, and lowering diagnostics
occupy `16xx`.

| Code | Phase | Meaning |
|---:|---|---|
| 1401 | Parser | Expected a top-level declaration |
| 1402 | Parser | Expected an identifier |
| 1403 | Parser | Expected the grammar-specific delimiter or operator |
| 1404 | Parser | Expected a type |
| 1405 | Parser | Expected an expression |
| 1406 | Parser | Expected a statement |
| 1407 | Parser | Reached end of input before closing a block |
| 1408 | Parser | Expression or statement/block nesting exceeds the deterministic depth limit |
| 1498 | Parser | Recovery made no progress; one token was consumed fail-closed |
| 1499 | Parser | A bounded parser, AST, scope, symbol, or diagnostic arena is full |
| 1501 | Semantics | Duplicate name in the same lexical scope |
| 1502 | Semantics | Unknown name |
| 1503 | Semantics | Incompatible operand, initializer, assignment, or declared type |
| 1504 | Semantics | If/while condition is not Boolean |
| 1505 | Semantics | Return expression does not match the function return type |
| 1506 | Semantics | Assertion expression is not Boolean |
| 1507 | Semantics | Called symbol is not a function |
| 1508 | Semantics | Type remains unresolved after deterministic inference |
| 1509 | Semantics | Deterministic type-inference work budget is exhausted |
| 1601 | Lowering | The bounded typed-IR instruction arena is full |

Every emitted diagnostic includes its one-based source line and column. The
test suite checks representative parser and semantic codes, exact counts,
repeat-output identity, and source sensitivity.
