# Aegis 2.4.3 support

This document defines the tested boundary of the standalone 2.4.3 distribution. Automated gates, not source-file presence or accepted command names, establish support.

## Status terms

| Term | Meaning |
| --- | --- |
| **Tested** | Exercised by a blocking release gate on the stated host. |
| **Foundation** | Implemented and directly tested, but not integrated as a complete replacement for the supported path. |
| **Source-reproduced** | A fresh deterministic build from the shipped DXL sources matches the shipped executable byte for byte. |
| **Unsupported** | Not covered by the release gate and not claimed. |

## Host support

| Host | Bundled toolchain | Status |
| --- | --- | --- |
| Linux x86-64 with glibc 2.34+ | Included under `toolchain/linux-x86_64/` | **Tested** |
| Linux x86-64 with an older glibc or a different system runtime | No compatibility promise | **Unsupported** |
| Other operating systems or architectures | No bundled executable set | **Unsupported** |

`make setup` checks Linux and x86-64. The bundled compiler, assembler, auditor, and VM executables are dynamically linked and have a maximum required symbol version of glibc 2.34. Generated DXL native-core programs are separate static executables and have no glibc dependency.

## DXL command and target support

| Path | Status | Guarantee |
| --- | --- | --- |
| `dxlc check`, `emit-tir`, `fmt` | **Tested compatibility profile** | General source corpus, formatting checks, typed-IR identity |
| `dxlc build`, `run`, `test` | **Tested native core profile** | Source-dependent static x86-64 Linux output, exact diagnostics, runtime matrix |
| `--target native` | **Tested** | Alias for x86-64 Linux |
| `--target x86_64-linux` | **Tested** | Same emitter as `native` |
| Any other target | **Unsupported** | Rejected by the public wrapper |

The native path uses `dxlc-native` and operates when the compatibility frontend is absent. Its compiler seed is source-reproduced from [`compiler/dxl/native/`](../compiler/dxl/native/) by the maintainer gate. This is not self-hosting: the native profile is smaller than the language used to implement that compiler.

## Component support

| Component | 2.4.3 status | Tested boundary |
| --- | --- | --- |
| General DXL | **Tested profile** | Modules, declarations, ownership, bounded compile time, positive/negative checking, formatting, typed IR |
| DXL native core | **Tested** | Scalar locals, checked arithmetic/casts, branches, loop fuel, printing, assertions, tests, static executables |
| DXS | **Tested; source-reproduced tool** | Compile to DXB3, positive/negative corpus, repeat bytes, VM execution |
| DXASM | **Tested; source-reproduced tool** | Assemble to DXB3, positive/negative corpus, repeat bytes, VM execution |
| DXB3 audit and VM | **Tested; source-reproduced tools** | Structure, bounds, capabilities, handles, execution, proof records |
| Integrated DXL-native frontend | **Foundation** | Lexer→parser→scope/type analysis→canonical TIR, mutation and error matrices |
| Parser/lexer/object components | **Foundation** | Tables, spans, recovery, bounded arenas, fixed relocatable layout fixture |
| Complete DXL-native self-host compiler | **Unsupported as complete** | First compiler stage cannot yet be produced from the full source closure |

The source-reproduction gate covers `dxscc`, `dxasm`, `dxvm`, `dxaudit`, `dxs24cc`, `dxvm24`, and `dxlc-native`. It deliberately does not claim source reproduction for the pinned general compatibility frontend.

## Safety boundary

DXB3 guarantees apply only to DXS/DXASM programs executed through the auditor and VM. They include fail-closed container validation, declared resource checks, capability enforcement, structured control flow, checked arithmetic, generation-checked handles, and deterministic proof records for successful runs.

Native DXL programs use checked arithmetic, checked narrowing, assertions, a non-executable stack declaration, lexical locals, and loop fuel. They do not pass through DXB3 and therefore do not receive DXB3 capability or proof guarantees.

See [Safety model](SAFETY_MODEL.md) and [DXL native core profile](NATIVE_PROFILE.md).

## Compatibility policy

- The references shipped in this archive describe only 2.4.3.
- Bytecode consumers must validate the DXB3 version and every container invariant.
- Reproducibility claims apply to the exact supported host, tool bytes, inputs, and named gates.
- A new target or feature becomes **Tested** only after positive, negative, deterministic-repeat, artifact-inspection, and execution tests where applicable.
- Typed-IR text and the native-core subset may evolve until separately declared stable.

Known incomplete work is tracked in [Implementation status](IMPLEMENTATION_STATUS.md) and [Maturity roadmap](ROADMAP.md). Report security-sensitive defects through [Security policy](../SECURITY.md).
