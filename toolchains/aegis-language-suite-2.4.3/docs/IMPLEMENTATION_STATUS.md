# Aegis 2.4.3 implementation status

The passing gates define the implemented boundary. This page separates public behavior, compiler foundations, and future work.

## Public release surface

### General DXL compatibility profile

- lexical, syntactic, name, type, ownership, and bounded compile-time checks;
- imports, constants, structures, enumerations, functions, compile-time functions/blocks, and tests;
- checked `i64`/`i32` operations and casts;
- explicit `result_i64`, owned `array_i64`, and borrowed `slice_i64` rules;
- deterministic formatting checks;
- deterministic typed-IR text emission;
- positive, negative, overflow, import-cycle, ownership, and compile-time corpora.

Public commands: `check`, `emit-tir`, and `fmt`.

### DXL native core profile

- DXL-authored source-dependent compiler;
- public `build`, `run`, and `test` commands;
- scalar `i64` locals, Boolean expressions, lexical block scope, assignment, branches, loops, printing, assertions, and explicit `i32` returns;
- short-circuit `&&`/`||`;
- checked addition, subtraction, multiplication, negation, and narrowing;
- 64-level syntax bound, 64 visible locals, 64 print sites, 65,536-byte source limit, and exactly 1,000,000 shared loop-condition evaluations;
- user process returns restricted to `0..63`, with reserved deterministic failure statuses `70..73`;
- stable machine-readable compiler diagnostics and human-readable public messages;
- deterministic static Linux x86-64 executables with a non-executable stack and no dynamic loader;
- failed compilation preserves an existing output;
- isolated compilation without the compatibility frontend present.

The native compiler does not yet accept the complete general DXL language.

### DXS, DXASM, and DXB3

- deterministic DXS compilation and DXASM assembly to DXB3;
- positive and negative corpora;
- bounded structured control flow and checked stack operations;
- generation-checked memory and byte handles;
- strict header, length, checksum, profile, capability, stack, step, heap, instruction, and termination validation;
- deterministic audit, execution output, and proof records for the release fixtures.

## DXL-native compiler foundations

### Integrated frontend

`compiler/dxl/selfhost/full/` implements an arbitrary-input lexer→parser→semantic→typed-IR pipeline with:

- exact source-backed tokens;
- precedence expressions and declaration/statement parsing;
- multiple diagnostic recovery with progress guards;
- lexical scopes and bounded symbol/AST/TIR arenas;
- deterministic type propagation with an outer-node inference budget;
- canonical source-sensitive typed-IR records;
- recursion and capacity rejection;
- stable parser, semantic, and lowering identifiers.

Its dedicated gate passes positive, mutation, integer-boundary, forward-inference, multi-error, deep-recursion, aggregate-gap, and partial self-acceptance tests. It accepts `model.dxl` end to end and parses the integrated entry module without syntax diagnostics; the pinned frontend separately checks and builds the ten-module source closure. Full import/builtin/named-aggregate semantic closure in the new frontend remains incomplete.

### Focused foundations

- 256-entry byte classification and sorted keyword recognition;
- file-aware token spans and multiple lexical diagnostics;
- parser span/AST arenas and synchronization tests;
- deterministic byte writers;
- fixed x86-64 relocatable-object layout fixture with a minimal line table.

The fixed object fixture is not the production native-core backend; the latter emits source-dependent static executables from `compiler/dxl/native/`.

## Source reproduction

Fresh repeat builds of these DXL-authored tools match the shipped bytes:

- `dxscc`;
- `dxasm`;
- `dxvm`;
- `dxaudit`;
- `dxs24cc`;
- `dxvm24`;
- `dxlc-native`.

This is seed reproduction, not compiler self-hosting. The general compatibility frontend is outside the source-reproduced set.

## Standard library

Implemented modules provide bounded validation, canonical non-negative integer serialization, and deterministic fixed-capacity collections. Filesystem, network, process, dynamic-loading, and ambient native-call interfaces are not part of the verified DXB3 capability surface.

## Explicitly incomplete

- complete DXL compiler self-reproduction and stage identity;
- full import/builtin/aggregate semantics in the DXL-native integrated frontend;
- a general native backend for every DXL construct;
- generic functions, structures, arrays, slices, and algebraic standard-library types;
- package registry, dependency fetching, and incremental package builds;
- additional instruction sets, operating systems, and object formats;
- language server and documentation generator;
- complete variable-level debug information and source debugger;
- general lifetimes and owned aggregate fields;
- deterministic concurrency.

See [Support](SUPPORT.md), [Testing](TESTING.md), and [Maturity roadmap](ROADMAP.md).
