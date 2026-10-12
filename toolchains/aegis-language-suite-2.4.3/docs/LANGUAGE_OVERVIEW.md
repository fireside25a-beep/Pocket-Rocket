# Language overview

## DXL

DXL is the statically typed language at the base of the suite. The general compatibility profile supports typed functions, checked integer operations, booleans, named structures and enumerations, relative modules, bounded compile-time evaluation, explicit result values, owned `array_i64` values, borrowed `slice_i64` views, formatting, checking, and typed-IR text emission.

A separately documented [native core profile](NATIVE_PROFILE.md) compiles scalar `main` programs and test blocks directly to static Linux x86-64 executables. It includes checked scalar arithmetic, lexical locals, branches, bounded loops, printing, assertions, and process returns. Successful general checking does not imply that a file belongs to the native core profile.

DXL also authors the DXS compiler, DXASM assembler, DXB3 runtime tools, native-core compiler, and new integrated frontend foundation in this repository.

## DXS

DXS is the compact scripting layer. It favors deterministic tokens, structured bounded control flow, and a small auditable instruction surface. Source compiles to DXB3, is verified before execution, and then runs under an explicit capability policy.

## DXASM

DXASM is the explicit assembly layer for DXB3. It maps mnemonics and operands to the shared instruction model and is useful for exact fixtures, low-level programs, verifier tests, and bytecode tooling.

## DXB3

DXB3 is the common execution layer for DXS and DXASM. The auditor and VM validate the container, checksum, capabilities, control flow, stack effects, declared resource bounds, heap handles, and termination rules before execution. Successful runs can emit deterministic proof records.

DXL native executables do not use DXB3. Their tested limits and safety boundary are defined separately in the [native core profile](NATIVE_PROFILE.md).
