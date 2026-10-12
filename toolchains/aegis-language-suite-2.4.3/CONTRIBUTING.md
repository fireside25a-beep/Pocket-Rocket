# Contributing to Aegis

Changes must keep implementation, language references, examples, diagnostics, and tests synchronized.

## Before opening a pull request

```sh
make matrix
make manifest
make clean
make maintainer-check
```

The commands must complete with zero failures for release-affecting compiler/runtime changes. `make matrix` refreshes committed evidence; `make manifest` records final tracked-file bytes; `make maintainer-check` includes the installed gate, compiler-foundation suites, source rebuilds, and seven-tool reproduction. Documentation-only changes may use `make check` when they do not alter a source, tool, manifest, or proof artifact.

## Change requirements

- Language behavior changes require an updated reference plus positive and negative tests.
- DXB3 changes require an updated specification, verifier tests, runtime tests, and a compatibility note.
- Native-compiler changes require positive, negative, boundary, source-sensitivity, repeat-byte, runtime, and executable-structure tests.
- Diagnostic changes require a unique stable code, a human-readable message, and synchronized machine-readable registries.
- Determinism changes require two independently generated artifacts and a byte comparison.
- Documentation examples must be complete files under `examples/` and exercised by a test gate.
- Unsupported behavior must not be described as implemented.

Keep general DXL frontend work under `compiler/dxl/selfhost/`, native-core compiler work under `compiler/dxl/native/`, native runtime emission under `runtime/native/`, DXS work under `compiler/dxs/`, DXASM work under `compiler/dxasm/`, and verified bytecode/runtime work under `runtime/dxb3/`.

## Pull requests

Use a focused title and explain:

1. the behavior changed;
2. the invariant preserved;
3. the exact tests added or updated;
4. any compatibility or security effect;
5. whether deterministic artifacts changed.

Security-sensitive changes follow [SECURITY.md](SECURITY.md), not the public issue tracker.
