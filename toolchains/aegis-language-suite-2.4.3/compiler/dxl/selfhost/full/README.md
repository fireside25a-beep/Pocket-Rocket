# Integrated DXL Frontend Foundation

This directory contains a real DXL-authored frontend pipeline. The executable
entry point is `main.dxl`; it loads the source path supplied on the command
line, invokes the table-driven lexer, builds a bounded AST, performs scope and
type analysis, and emits a canonical typed-IR record.

It is a compiler foundation, not a self-hosting compiler. The output is typed
IR, not a new compiler executable, so it cannot participate in a Stage 1 to
Stage 2 reproduction chain yet.

## Implemented profile

- imports, constants, functions, parameters, structs, enums, tests, and
  top-level comptime blocks;
- primitive, managed-buffer, and named type syntax;
- let bindings, assignments, returns, assertions, while loops, if/else and
  else-if blocks;
- integer and Boolean literals, names, calls, casts, unary operators, binary
  precedence, field access, indexing, and struct literals;
- unique lexical scopes with parent lookup and duplicate-name detection;
- deterministic fixed-point inference for declarations and expressions;
- stable `14xx` parser, `15xx` semantic, and `16xx` lowering diagnostics;
- canonical typed-IR records and an input-sensitive digest.

Storage is bounded and explicit. Capacity exhaustion fails closed with a
stable diagnostic instead of growing memory implicitly.
Expression and statement/block recursion are each capped at 128 levels and
fail with diagnostic `1408`.

## Executable acceptance boundary

`tests/selfhost/full/test_full_frontend.sh` proves all of the following:

1. The complete ten-module DXL source closure checks and builds twice.
2. Both builds are byte-identical.
3. A positive program traverses lexer, parser, semantics, and lowering with no
   diagnostics, and both executables emit byte-identical records.
4. A one-literal source mutation changes the typed-IR digest.
5. Parser and semantic failures have deterministic codes and locations.
6. Maximum and derived-minimum integer expressions lower without overflow.
7. Deep expressions and statement blocks reject at the deterministic recursion
   limit instead of exhausting the process stack.
8. A forward type-inference chain longer than eight links reaches a real fixed
   point, and unknown aggregate literals fail closed.
9. `model.dxl` is accepted end-to-end by the resulting frontend.
10. The complete `main.dxl` source is accepted lexically and syntactically, but
   is rejected at semantic closure. This guard prevents a premature
   self-hosting claim.

## Remaining self-host blockers

- recursively load and resolve the complete import graph rather than analyze
  one file in isolation;
- intern named types and connect struct fields, enum variants, and field access
  to their declarations;
- define typed signatures and ownership effects for the compiler's builtin
  operations over arrays, slices, results, file arguments, and printing;
- complete call arity/parameter checking, aggregate ownership, comptime
  execution, and all full-language diagnostics;
- lower the typed IR through the production backend into a compiler executable;
- then pass a genuine source-sensitive Stage 0 to Stage 1, Stage 1 to Stage 2,
  and Stage 2 to Stage 3 byte-identity gate without an external compiler in the
  later-stage process trace.

Until those gates pass, this directory must be described as an integrated
DXL-native frontend foundation only.

See [PROFILE.md](PROFILE.md) for the exact grammar and acceptance boundary and
[DIAGNOSTICS.md](DIAGNOSTICS.md) for the stable code registry.
