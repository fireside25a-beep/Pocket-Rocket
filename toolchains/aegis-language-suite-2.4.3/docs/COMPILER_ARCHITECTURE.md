# Compiler and runtime architecture

## DXL compatibility path

The general DXL path loads modules, lexes, parses, resolves declarations, checks types and ownership, evaluates bounded compile-time code, formats source, and emits inspectable typed-IR text.

```text
DXL source + imports -> compatibility frontend -> diagnostics / formatted source / typed IR
```

This is the supported path for the broader language surface in [DXL language reference](DXL_LANGUAGE_REFERENCE.md). It does not emit a native executable through the public 2.4.3 interface.

## DXL native-core path

The DXL-authored compiler in `compiler/dxl/native/` uses the shared table-driven lexer, a profile parser/type checker, direct x86-64 instruction encoding, a small integer-output runtime emitter, and an ELF64 executable writer.

```text
native-core DXL -> DXL lexer -> profile parser/type checks -> x86-64 bytes -> static ELF64
```

Output is source-dependent. The emitter creates one read/execute load segment and an explicit non-executable stack declaration, with no interpreter, dynamic section, relocation processing, or external runtime dependency. `build`, `run`, and `test` use this path.

The native compiler supports only the bounded [DXL native core profile](NATIVE_PROFILE.md); it is not the backend for every construct accepted by the compatibility frontend.

## Integrated DXL-native frontend foundation

`compiler/dxl/selfhost/full/` connects:

1. table-driven lexing and source coordinates;
2. precedence parsing with bounded recovery and recursion guards;
3. lexical scopes, symbol tables, deterministic type propagation, and semantic diagnostics;
4. canonical input-derived typed-IR records.

Its test driver accepts arbitrary source files, produces deterministic summaries, distinguishes a one-literal source mutation, handles integer boundaries, reports multiple exact diagnostics, and rejects recursion or capacity exhaustion. It parses the integrated entry module without syntax diagnostics; the pinned frontend separately checks and builds the ten-module implementation closure. Import-closure and named-aggregate semantics are not complete enough for the new frontend to type that closure itself.

The older component directories remain useful focused foundations: lexer diagnostics, parser arenas/recovery, and a fixed relocatable-object layout with minimal line data.

## DXS path

```text
DXS source -> dxscc -> DXB3 -> dxaudit -> dxvm + policy -> output + proof
```

The DXS compiler is authored in DXL. It validates structured operations, derives bounded resource declarations, and writes a DXB3 container.

## DXASM path

```text
DXASM source -> dxasm -> DXB3 -> dxaudit -> dxvm + policy -> output + proof
```

The DXL-authored assembler maps explicit mnemonics and operands to the same instruction model.

## Shared DXB3 boundary

DXS and DXASM converge before execution. The auditor and VM validate the header, checksum, capabilities, stack depth, structured control flow, worst-case steps, heap budget, instruction encodings, and termination rules. This allows high-level scripts and explicit assembly to be compared through one execution and proof model.

## Reproduction boundary

The maintainer gate rebuilds and byte-compares seven DXL-authored shipped tools. The native compiler's repeat seed-build identity proves deterministic reproduction from its DXL source, but it is not self-compilation. Complete self-hosting requires a compiler stage to compile the same compiler source closure without returning to the pinned frontend; see [DXL-native compiler status](SELF_HOSTING.md).
