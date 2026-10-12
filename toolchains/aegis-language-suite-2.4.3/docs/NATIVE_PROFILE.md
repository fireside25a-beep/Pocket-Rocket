# DXL native core profile

This document defines the DXL source subset that Aegis 2.4.3 compiles directly to a static Linux x86-64 executable. It is a versioned, tested profile of DXL—not a claim that every construct accepted by `dxlc check` can be emitted natively.

## First program

```dxl
fn main() -> i32 {
    let count: i64 = 0;
    while count < 10 {
        count = count + 1;
    }
    print_i64(count);
    return as(i32, 0);
}
```

Build and run it:

```sh
dxlc build counter.dxl -o counter
./counter

dxlc run counter.dxl
```

Both executions print `10` followed by a newline.

## Command contract

```text
dxlc build FILE -o OUTPUT [--target native|x86_64-linux]
dxlc run FILE [--target native|x86_64-linux]
dxlc test FILE [--target native|x86_64-linux]
```

`build` writes through a temporary file and replaces `OUTPUT` only after compilation succeeds. A rejected program therefore cannot erase or partially overwrite an existing output. `run` requires a `main` function, compiles a temporary executable, and returns the program's exit status. `test` requires one or more test blocks, runs them, and succeeds only when every assertion succeeds. The commands reject the opposite source form with distinct diagnostics.

Only `native` and `x86_64-linux` are accepted target names. Both select the same tested Linux x86-64 emitter.

## Program forms

A native-core file contains either one entry function or one or more test blocks.

```text
program       = main-function | test-block+
main-function = "fn" "main" "(" ")" "->" "i32" block
test-block    = "test" string block
block         = "{" statement* "}"
```

The entry function must end with a top-level return:

```dxl
return as(i32, expression);   // main only
```

A return value outside the signed `i32` range traps before process exit.

## Statements

The profile accepts:

```text
let name: i64 = expression;
name = expression;
print_i64(expression);
assert(boolean-expression);
if boolean-expression block else block
while boolean-expression block
return as(i32, expression);
```

The `else` branch is optional. Local names have lexical block scope. Redeclaration in a visible scope and use outside the declaring block are rejected. `return` is valid only in `main`; it is rejected in test blocks so one test cannot skip the tests that follow it.

## Expressions

| Precedence | Operators | Result |
| --- | --- | --- |
| Primary | integer, `true`, `false`, local name, `(expression)` | Literal or local type |
| Unary | `-`, `!` | `i64`, `bool` |
| Multiplicative | `*` | `i64` |
| Additive | `+`, `-` | `i64` |
| Ordering | `<`, `<=`, `>`, `>=` | `bool` |
| Equality | `==`, `!=` | `bool` |
| Conjunction | `&&` | `bool` |
| Disjunction | `||` | `bool` |

`&&` and `||` short-circuit. Addition, subtraction, multiplication, unary negation, and narrowing to `i32` are checked. Type mismatches are compile-time diagnostics.

## Tests

Test files use ordinary statements and expressions:

```dxl
test "arithmetic" {
    let value: i64 = 6 * 7;
    assert(value == 42);
}

test "loop" {
    let count: i64 = 0;
    while count < 5 {
        count = count + 1;
    }
    assert(count == 5);
}
```

Run them with:

```sh
dxlc test tests.dxl
```

## Compile-time limits

| Resource | Limit |
| --- | ---: |
| Source bytes | 65,536 |
| Simultaneously visible locals | 64 |
| `print_i64` call sites | 64 |
| Expression/block nesting | 64 |

All limits reject explicitly. The machine-readable diagnostic registry is [`compiler/dxl/native/diagnostics.tsv`](../compiler/dxl/native/diagnostics.tsv); the public command prints the corresponding `AEGnnnn` identifier and message.

## Runtime limits and exits

| Status | Meaning |
| ---: | --- |
| `0–63` | Value returned through `as(i32, expression)` |
| `70` | Arithmetic, negation, or narrowing-cast overflow |
| `71` | Failed assertion |
| `72` | Shared loop fuel exhausted |
| `73` | A return value was outside the supported process-status range |

Exactly 1,000,000 `while` condition evaluations are permitted across the program. Evaluation 1,000,001 exits with status `72`. This bounds loop iterations, but it is not the DXB3 verifier's whole-program step proof.

## Executable contract

The emitter writes an ELF64 `ET_EXEC` image directly:

- machine: x86-64;
- one read/execute load segment;
- an explicit read/write, non-executable stack declaration;
- no interpreter;
- no dynamic section or dependency;
- no relocations, section table, or build identifier;
- integer output and process exit through the bundled native runtime bytes.

The emitted bytes are source-dependent and deterministic. The release gate compiles the same source twice, requires byte identity, compiles a distinct source and requires different bytes, inspects the executable headers, and runs the result.

## Boundary from DXB3

Native DXL executables do not pass through the DXB3 auditor or VM. Consequently, DXB3 capability enforcement, container verification, heap-handle checks, whole-program resource declarations, and execution proof files do not apply to this path. Use DXS or DXASM with DXB3 when those guarantees are required.

## Outside this profile

Native-core compilation does not yet accept helper functions, parameters, imports, constants, structures, enumerations, compile-time declarations, owned arrays, borrowed slices, result values, division, remainder, generic types, filesystem operations, or program arguments. The compatibility frontend can check a broader DXL language surface, but successful checking does not imply native-core acceptance.

The native compiler is authored in DXL and compiles arbitrary accepted input. It does not compile its own implementation, so 2.4.3 does not claim compiler self-reproduction. See [DXL-native compiler status](SELF_HOSTING.md).
