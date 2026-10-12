# Safety and execution boundaries

Aegis 2.4.3 has two distinct execution paths. Their guarantees must not be combined.

## DXB3 verified path

DXS and DXASM compile or assemble to DXB3. Before execution, the auditor and VM validate:

- container structure, length, version, and checksum;
- instruction encodings and structured control flow;
- stack effects and maximum depth;
- declared worst-case steps and heap budget;
- required capability mask against the supplied policy;
- checked arithmetic and valid termination;
- generation-checked memory/byte handles, bounds, stale handles, double release, and leak-free successful termination.

The implemented capability surface covers integer output and bounded byte output. There is no ambient filesystem, network, process, dynamic-loading, general native-call, or JIT operation in the verified profile.

Successful fixture runs can write deterministic proof records. This is a concrete verifier/runtime contract, not a general formal proof of arbitrary source programs.

## DXL native-core path

DXL native-core source compiles directly to a static executable. Its tested protections are:

- checked addition, subtraction, multiplication, negation, and `i32` narrowing;
- lexical local scope and compile-time type checks;
- short-circuit Boolean operations;
- runtime assertions;
- exactly 1,000,000 shared loop-condition evaluations before status `72`;
- user process returns restricted to `0..63`, reserving statuses `70..73` for generated runtime failures;
- explicit parser, local, call-site, source-size, and nesting limits;
- a read/write non-executable stack declaration;
- no interpreter or dynamic dependency;
- atomic output replacement only after compilation succeeds.

Native output does not pass through DXB3. It has no DXB3 capability mask, container audit, generation-checked heap model, whole-program verifier proof, or `.proof` record. The loop-fuel bound covers `while` condition evaluations; it is not a bound on every executed instruction.

See [DXL native core profile](NATIVE_PROFILE.md) for the exact syntax and limits.

## Compiler foundations

The integrated frontend and focused compiler components use fixed-capacity arenas, recursion guards, deterministic inference passes, explicit diagnostics, and runner timeouts. These implementation bounds prevent silent unbounded growth in the tested cases; they are not a claim that the incomplete frontend safely compiles arbitrary production input.
