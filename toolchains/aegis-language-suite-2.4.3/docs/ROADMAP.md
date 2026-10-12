# Aegis maturity roadmap

This roadmap orders work after the 2.4.3 standalone release. It is a plan, not a statement that the listed features already exist. [Implementation status](IMPLEMENTATION_STATUS.md) is the authoritative record of shipped behavior.

## Milestone order

| Order | Milestone | Completion evidence |
| --- | --- | --- |
| 1 | Complete DXL-native frontend and backend | The compiler builds itself through three stages; stage 2 and stage 3 are byte-identical; all stages pass the same language corpus. |
| 2 | Parser and diagnostic infrastructure | Every token and AST node has an exact source span; recovery reports multiple ordered diagnostics; every distinct failure has a stable identifier and message. |
| 3 | Parametric types | Generic functions, structures, arrays, and slices monomorphize deterministically and pass ownership tests. |
| 4 | Core standard library | Generic strings, optional values, results, lists, deterministic maps/sets, bounded queues/stacks, arenas, and capability-declared I/O have positive and negative coverage. |
| 5 | Package and build system | Strict manifests, canonical locks, vendored dependencies, cycle/conflict rejection, and minimal incremental rebuilds are reproducible. |
| 6 | Additional targets | Each target has independently inspected object metadata, deterministic repeat output, native link/run coverage, and target-aware compile-time tests. |
| 7 | Developer tooling | One shared parser powers an idempotent formatter, incremental language server, and cross-referenced documentation generator. |
| 8 | Debugging | Deterministic line, type, function, and variable information passes structural and source-mapping tests; source-level debugging follows only after that base is complete. |
| 9 | General memory model | Moves, borrows, lifetime relationships, owned aggregate fields, and arena escape rules are checked across parameters, returns, and structures. |
| 10 | Deterministic concurrency | Isolated actors, bounded mailboxes, explicit ownership transfer, and reproducible scheduling are defined in a versioned execution profile. |

The ordering is intentional: compiler self-reproduction comes first; parser infrastructure precedes parametric types; parametric types precede the general library; the package system precedes platform expansion; tooling, debugging, and the general memory model build on those foundations. Concurrency remains a future boundary.

## Near-term compiler work

The tested modules under `compiler/dxl/selfhost/` now provide table-driven lexing, spans, multiple-diagnostic recovery, canonical AST/type/TIR arenas, an integrated precedence parser and semantic foundation, deterministic typed-IR records, byte writing, object-layout fixtures, and minimal line data. The separate native-core compiler already emits source-dependent static executables for its bounded scalar profile.

The next complete-compiler increments are:

1. load and merge the complete import graph with cycle-aware symbol resolution;
2. model builtin signatures, effects, file operations, named structures, fields, and aggregate schemas;
3. extend ownership, managed storage, result values, parameters, function calls, and bounded compile-time evaluation;
4. lower complete function bodies and control flow into one executable canonical IR;
5. extend the source-dependent backend from the native scalar core to every construct used by the compiler closure;
6. create one canonical full compiler source closure and execute the three-stage identity gate in [DXL-native compiler status](SELF_HOSTING.md).

No intermediate foundation is labeled self-hosting before the last gate succeeds.

## Cross-cutting requirements

Every milestone must add:

- positive behavior tests;
- negative tests asserting exact diagnostic identifiers and messages;
- repeated-artifact byte-identity tests;
- regressions for every previously supported feature;
- bounded execution and explicit resource limits where applicable;
- updates to the language references, implementation status, diagnostic catalog, and changelog.

The release continues to fail closed: unsupported targets, malformed artifacts, missing capabilities, exhausted limits, unresolved dependencies, and invalid ownership states must be rejected rather than guessed or silently accepted.
