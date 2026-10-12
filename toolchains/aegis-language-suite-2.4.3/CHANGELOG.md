# Changelog

All notable changes to Aegis Language Suite are recorded here.

## 2.4.3 — 2026-08-07

### Languages

- Published DXL, DXS, and DXASM together with the DXB3 execution specification.
- Added bounded loop examples for all three source languages.
- Added checked arithmetic, compile-time evaluation, explicit results, owned arrays, borrowed slices, and balanced-ternary documentation.

### Compiler and runtime

- Shipped checksum-pinned Linux x86-64 toolchain executables.
- Added a DXL-authored native-core compiler for public `build`, `run`, and `test` commands.
- Added direct source-dependent static ELF64 executable emission with a non-executable stack and no dynamic loader.
- Added strict `main`/test command separation, checked arithmetic and narrowing, lexical scope, exact resource limits, atomic output replacement, and stable diagnostics.
- Reserved user return values to `0..63`; runtime statuses `70..73` now identify overflow, assertion, loop-fuel, and invalid-return failures without collision.
- Defined a general DXL compatibility profile for checking, typed-IR emission, and formatting.
- Shipped readable DXL sources for DXS compilation, DXASM assembly, DXB3 audit, verification, execution, and proof writing.
- Added an integrated DXL-authored lexer, parser, semantic analyzer, and canonical typed-IR foundation plus focused parser/object/line-table components.

### Verification

- Added positive and negative corpora for all three languages.
- Added timeout-aware rejection tests so a hang cannot pass as a successful diagnostic.
- Added repeated typed-IR, native executable, bytecode, output, and proof identity checks.
- Added source-sensitivity tests so a fixed or canned compiler artifact cannot pass.
- Added exact one-million loop-condition boundary tests and stable native failure-status tests.
- Added a three-language loop matrix with general DXL, native DXL, DXS, and DXASM evidence plus SHA-256 manifests.
- Added seven-tool DXL-source reproduction and exact shipped-byte comparison in the pinned maintainer environment.
- Added static source, documentation-link, version, checksum, archive, and repository-hygiene gates.

### Project

- Added a standalone documentation index, getting-started guide, toolchain guide, support contract, testing guide, proof guide, governance, contribution policy, release notes, and CI workflow.
- Defined Linux x86-64 with glibc 2.34 or newer as the tested bundled host.
- Kept incomplete self-hosting and unsupported targets outside the release claims.
