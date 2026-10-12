# 0.4 framing: deterministic substrate, measured mechanisms

The claim is not “sparsity makes x86 faster” and it is not “software TCAM is O(1).” The implementation separates representational properties from hardware/runtime properties.

- Dense ternary dot remains the normal path. `nr_ternary_dot_sparse` is an explicit event-driven reference for targets where a caller has measured a benefit. It is never auto-selected.
- `nr_tcam_lookup` performs constant work per fixed-width entry and a bounded O(n) table scan. Hardware TCAM is the parallel analogue; this C implementation does not claim hardware-TCAM complexity.
- `nr_ternary_ssm_step` has O(hidden_dim) resident state independent of sequence length. It is a diagonal exact recurrence, not a Mamba implementation and not a 1B-model claim.
- `nr_hamming_route` is an exact native scan. Its benchmark isolates native Hamming cost from Python sorting/GC/orchestration effects; it does not compare itself to approximate ANN systems as if the algorithms had the same semantics.
- Exact arithmetic removes numerical nondeterminism from these specific decision/reference paths. It does not prove semantic correctness or model quality.

The architectural thesis is narrower and testable: exact ternary arithmetic in the decision plane, an integer-oracle/explicitly-rounded binary32 numeric boundary, fail-closed governance in the control plane, and hash-committed state in the audit plane. The model is a proposal source, never an authorization source.
