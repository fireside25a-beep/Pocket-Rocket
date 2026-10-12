# Language overview

## DXL

DXL is the statically typed language at the base of the suite. It is used for ordinary programs and for implementation of the higher layers of the toolchain. Its implemented feature set includes typed functions, checked integer arithmetic, booleans, structs, enums, modules, compile-time evaluation, explicit result values, owned arrays, borrowed slices, deterministic formatting and target-aware compilation.

## DXS

DXS is the scripting layer. It favors compact deterministic source and a bounded execution model. Source is compiled to DXB3, verified before execution and then run by the shared VM.

## DXASM

DXASM is the assembly layer. It maps explicit mnemonics and operands to the DXB3 instruction model. It exists for low-level programming, exact fixtures, VM tests and bytecode-oriented tooling.

## Shared execution layer

DXS and DXASM converge on DXB3. This gives the suite one verifier/runtime boundary for capability checks, resource accounting, bytecode validation and deterministic execution proofs.
