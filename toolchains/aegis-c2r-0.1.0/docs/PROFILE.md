# S0-DEFINED-I32 profile

The 0.1.0 release intentionally recognizes a small C99/C11-compatible scalar subset whose semantics can be lowered without raw pointers or `unsafe` Rust.

Accepted: `int` functions; final `main()`; up to 63 functions; 16 parameters/function; 256 initialized prefix locals/function; decimal signed-i32 values; variables; calls to already declared functions; unary `-` and `!`; `+ - * / %`; `== != < <= > >=`; `&& ||`; assignment; return; `if/else`; `while`; blocks; exact `printf("%d\\n", expr)`; `assert(expr)`; `#include <stdio.h>` and `#include <assert.h>`.

Rejected: pointers/references, arrays, structs/unions/enums, floating point, unsigned types, casts, `switch`, `for`, `do`, `goto`, recursion, variadics, globals/statics, arbitrary preprocessing/macros, arbitrary libc calls, late/nested declarations, missing final top-level return, unknown identifiers, callable shadowing, direct literal division/remainder by zero, literals outside signed i32, and files above 1 MiB.

This is a contract, not a parser bug list: a future version can expand the contract only with synchronized semantics, tests, lowering and evidence.
