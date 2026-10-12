# Pocket Rocket 0.3 security and architecture audit

Date: 2026-10-01

## Scope and result

The 0.3 source tree was reviewed from CLI entry points through the capability
fabric, exact decision layer, page store, and pinned DS4 boundary. The release
contains no `src/qf_cli.c`, training command, or C path-list accumulator, so a
reported signed/unsigned write in a different CLI is not reachable or packaged
here. Existing model-page length, offset, allocation, alias, symlink, hash, and
decompression-expansion checks remain covered by Python and strict-C tests.

No critical release-blocking defect remains in the locally executable scope.
The full GGUF runtime gate is still unrun and is not converted into a pass.

## 0.3 findings and controls

| Risk | Control | Verification |
| --- | --- | --- |
| “1,024 agents” causing unbounded work | Cells are immutable routing identities; activated nodes are limited to 2–64 | exhaustive fabric identity test; budget tests |
| Alternate or simulated model backend | Runtime constructor accepts only `DS4LocalTransport` | direct rejection test; source-surface audit |
| Binary collapse of uncertainty | direct `Trit` reject/abstain/accept; only abstain recurses | all three states exercised |
| Floating threshold drift | reduced `ExactRational` comparisons only | boundary/ordering tests |
| Recursion or token explosion | depth ≤6, quorum 2–5, nodes ≤64, output ≤2,048, prior-round output budget ≤4,096 tokens | constructor rejects every out-of-contract setting tested |
| Model-output tool injection | model output is data; no shell, filesystem, network, package, or mutation tool is exposed | architectural inspection; transport lock |
| Evidence prompt injection | prior output is delimited and explicitly labeled untrusted | prompt construction test path and source review |
| Silent routing drift | committed fabric root covers IDs, labels, facets, and all 1,024-bit codes | construction-time root check |
| Transcript or answer tampering | canonical-JSON run certificate plus answer hash | positive and tamper-negative tests |
| Dead or simulated new surface | AST release audit rejects mock/fake/stub production imports, incomplete raises, and unconsumed public 0.3 APIs | `make surface-audit` |

## Residual risks

- Hypervector response agreement is not semantic truth. Correlated model errors
  can agree; unrelated wording can disagree. Status is evaluator evidence only.
- SHA-256/SHAKE-256 commitments provide tamper evidence, not formal proof of
  model correctness or resistance to a compromised host.
- A model can still produce harmful or false prose. The fabric exposes no tools,
  but downstream consumers must continue treating returned text as untrusted.
- Full-model latency, answer quality, peak RSS, SSD traffic, and 8K/2K context
  behavior require the pinned target machine and 86.72 GB GGUF.
- The source audit establishes configured structural properties. It is not a
  substitute for an independent penetration test or formal verification.

## Local gates

The release gate includes 150 Python tests, six GTK source-contract tests,
strict GCC builds, ASan, UBSan, exact synthetic proofs, routing/page benchmarks,
archive scanning, deterministic archive reproduction, CRC and internal-manifest
checks, and a clean-extraction rerun. Hardware-dependent DS4 gates remain
explicitly pending.
