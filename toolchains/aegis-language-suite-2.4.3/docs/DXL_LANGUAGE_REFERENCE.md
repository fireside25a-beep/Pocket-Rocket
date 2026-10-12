# DXL language reference

DXL is the statically typed implementation and systems language in Aegis. Source files use the `.dxl` extension.

## Release profiles

DXL 2.4.3 has two tested command surfaces:

| Profile | Commands | Scope |
| --- | --- | --- |
| General compatibility profile | `check`, `emit-tir`, `fmt` | The declarations, managed values, modules, ownership checks, and compile-time features in this reference |
| [Native core profile](NATIVE_PROFILE.md) | `build`, `run`, `test` | A bounded scalar subset compiled to static Linux x86-64 executables |

The native profile is intentionally narrower. A successful `check` is not a promise that `build` accepts the same source. Native-specific grammar, resource limits, runtime exits, and artifact guarantees are normative in [DXL native core profile](NATIVE_PROFILE.md).

## Lexical structure

DXL source contains identifiers, integer literals, quoted strings, keywords, operators, punctuation, line comments, and nested block comments.

```dxl
// line comment
/* outer /* nested */ comment */
const decimal: i64 = 1_000_000;
const hexadecimal: i64 = 0x2a;
```

Integer underscores do not change value. Invalid bytes, malformed integer forms, overflow, invalid escapes, and unterminated strings or block comments reject. The DXL-native lexer attaches a file identifier and exact byte/line/column start and end to each token.

## Declarations

The general profile accepts:

- relative imports;
- typed constants;
- structures;
- enumerations;
- functions;
- compile-time functions;
- compile-time blocks;
- test declarations;
- exported and external function declarations where supported by the compatibility frontend.

```dxl
import "math.dxl";

struct Pair {
    left: i64,
    right: i64,
}

enum State {
    idle,
    ready,
}

fn add(a: i64, b: i64) -> i64 {
    return a + b;
}
```

The executable entry shape is `fn main() -> i32`.

## Scalar and named types

| Type | Meaning |
| --- | --- |
| `i64` | Signed 64-bit integer with checked operations |
| `i32` | Signed 32-bit integer with checked operations and casts |
| `bool` | `true` or `false` |
| `void` | No returned value |
| Named `struct` | Fixed ordered fields |
| Named `enum` | Closed set of variants |

The general profile does not implement implicit numeric widening or narrowing. Use `as(i32, expression)` for a checked cast.

## Managed types

| Type | Ownership role |
| --- | --- |
| `array_i64` | Single-owner bounded array |
| `slice_i64` | Borrowed view into a live array |
| `result_i64` | Explicit `i64` success or numeric error |

An owned array cannot be copied, returned, stored in a structure, or passed by value in this release profile. Borrowed slices cannot outlive their owner or be returned. Every successful checked path releases an owner exactly once. The negative corpus covers copies, branch-owner disagreement, missing release, double-use, and slice escape.

Core array operations are `array_new`, `array_free`, `array_len`, and `slice`. Bounds and invalid releases fail explicitly.

Result operations are `ok_i64`, `err_i64`, `is_err`, `unwrap_i64`, and `error_code`. Unwrapping an error is invalid.

## Statements

The general profile includes:

- lexical blocks;
- typed `let` declarations;
- assignment and indexed assignment;
- `if`/`else`;
- `while`;
- `assert`;
- call statements;
- `return`.

```dxl
fn sum_to(limit: i64) -> i64 {
    let count: i64 = 0;
    let total: i64 = 0;
    while count < limit {
        count = count + 1;
        total = total + count;
    }
    return total;
}
```

## Expressions

Implemented expression forms include:

- integer and Boolean literals;
- names and calls;
- field access and indexing;
- structure literals;
- checked casts;
- unary `-` and `!`;
- arithmetic;
- comparisons and equality;
- short-circuit Boolean operators.

Checked integer operations reject overflow. Compile-time division or remainder by zero, invalid negation, and invalid casts reject during evaluation.

## Compile-time execution

`comptime fn`, constants, and `comptime { ... }` run in a bounded evaluator. Cyclic constants, unknown values, overflow, excessive recursion, and exhausted evaluation steps reject.

```dxl
comptime fn square(value: i64) -> i64 {
    return value * value;
}

const answer: i64 = square(6) + 6;

comptime {
    assert(answer == 42);
}
```

Compile-time evaluation in the general profile supports scalar integers, booleans, and enumeration variants; it is not a general aggregate interpreter.

## Modules

Imports use paths relative to the importing source file:

```dxl
import "math.dxl";
```

The compatibility frontend detects missing modules, duplicate declarations, and import cycles. There is no package registry or remote dependency resolver in 2.4.3.

## Tests

The general profile recognizes test declarations for checking. The native core profile additionally compiles one or more `test "name" { ... }` blocks into a runnable assertion executable:

```sh
dxlc test tests/native/positive/assertions.dxl
```

See [DXL native core profile](NATIVE_PROFILE.md) for the statements valid inside a native test block.

## Formatting

```sh
dxlc fmt FILE
dxlc fmt FILE --check
```

`--check` rejects when the file is not in the formatter's canonical form. Formatting is deterministic for the tested corpus. The formatter in this release is not claimed to preserve arbitrary trivia in every malformed source.

## Typed IR

```sh
dxlc emit-tir FILE -o OUTPUT.tir
```

The public compatibility path emits deterministic typed-IR text for inspection and repeated-byte tests. The integrated DXL-native frontend under `compiler/dxl/selfhost/full/` independently emits canonical input-derived typed-IR records for its own bounded profile. Neither text form is a stable external ABI in 2.4.3.

## Commands

```text
dxlc check FILE [--target native|x86_64-linux]
dxlc emit-tir FILE -o OUTPUT [--target native|x86_64-linux]
dxlc fmt FILE [--check]
dxlc build FILE -o OUTPUT [--target native|x86_64-linux]
dxlc run FILE [--target native|x86_64-linux]
dxlc test FILE [--target native|x86_64-linux]
dxlc targets
dxlc version
```

Only Linux x86-64 output is claimed. `native` and `x86_64-linux` are aliases for that one target.

## Diagnostics and acceptance

New DXL-native components use unique `AEGnnnn` identifiers. The native compiler's machine-readable map is [`compiler/dxl/native/diagnostics.tsv`](../compiler/dxl/native/diagnostics.tsv), and the shared registry is described in [Diagnostic codes](DIAGNOSTIC_CODES.md). Some established compatibility-frontend diagnostics remain human-readable without a migrated numeric identifier.

The positive and negative corpora shipped with this release are the executable acceptance record. See [Testing](TESTING.md) and [Support](SUPPORT.md).
