# Pocket Recursive Proof Fabric 0.3

## Contract

The fabric contains exactly 1,024 deterministic routing cells:

```text
8 roles × 16 domains × 8 facets = 1,024 cells
```

A cell is a capability identity and 1,024-bit hypervector. It is not a process,
thread, model instance, or claim of independent intelligence. A run activates
only its configured quorum through `DS4LocalTransport`, the same pinned local
model boundary used by chat and `/ask`.

## Exact routing

Input is lowercased and tokenized to ASCII alphanumerics. Each token-position
bucket maps to 128 bytes using SHAKE-256. Per-bit signed integer votes are
bundled by majority; deterministic whole-text bits break exact ties. Routing
uses:

```text
d(a,b) = popcount(a XOR b), |a| = |b| = 1,024 bits
```

Candidates are ordered by `(distance, cell_id)`. There is no floating-point
calculation, learned router, approximate nearest-neighbor result, or binary
translation of a ternary state.

## Recursive state machine

Each round selects a 2–5-cell quorum for one role. The model receives the goal,
cell identity, role/domain/facet, and only the immediately preceding evidence.
All pairwise response hypervector distances are measured. Similarity is the
reduced exact rational `(1024 - distance) / 1024`.

- `reject (-1)`: minimum similarity is below `4/9`; stop.
- `abstain (0)`: neither rejection nor acceptance holds; recurse if budget
  remains, otherwise return the bounded abstention.
- `accept (+1)`: every pair similarity is at least `5/9`; stop.

The returned candidate is the Hamming medoid with stable index ties. Agreement
does not prove factual correctness: shared model errors can agree, and lexical
hypervector distance is only a reproducible proxy. The status describes this
evaluator's evidence, not truth.

## Limits and security

`FabricLimits` enforces depth `0..6`, total activated nodes `2..64`, quorum
`2..5`, and output tokens `1..2048`. The plan is computed before execution and
cannot exceed the total-node limit. Model output is data only: it receives no
shell, filesystem, network, package, or self-modification capability.

The executor constructor requires an actual `DS4LocalTransport` instance.
This prevents a plugin, hosted endpoint, or silent second responder from
entering the production path. Tests exercise routing, limits, all ternary
states, certificates, and the CLI planner without simulating a model response.
The full execution command consequently requires the real pinned runtime and
weights and is not claimed as run in a source-only packaging environment.

## Evidence

The plan certificate commits the domain, fabric root, request root, limits,
round roles, cells, and route distances. A run transcript additionally commits
every response hash, pair distance, state, and answer hash. The run certificate
is SHA-256 over canonical JSON. `verify_run_certificate` checks the domain,
fabric identity, answer hash, and transcript commitment without rerunning the
model.

This is a tamper-evident execution record, not a formal proof of answer truth.

## Scientific evaluation required

A defensible quality claim requires paired tests against the same pinned model
in single-agent mode, fixed prompts and token budgets, task-specific external
scorers, repeated trials, latency/RSS/SSD accounting, and reporting of rejects
and abstentions rather than dropping them. Until that target experiment is
run, 0.3 claims architecture, determinism, limits, and local test results only.
