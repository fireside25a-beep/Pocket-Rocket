# Determinism contract

Aegis defines deterministic compilation or execution as identical observable artifacts for identical explicit inputs within the same supported release profile and pinned environment.

## Explicit inputs

Relevant inputs include:

- source and resolved module bytes;
- compiler, assembler, auditor, and VM executable identity;
- selected supported target/profile;
- DXB3 policy bytes;
- declared capabilities and resource limits.

Release tests do not intentionally depend on current time, randomized hashing, directory iteration order, absolute workspace paths, or undeclared ambient capabilities.

## Compared artifacts

- general DXL check transcripts and typed-IR text;
- native DXL static executable bytes and process output;
- integrated DXL-native frontend executables and canonical typed-IR records;
- DXS-compiled and DXASM-assembled DXB3 bytes;
- DXB3 audit summaries, VM output, and proof records;
- fresh DXL-authored tool executables in the pinned maintainer environment;
- the fixed relocatable-object fixture.

The relevant gates independently generate two copies and compare with `cmp`. Source-sensitivity tests also require a changed source to change the resulting TIR or executable. SHA-256 manifests provide integrity after the equality tests pass.

## Native output normalization

The native core emitter omits timestamps, build identifiers, section tables, interpreter entries, and dynamic dependencies. Its byte order, headers, instruction order, runtime bytes, and layout are deterministic functions of the accepted source and release implementation.

## DXB3 execution

DXB3 programs execute with explicit policy bytes and verifier-derived bounds. For the committed matrix, repeated executions produce byte-identical output and proof records.

## Scope

Runtime artifact determinism is claimed on the supported Linux x86-64 profile for the named gates. Exact source-to-shipped executable reproduction additionally uses the pinned Ubuntu 24.04 maintainer environment described in [Testing](TESTING.md). A recognized but unsupported target, different seed builder, or changed system environment does not inherit these claims automatically.
