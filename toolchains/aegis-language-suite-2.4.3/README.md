# Aegis Language Suite 2.4.3

Aegis is a standalone three-language suite for deterministic compilation and explicit execution boundaries.

| Layer | Source | Purpose |
| --- | --- | --- |
| **DXL** | `.dxl` | Statically typed language with checked integers, compile-time evaluation, ownership checks, typed IR, and a bounded native core profile |
| **DXS** | `.dxs` | Compact deterministic scripting language compiled to verified bytecode |
| **DXASM** | `.dxasm` | Explicit assembly notation for the same bytecode instruction model |
| **DXB3** | `.dxb` | Audited execution format with declared limits, capability checks, and reproducible VM evidence |

The repository contains language and implementation sources, a checksum-pinned Linux x86-64 toolchain, specifications, examples, positive and negative corpora, committed loop evidence, continuous-integration gates, and deterministic release packaging. There are no nested release archives.

## What is new in 2.4.3

- `dxlc build`, `dxlc run`, and `dxlc test` now use a DXL-authored, source-dependent native compiler for the documented DXL native core profile.
- Native output is a deterministic static Linux x86-64 executable written directly by the DXL backend; it needs no separate linker or dynamic loader.
- The native profile has checked arithmetic and narrowing, lexical local scope, short-circuit Boolean operations, assertions, a shared loop-fuel bound, stable diagnostics, and atomic output replacement.
- The DXL-native frontend foundation now integrates the table lexer, precedence parser, scope/type analysis, and canonical typed-IR lowering on arbitrary input.
- The release matrix includes a native DXL counter executable and audit record alongside the DXS and DXASM DXB3 proofs.

## Tested boundary

The bundled tools are tested on **Linux x86-64 with glibc 2.34 or newer**. Setup is repository-local and requires no network access.

| Path | Status | Output |
| --- | --- | --- |
| General DXL `check`, `emit-tir`, `fmt` | Tested compatibility profile | Diagnostics, formatted source, typed IR |
| DXL native-core `build`, `run`, `test` | Tested | Static x86-64 Linux executable |
| DXS compilation | Tested | DXB3 |
| DXASM assembly | Tested | DXB3 |
| DXB3 audit and execution | Tested | Audit, output, deterministic proof record |
| Integrated DXL-native frontend | Tested foundation | Canonical typed-IR records for its bounded profile |
| Complete self-reproducing DXL compiler | Not claimed | Acceptance gate remains open |
| Other hosts and targets | Not claimed | No release artifact |

The generated native DXL executables are static and do not depend on glibc. The glibc requirement applies to the bundled compiler and VM executables used to create them.

See [Support](docs/SUPPORT.md), [DXL native core profile](docs/NATIVE_PROFILE.md), and [Implementation status](docs/IMPLEMENTATION_STATUS.md) for the exact contract.

## Quick start

### Verify and install locally

```sh
make setup
```

This verifies every bundled file against `toolchain/linux-x86_64/SHA256SUMS.txt` and copies the toolchain into `build/`. Nothing is installed system-wide.

### Build and run DXL natively

```sh
build/bin/dxlc build examples/loops/dxl/native_counter.dxl -o build/native-counter
build/native-counter

build/bin/dxlc run examples/loops/dxl/native_counter.dxl
build/bin/dxlc test tests/native/positive/assertions.dxl
```

The standalone executable and `dxlc run` each print:

```text
10
```

Native compilation supports the bounded syntax listed in [DXL native core profile](docs/NATIVE_PROFILE.md). Use `dxlc check` for the broader DXL compatibility profile.

### Check general DXL and inspect typed IR

```sh
build/bin/dxlc check examples/loops/dxl/counter.dxl
build/bin/dxlc emit-tir examples/loops/dxl/counter.dxl -o build/counter.tir
```

### Compile and execute DXS

```sh
build/bin/dxscc examples/loops/dxs/counter.dxs build/counter-dxs.dxb
build/bin/dxaudit build/counter-dxs.dxb
build/bin/dxvm build/counter-dxs.dxb examples/policy_all.bin build/counter-dxs.proof
```

### Assemble and execute DXASM

```sh
build/bin/dxasm examples/loops/dxasm/counter.dxasm build/counter-dxasm.dxb
build/bin/dxaudit build/counter-dxasm.dxb
build/bin/dxvm build/counter-dxasm.dxb examples/policy_all.bin build/counter-dxasm.proof
```

Both DXB3 paths print `10` and produce deterministic proof records for this fixture.

## Command overview

| Command | Role |
| --- | --- |
| `dxlc check FILE` | Check the general DXL compatibility profile |
| `dxlc emit-tir FILE -o FILE` | Emit deterministic typed-IR text |
| `dxlc fmt FILE [--check]` | Format or verify DXL formatting |
| `dxlc build FILE -o FILE` | Compile the DXL native core profile |
| `dxlc run FILE` | Compile and run a native-core program |
| `dxlc test FILE` | Compile and execute native-core test blocks |
| `dxscc SOURCE OUTPUT` | Compile DXS to DXB3 |
| `dxasm SOURCE OUTPUT` | Assemble DXASM to DXB3 |
| `dxaudit PROGRAM` | Audit a DXB3 container |
| `dxvm PROGRAM POLICY PROOF` | Verify and execute DXB3 |
| `dxs24cc`, `dxvm24` | Extended bounded DXS/DXB3 profile pair |

`dxlc targets` reports the two aliases for the one native target tested in this release: `native` and `x86_64-linux`.

## Verification

```sh
make clean
make check
```

The installed release gate covers:

- general DXL checking, formatting, typed-IR identity, and positive/negative corpora;
- public native `build`/`run`/`test`, exact diagnostics, failed-output preservation, and operation without the compatibility frontend present;
- shipped native compiler non-canned source sensitivity, static-executable inspection, runtime traps, limits, and rejection cases;
- DXS and DXASM compilation, audit, execution, negative cases, byte identity, output identity, and proof identity;
- repository versioning, checksums, documentation links, source hygiene, shell syntax, and release inventory.

The maintainer gate adds deterministic source rebuilds, exact shipped-seed comparison, integrated lexer→parser→semantics→typed-IR tests, focused compiler foundations, mutation and boundary cases, and seven-tool source reproduction:

```sh
make maintainer-check
```

Exact byte reproduction is pinned in CI to the documented Ubuntu 24.04 maintainer environment. `make release` requires the maintainer gate, then packages and retests a clean extraction.

Every individual program invocation is time bounded. A timeout never counts as a valid rejection.

Committed loop evidence is under [`proofs/loops/`](proofs/loops/):

```sh
make matrix
(cd proofs/loops && sha256sum -c SHA256SUMS.txt)
```

The native DXL files in that directory are reproducibility and runtime evidence. The `.proof` files belong only to the verified DXB3 execution paths.

## Compiler-source boundary

The DXS compiler, DXASM assembler, DXB3 verifier, VM, auditor, DXL native-core compiler, native runtime emitter, and integrated frontend foundation are authored in DXL under `compiler/` and `runtime/`.

The native-core compiler is a real compiler: accepted source changes alter emitted machine code, and accepted programs execute independently of the compatibility frontend. Its accepted language subset is still smaller than the source used to implement the compiler, so it cannot compile itself. The broader DXL check/TIR/format path continues to use the pinned compatibility frontend seed.

Aegis will claim self-hosting only after one compiler source closure produces consecutive independent compiler stages whose final two executables are byte-identical and pass the same behavioral corpus. That gate does not pass in 2.4.3. See [DXL-native compiler status](docs/SELF_HOSTING.md).

## Repository map

| Path | Contents |
| --- | --- |
| `compiler/dxl/native/` | DXL native-core compiler and diagnostic registry |
| `compiler/dxl/selfhost/` | Table lexer, parser infrastructure, integrated frontend, and object foundations |
| `compiler/dxs/` | DXS compilers |
| `compiler/dxasm/` | DXASM assembler |
| `runtime/native/` | Static executable and integer-output emitters |
| `runtime/dxb3/` | DXB3 definitions, verifier, VM, and audit sources |
| `stdlib/` | Deterministic validation, serialization, and collection modules |
| `examples/` | DXL, DXS, and DXASM programs, including equivalent loops |
| `tests/` | Positive, negative, native, frontend, and matrix suites |
| `proofs/` | Committed reproducibility, audit, output, and DXB3 proof evidence |
| `toolchain/` | Checksum-pinned Linux x86-64 executables |
| `docs/` | Guides, references, specifications, status, and release policy |

## Documentation

Start with the [documentation index](docs/README.md).

- [Getting started](docs/GETTING_STARTED.md)
- [Language overview](docs/LANGUAGE_OVERVIEW.md)
- [DXL reference](docs/DXL_LANGUAGE_REFERENCE.md)
- [DXL native core profile](docs/NATIVE_PROFILE.md)
- [DXS reference](docs/DXS_LANGUAGE_REFERENCE.md)
- [DXASM reference](docs/DXASM_LANGUAGE_REFERENCE.md)
- [DXB3 specification](docs/DXB3_SPECIFICATION.md)
- [Compiler and runtime architecture](docs/COMPILER_ARCHITECTURE.md)
- [Toolchain guide](docs/TOOLCHAIN.md)
- [Testing guide](docs/TESTING.md)
- [Proofs and reproducibility](docs/PROOFS.md)
- [Safety model](docs/SAFETY_MODEL.md)
- [Support policy](docs/SUPPORT.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [DXL-native compiler status](docs/SELF_HOSTING.md)
- [Maturity roadmap](docs/ROADMAP.md)
- [Release process](docs/RELEASE_PROCESS.md)

## Contributing, security, and license

Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change. Report security-sensitive problems through [SECURITY.md](SECURITY.md). Project decisions follow [GOVERNANCE.md](GOVERNANCE.md), and community participation follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Aegis Language Suite 2.4.3 is distributed under the [MIT License](LICENSE).

Copyright © 2026 Alexandru Moraru.
