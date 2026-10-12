# DXL-native compiler and self-hosting status

Aegis 2.4.3 advances two DXL-native compiler paths:

1. an integrated lexer→parser→semantic→typed-IR frontend foundation under `compiler/dxl/selfhost/full/`;
2. a real source-dependent native-core compiler and static executable emitter under `compiler/dxl/native/` and `runtime/native/`.

Neither path is labeled self-hosting.

## What is proven now

- The integrated frontend executable builds deterministically and produces byte-identical output for repeated inputs.
- A one-literal source mutation changes its canonical typed-IR digest, preventing a fixed-output implementation from passing.
- It handles boundary integers, long forward inference, multiple syntax and semantic diagnostics, recursion limits, aggregate gaps, and a partial compiler-source self-acceptance case.
- The native-core compiler builds deterministically from its shipped DXL source.
- Repeated compilation of one accepted program is byte-identical; a different source produces different executable bytes.
- Generated executables run with exact expected output and have the documented static ELF structure.
- The shipped native compiler matches a fresh source rebuild byte for byte.

These are compiler and reproduction milestones. They are not stage self-compilation.

## Exact first failing stage

The pinned compatibility seed deterministically compiles the bounded native compiler source into the shipped `dxlc-native` executable. For that bounded compiler, this is a seed-produced first stage. When `dxlc-native` is then asked to compile the same source, it rejects immediately with `AEG2702`: the bounded Stage 1 cannot produce Stage 2.

A complete compiler source closure is a separate target. The native-core grammar accepts only one scalar `main` function or test blocks, while the complete implementation would require imports, helper functions, arrays, slices, result values, file primitives, and multiple modules. No complete source closure capable of entering the full acceptance sequence exists yet.

The integrated frontend accepts its bounded model module end to end and parses its entry module without lexer or parser diagnostics. The pinned frontend separately checks and builds the ten-module implementation closure. When the new frontend analyzes its entry module, semantic closure still fails because import-graph symbol merging, builtin signatures/effects, and named aggregate field schemas are incomplete. It therefore cannot yet feed a production backend to create a complete compiler stage.

## Acceptance gate

Self-hosting will be claimed only after all of the following pass:

1. A pinned seed compiles one canonical DXL compiler source closure to Stage 1.
2. With the seed unavailable, Stage 1 compiles the same closure to Stage 2.
3. Stage 2 compiles the same closure to Stage 3.
4. Stage 2 and Stage 3 are byte-identical.
5. Stage 2 and Stage 3 pass identical positive, negative, diagnostic, module, ownership, compile-time, typed-IR, object, executable, and runtime corpora.
6. Compiler/build-tool environment variables are poisoned and process tracing shows no fallback compiler or linker after Stage 1.
7. Two source programs with different behavior produce different correct artifacts.
8. A deliberate compiler-source mutation changes the next stage and then reconverges on the following stage.

The last two conditions prevent a stage from passing by copying itself or emitting a canned binary.

## Remaining compiler work

- complete import-graph semantic closure;
- model builtin signatures, effects, and file operations in the native frontend;
- complete named structure/field and aggregate typing;
- add full ownership and bounded compile-time semantics;
- define an executable canonical IR for every construct used by the compiler;
- adapt the source-dependent backend beyond the scalar native core;
- add function calls, parameters, managed storage, results, and multi-module lowering;
- run the acceptance gate above.

Until then, use the pinned compatibility frontend for general DXL checking/TIR/formatting and the DXL-authored native compiler for the documented native core profile. See [Compiler architecture](COMPILER_ARCHITECTURE.md) and [Implementation status](IMPLEMENTATION_STATUS.md).
