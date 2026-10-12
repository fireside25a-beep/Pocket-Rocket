# Validation matrix

The fixed 0.1.0 release gate has 37 counted checks: strict compiler builds, path-sensitive analysis, sanitizer execution, all handwritten positives, canonical-AST equivalence, repeated byte identity for every emitted artifact, independent proof-hash recomputation, safe-Rust emission markers, deterministic negatives, source mutations, 512 generated semantic vectors with GCC/Clang C oracles, path-collision rejection, the complete Aegis 2.4.0 11/11 bootstrap/toolchain gate, and DXL/DXS/DXASM certificate consensus.

`rustc` is an additional environment-dependent gate. If present, generated Rust is compiled and run; if absent, it must print `SKIP`. It is deliberately not converted into a PASS.
