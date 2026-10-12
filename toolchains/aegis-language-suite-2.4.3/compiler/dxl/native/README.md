# DXL native core profile

This directory contains a DXL-authored, source-dependent compiler for a
bounded DXL profile. It writes static Linux x86-64 ELF executables directly.
Generated programs need neither a separate linker nor a dynamic loader.

The command-line contract is:

```text
dxl-native INPUT.dxl OUTPUT
```

Exit status `0` means an executable image was written. Exit status `1` means
the source was rejected and a stable numeric diagnostic was printed. Exit
status `2` means the command line was invalid. The file writer does not set
permission bits; a command driver must make a successful output executable.

## Accepted program profile

The compiler accepts either one `fn main() -> i32` program or one or more
`test "name"` blocks. The profile includes:

- `i64` local variables and assignments;
- signed integer and Boolean literals;
- unary `-` and `!`;
- checked `+`, `-`, and `*`;
- comparisons, equality, `&&`, and `||` with type checks;
- `if`/`else`, `while`, `print_i64`, `assert`, and `return`;
- line, block, and nested block comments;
- parentheses and a maximum syntax nesting depth of 64.

Arithmetic or narrowing-cast overflow exits the generated program with status `70`. A failed
assertion exits with `71`. Exactly 1,000,000 loop-header evaluations are allowed
across all generated loops; the next exits with `72`. User return values are
restricted to `0..63`; an out-of-range return exits with `73`. Output is a
single read/execute `PT_LOAD` image, plus an explicit non-executable stack
declaration, with no interpreter, dynamic section, relocations, or external
runtime dependency.

## Stable compiler diagnostics

[`diagnostics.tsv`](diagnostics.tsv) is the authoritative machine-readable map
for command drivers. The table below summarizes the native-specific range.

| Code | Meaning |
|---:|---|
| 2702 | expected `fn` or a test block |
| 2703 | expected the `main` entry name |
| 2704 | expected `(` |
| 2705 | expected `)` |
| 2706 | expected `->` |
| 2707 | expected `i32` |
| 2708 | expected an entry block |
| 2709 | expected `}` |
| 2710 | expected a name |
| 2711 | expected `:` |
| 2712 | expected `i64` |
| 2713 | expected `=` |
| 2714 | expected `;` |
| 2715 | duplicate local variable |
| 2716 | unknown local variable |
| 2717 | expected expression |
| 2718 | expected statement block |
| 2719 | malformed `print_i64` call |
| 2720 | malformed return cast |
| 2721 | statement is outside the profile |
| 2722 | local-variable capacity exceeded |
| 2723 | print-call capacity exceeded |
| 2724 | `main` requires a return statement |
| 2725 | trailing tokens after the program |
| 2726 | lexer-table initialization failed |
| 2727 | lexer failed without a specific code |
| 2728 | source exceeds 65,536 bytes |
| 2729 | expression type mismatch |
| 2730 | syntax nesting limit exceeded |
| 2731 | `run` requires a `main` function |
| 2732 | `test` requires one or more test blocks |
| 2733 | `return` is not allowed in a test block |
| 2790 | invalid compiler command line |
| 2791 | output write failed |
| 2792 | source input is not a readable regular file |
| 2793 | output directory does not exist |
| 2794 | output path is a directory |
| 2795 | unable to create temporary output |
| 2796 | unable to make output executable |
| 2797 | unable to create diagnostic capture |
| 2801 | invalid generated code length |
| 2802 | output buffer is too small |

Lexer diagnostics `1001` through `1010` retain their stable meanings from the
shared table-driven lexer.

## Explicit boundary

This is a genuine compiler for the profile above, not a fixed object fixture.
Different accepted programs generate different runnable machine code. It is
not the complete DXL language compiler, and it cannot compile its own source:
its implementation uses arrays, byte slices, file primitives, helper
functions, result values, and imports beyond the accepted profile. Therefore
this directory does not claim compiler self-reproduction or stage agreement.
