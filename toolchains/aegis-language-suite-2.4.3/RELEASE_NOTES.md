# Aegis Language Suite 2.4.3

Version 2.4.3 is a standalone release of DXL, DXS, DXASM, and the shared DXB3 verifier/runtime.

## Highlights

- One repository with language sources, compiler/runtime sources, documentation, examples, tests, and checksum-pinned tools.
- A DXL-authored, source-dependent native-core compiler behind `dxlc build`, `run`, and `test`.
- Direct deterministic static Linux x86-64 executable emission with no linker, interpreter, or dynamic dependency in generated programs.
- Strict command modes: `run` requires `main`; `test` requires test blocks; failed compilation preserves an existing output.
- Checked native arithmetic and casts, lexical scope, exact syntax/resource limits, one-million condition-evaluation fuel, and reserved failure statuses.
- General DXL checking, bounded compile-time evaluation, typed-IR emission, and formatting through the compatibility profile.
- DXS and DXASM compilation to the same fail-closed DXB3 format.
- Bounded DXB3 execution with capability checks, generation-checked handles, audit output, and deterministic proofs.
- Equivalent counter loops in all three languages, including native DXL executable evidence and DXB3 proof identity checks.
- An integrated DXL-authored lexer→parser→semantics→typed-IR frontend foundation with source mutation, boundary, recovery, and partial self-acceptance tests.
- Exact repeat reproduction of seven shipped DXL-authored tools in the pinned maintainer environment.
- A clean-release gate covering version consistency, host ABI, checksums, strict CLI behavior, source hygiene, documentation links, timeouts, byte identity, source sensitivity, and archive structure.

## Supported host

The bundled executable set is tested on Linux x86-64 with glibc 2.34 or newer. Generated native-core executables are static. Exact shipped-tool byte reproduction uses the pinned CI/maintainer environment described in [Testing](docs/TESTING.md). No other host or target is claimed.

## Known boundaries

- The native compiler accepts the bounded [DXL native core profile](docs/NATIVE_PROFILE.md), not the complete general DXL language.
- General DXL check/TIR/format operations still use a pinned compatibility frontend outside the seven-tool source-reproduction set.
- The DXL-authored compiler and frontend foundations are not a complete self-reproducing compiler. The bounded seed-produced compiler rejects its own source before Stage 2.
- The standard library and capability surface are deliberately bounded.
- Package registry, language server, source debugger, general lifetimes, and concurrency remain outside 2.4.3.

## Verification

```sh
make clean
make check
(make maintainer-check)
(cd proofs/loops && sha256sum -c SHA256SUMS.txt)
```

`make check` is the installed public gate. Official publication additionally requires `make maintainer-check`, which rebuilds compiler sources and all seven reproducible DXL-authored tools. See [README.md](README.md), [Support](docs/SUPPORT.md), and [Testing](docs/TESTING.md).
