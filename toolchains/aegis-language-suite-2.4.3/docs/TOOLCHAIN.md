# Aegis 2.4.3 toolchain

The distribution contains a checksum-pinned toolchain for Linux x86-64 with glibc 2.34 or newer. `make setup` installs a disposable copy under `build/`; it never modifies the host system.

## Public commands

| Executable | Role | Example |
| --- | --- | --- |
| `dxlc` | General DXL check/TIR/format plus native-core build/run/test | `dxlc build main.dxl -o main` |
| `dxscc` | DXS to DXB3 compiler | `dxscc source.dxs program.dxb` |
| `dxasm` | DXASM to DXB3 assembler | `dxasm source.dxasm program.dxb` |
| `dxaudit` | DXB3 structural/resource auditor | `dxaudit program.dxb` |
| `dxvm` | DXB3 verifier, VM, and proof writer | `dxvm program.dxb policy.bin run.proof` |
| `dxs24cc` | Extended bounded DXS-profile compiler | `dxs24cc source.dxs program.dxb` |
| `dxvm24` | Matching extended DXB3-profile VM | `dxvm24 program.dxb policy.bin run.proof` |

## DXL dispatch

`dxlc` has two internal paths with different accepted language surfaces:

| Commands | Engine | Contract |
| --- | --- | --- |
| `check`, `emit-tir`, `fmt` | Pinned compatibility frontend | Broader DXL declarations, modules, ownership, and compile-time checks |
| `build`, `run`, `test` | DXL-authored `dxlc-native` | [Bounded native core profile](NATIVE_PROFILE.md) |

The native path does not invoke or require the compatibility frontend. The regression gate copies only the public wrapper, `dxlc-native`, and its diagnostic table into an isolated layout and proves native compilation and execution there.

### General DXL

```sh
dxlc check program.dxl
dxlc emit-tir program.dxl -o program.tir
dxlc fmt program.dxl --check
```

### Native-core DXL

```sh
dxlc build program.dxl -o program
dxlc run program.dxl
dxlc test tests.dxl
```

`build` writes a temporary sibling first and atomically replaces the destination only after success. Missing, unreadable, oversized, malformed, or unsupported sources leave a pre-existing output untouched.

`dxlc targets` reports:

```text
native -> x86_64-unknown-linux-gnu
x86_64-linux -> x86_64-unknown-linux-gnu
```

These are two names for one emitter, not two independent targets.

## Artifact flows

| Source path | Transformation | Result |
| --- | --- | --- |
| DXL general | `dxlc check` / `emit-tir` / `fmt` | Diagnostics, canonical source, typed-IR text |
| DXL native core | `dxlc build` | Static ELF64 x86-64 executable |
| DXS | `dxscc` → `dxaudit` → `dxvm` | DXB3, audit, output, proof |
| DXASM | `dxasm` → `dxaudit` → `dxvm` | DXB3, audit, output, proof |

Native DXL output does not pass through DXB3. The two execution paths have distinct safety and evidence contracts.

## File types

| Suffix | Meaning |
| --- | --- |
| `.dxl` | DXL source |
| `.dxs` | DXS source |
| `.dxasm` | DXASM source |
| `.dxb` | DXB3 container |
| `.tir` | Inspectable DXL typed-IR text |
| `.proof` | Deterministic DXB3 execution proof record |
| `.audit` | Human- or machine-readable artifact audit |
| `.bin` | Explicit binary fixture or native evidence executable |

## Integrity

Verify bundled tool bytes:

```sh
(cd toolchain/linux-x86_64 && sha256sum -c SHA256SUMS.txt)
```

The manifest covers all seven public executables, the compatibility frontend, the DXL native compiler, and the native diagnostic table. `make setup` verifies before copying.

## Source reproduction

```sh
make reproduce
```

This maintainer gate builds each DXL-authored shipped tool twice from the included source, compares the two outputs, and compares the result with the shipped executable. It covers:

- `dxscc`;
- `dxasm`;
- `dxvm`;
- `dxaudit`;
- `dxs24cc`;
- `dxvm24`;
- `dxlc-native`.

The compatibility frontend is a pinned seed and is outside this source-reproduction list. `make reproduce`, `make native-source`, and compiler-foundation builds require a compatible host executable builder. Public native compilation through the already verified `dxlc-native` does not.

See [Testing](TESTING.md), [Support](SUPPORT.md), and [DXL-native compiler status](SELF_HOSTING.md).
