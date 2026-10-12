# Aegis 2.4.3 documentation

This documentation is versioned with the Aegis 2.4.3 distribution. Examples and feature claims are tied to release tests; a recognized token, command, or target name alone is not a support guarantee.

> **Host boundary:** bundled tools are tested on Linux x86-64 with glibc 2.34 or newer. Native DXL output is static, but the tools that produce it use the stated host profile.

## Choose a path

| Goal | Start here |
| --- | --- |
| Install locally and run each language | [Getting started](GETTING_STARTED.md) |
| Compile a DXL program to a static executable | [DXL native core profile](NATIVE_PROFILE.md) |
| Learn the broader DXL syntax accepted for checking | [DXL language reference](DXL_LANGUAGE_REFERENCE.md) |
| Write deterministic scripts | [DXS language reference](DXS_LANGUAGE_REFERENCE.md) |
| Work directly with bytecode instructions | [DXASM language reference](DXASM_LANGUAGE_REFERENCE.md) |
| Implement or inspect a DXB3 producer/consumer | [DXB3 specification](DXB3_SPECIFICATION.md) |
| Verify support and nonclaims | [Support](SUPPORT.md) and [Implementation status](IMPLEMENTATION_STATUS.md) |
| Reproduce the release evidence | [Testing](TESTING.md) and [Proofs](PROOFS.md) |

All shell examples assume the repository root as the current directory.

## Languages and artifacts

- [Language overview](LANGUAGE_OVERVIEW.md)
- [DXL language reference](DXL_LANGUAGE_REFERENCE.md)
- [DXL native core profile](NATIVE_PROFILE.md)
- [DXS language reference](DXS_LANGUAGE_REFERENCE.md)
- [DXASM language reference](DXASM_LANGUAGE_REFERENCE.md)
- [DXB3 specification](DXB3_SPECIFICATION.md)
- [Value, memory, UTF-8, and error model](VALUE_MEMORY_AND_ERROR_MODEL.md)
- [Ternary architecture](TERNARY_ARCHITECTURE.md)

## Compiler, runtime, and safety

- [Compiler and runtime architecture](COMPILER_ARCHITECTURE.md)
- [Toolchain guide](TOOLCHAIN.md)
- [Safety model](SAFETY_MODEL.md)
- [Capability-aware standard library](CAPABILITY_STANDARD_LIBRARY.md)
- [Determinism contract](DETERMINISM.md)
- [Diagnostic codes](DIAGNOSTIC_CODES.md)

DXS and DXASM converge on the verified DXB3 path. DXL native-core executables are a separate path and do not inherit DXB3 capability, verifier, or proof guarantees.

## Project state and release discipline

- [Implementation status](IMPLEMENTATION_STATUS.md)
- [DXL-native compiler and self-hosting status](SELF_HOSTING.md)
- [Maturity roadmap](ROADMAP.md)
- [Testing guide](TESTING.md)
- [Proofs and reproducibility](PROOFS.md)
- [Support policy](SUPPORT.md)
- [Release process](RELEASE_PROCESS.md)
- [Contribution guide](../CONTRIBUTING.md)
- [Governance](../GOVERNANCE.md)
- [Security policy](../SECURITY.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)

The integrated DXL-native frontend and the DXL native-core compiler are substantial tested implementations, but neither can reproduce the complete compiler source closure. The exact acceptance gate is documented in [DXL-native compiler and self-hosting status](SELF_HOSTING.md).
