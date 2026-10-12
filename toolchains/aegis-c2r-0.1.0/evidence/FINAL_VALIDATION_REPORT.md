# Aegis-C2R 0.1.0 - Final Validation Report

Validation date: 24 August 2026  
Profile: `S0-DEFINED-I32`  
Primary implementation: strict C11  
Aegis integration: DXL + DXS + DXASM, clean 2.4.0 C stage-zero bootstrap

## Release result

- Fixed Aegis-C2R release gate: **37 PASS / 0 FAIL**.
- Aegis 2.4.0 vendored release gate: **11 PASS / 0 FAIL**.
- Generated semantic corpus: **512 deterministic cases**.
- Deterministic byte-mutation gate: **256/256 repeat-stable** (**11 accepted / 245 rejected**).
- Handwritten profile positives: **8/8 accepted**.
- Handwritten positive C oracle: **8/8 GCC/Clang runtime-output and exit-code consensus**.
- Handwritten negatives: **18/18 rejected deterministically**.
- DXL/DXS/DXASM structural certificate: **three-way consensus PASS**; DXS and DXASM repeated bytecode identity PASS.
- Strict GCC translator build: PASS.
- Strict Clang translator build: PASS.
- GCC path-sensitive `-fanalyzer`: PASS.
- ASan + UBSan positive/negative corpus: PASS.
- Rust compiler/runtime differential gate: **SKIP - rustc is not installed on this validation host**.

## Host compilers

- gcc (Debian 14.2.0-19) 14.2.0
- clang version 17.0.0 (https://github.com/swiftlang/llvm-project.git 10999b6d034fe318f3d56c83bddb6572593a8bb0)

## Artifact identities at validation

- optimized Linux x86-64 `aegis-c2r` SHA-256: `67353b4adf8003977d76486d3feb3288b8353493395495470f6d53f27060ebd8`
- 26-page engineering manual SHA-256: `a9c540d3e24dbcab2e07b0dd938bed4dbe9d215d025f83b1b457de8ebe8dcb9e`

## Corrections made before freeze

The release was not frozen at first failure. Finalization corrected the previously found file-close analyzer defect, DXL type mismatch, strict-Clang format checking issue, local self-initializer visibility, callable shadowing, output-path collision handling, and generated logical-vector warning behavior. The fixed corpus was rerun after those corrections.

## Claim boundary

These results establish deterministic translation and evidence behavior for the declared S0 profile and the shipped tests. They do not prove correctness for arbitrary C, repository-scale migration, formal equivalence, independent security certification, or a complete Rust compiler/runtime check on this host.
