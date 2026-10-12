# Pocket Rocket status

## Durable milestones

1. **Target lock — complete:** DeepSeek V4 Flash, 256 routed/top-6/43 layers,
   exact GGUF identity, pinned DwarfStar revision, no alternate model path.
2. **Recovered architecture — complete:** Lumus ARH routes, Lbit
   coupling/collapse, Dexr Aegis T39/DXT4 facts, and NeuroBSD-T3 RV64 evidence
   are recorded in `docs/ARCHITECTURE.md` and
   `docs/RECOVERED_TERNARY_INTEGRATION.md`.
3. **Low-C conformance — complete:** native ternary/T39 tri-state bridge and
   x87 candidate pass exact vectors, corruption gates, ASan, and UBSan. x87 was
   accepted on the packaging x86-64 host; other hosts rerun the gate.
4. **Unified runtime — pending target execution:** CLI chat and `/ask` share the
   guarded pinned ds4 transport; the remaining step is the real-token
   14.5 GiB RSS gate on the target machine.
5. **0.3 source release — complete locally:** the source-only ZIP rebuilds
   byte-identically, its internal SHA-256 manifest and compressed data pass,
   and a fresh extraction passes the complete locally runnable gate set.
6. **CPU-only v1 control plane — complete:** the declarative v1 spec was
   safety-reviewed and normalized in `docs/CPU_ONLY_V1_SPEC_REVIEW.md`.
   Read-only host qualification and CPU-only ds4 selection are implemented.
   Public arithmetic modes fail closed to `integer_oracle` until an x87 or
   AVX2 conformance digest matches.
7. **Desktop and certificate boundaries — partially complete:** a real GTK4 C
   client and the per-token GGUF certificate design are present. The image
   runtime is a reviewed candidate only. Native ds4 page/logit instrumentation,
   full-model execution, and image generation remain measured milestones. See
   `docs/V1_ACCEPTANCE_MATRIX.md`.
8. **Exact ternary decision plane — complete:** direct sign-plane dot products,
   exact triadic/rational arithmetic, reject/abstain/accept gates, typed Choice,
   local route decisions, and deterministic evidence certificates are wired to
   the CLI and covered by adversarial tests.
9. **Static/demand model pages — complete for authenticated local sources:**
   a canonical manifest, domain-separated Merkle root, bounded cache format,
   atomic writes, and range reads use the same identity in both modes. The
   former 64 GiB ceiling that rejected the pinned model is now 128 GiB.
10. **Adaptive authenticated page compression — complete:** every page measures
    raw, DEFLATE, and 2/4/8-byte shuffle+DEFLATE, then stores the exact smallest
    candidate with a deterministic tie rule. Legacy v1 pages remain readable.
11. **Ordered exact Score — complete:** ordered triadic support is normalized to
    exact rational probabilities and expected score; ties and inadequate
    confidence produce semantic abstention, not a binary translation.
12. **Recursive proof fabric — complete in source:** 1,024 deterministic
    capability cells route bounded quorums; only the pinned DS4 transport can
    execute them. Exact response agreement controls reject/abstain/accept,
    abstention alone triggers another bounded round, and every run commits a
    verifiable transcript. Full-model agent execution remains target-dependent.
13. **Production-surface audit — complete:** release tests reject simulated
    production dependencies and incomplete paths, and require every public 0.3
    callable to be connected to an export, CLI surface, or direct test.

## Implemented and locally testable

- Immutable DeepSeek V4 Flash identity: 256 routed experts, top-6, 43 layers.
- Exact GGUF size/SHA verification and official resumable download.
- Pinned DwarfStar source installer, upstream tests, and CLI-contract check.
- Process-tree 16 GiB gate with 1 GiB expert cache, a 512/16 smoke profile and an
  ordered ladder ending at the 8192-context/2048-output product profile,
  14.5 GiB process-tree RSS ceiling, and per-frontier JSON evidence.
- Deterministic Lbit commitments, coupling closure, recursive expansion,
  authenticated omission certificates, and fail-closed fallback.
- Pre-React Lumus `/ask` and `/reset` boundary with bounded ephemeral history.
- One guarded `DS4LocalTransport` powers both CLI chat and `/ask`; no second
  model backend is packaged.
- Reference binary32 conformance for NaNs, signed zero, overflow, subnormals,
  ties-even, fixed reductions, RMSNorm, SiLU, softmax, and attention.
- Native C binary32/envelope/Flat32/NPRQ/Pocket Rocket tests.
- Exact ternary Python and C kernels, typed Gate/Choice/Score decisions, and
  static/demand page storage with corruption, source-mutation, alias, symlink,
  pre-allocation bound, and codec regressions.
- `model-analyze` authenticates a complete supplied model and reports codec
  counts, complete framed bytes, a reduced exact ratio, and decision root.

## Hardware-dependent and not yet claimed here

- The 86.72 GB weight download was not performed in the packaging container.
- DwarfStar inference against the full model was not run here.
- Therefore the target-PC 16 GiB PASS, latency, SSD traffic, and output quality
  remain unmeasured until `scripts/run_16gb_gate.py` succeeds there.
- Synthetic NPRQ and Flat32/Pocket Pack fixtures are implementation proofs only;
  they do not establish compression or quality for the pinned GGUF.
- Synthetic shuffle/DEFLATE fixtures likewise do not establish the pinned
  GGUF's codec distribution or compression ratio.

## Historical local qualification (2026-10-01)

- Python: 150/150 PASS; GTK source-contract tests: 6/6 PASS.
- Native: NPRQ/ternary, envelope, Pocket Pack, Flat32/dictionary, binary32/x87,
  and T39 Lbit PASS under strict GCC.
- ASan and UBSan: PASS for every native target.
- x87: accepted on the qualification x86-64 host after canonical edge-vector
  agreement.
- T39: 10,000 deterministic round trips; reject/recurse/allow gates PASS.
- Golden-Hamming benchmark: 10,000 experts × 100 queries, repository-run
  median 12.163 ms and p95 28.023 ms in this container.
- Recursive-fabric routing benchmark: 1,024 cells × 1,000 queries with a
  three-cell quorum, median 1,711,047 ns and p95 1,995,760 ns in this
  container; checksum 2,863,516. This excludes model inference.
- Exact 256-trit benchmark: 10,000 vector pairs × 7 repeats, scalar median
  95,257,258 ns, sign-plane median 3,130,385 ns, measured 30.429× speedup with
  identical checksum 574. This is the Python kernel comparison on this host,
  not a full-model throughput claim.
- Archive: source-only audit, two byte-identical builds, ZIP CRC, internal
  manifest, and fresh-extraction `test proof native-test benchmark
  page-codec-benchmark archive-check` all PASS.
- Page-codec benchmark: lossless PASS on three deterministic 2 MiB fixtures;
  stored bytes including framing were 8,103 (structured32), 3,158 (pattern),
  and 2,097,208 (entropy). These are fixture observations only.
- Host preflight: Linux x86-64-v3, AVX2/FMA present, CPU-only, no privileged
  tuning; default arithmetic mode remains `integer_oracle`.
- GTK4 compilation: not run because this container lacks `pkg-config`/GTK4
  development headers; no binary is claimed.
- Full GGUF/ds4/14.5 GiB: not run. The exact 86.72 GB weights cannot fit in
  the 29 GiB currently free in this container.
- Context-profile correction: complete in source. The earlier 512/128 product
  cap and zero-byte KV estimate were defects. Product defaults are now
  8192/2048; pinned ds4 compressed-KV/context accounting is 124,202,514 bytes
  at 8K. Hardware ladder execution remains pending with the full GGUF.

## 0.4.2 additions (2026-10-12)

- Lumus ARH is the sole service/component name (`lumus_arh.py`,
  `LumusARHService`, `LumusARHWSGI`). The HTTP protocol remains `/ask`, `/reset`.
- Full, separately versioned Aegis Language Suite 2.4.3 ships with local
  checksummed compiler/VM binaries, real execution from the Pocket Rocket CLI,
  implementation sources, specifications and negative tests.
- Aegis-C2R 0.1.0 is separately packaged with its original isolated 2.4.0
  bootstrap for independent reproducibility, not merged into Aegis 2.4.3.
- Tests and outstanding environment-pinned byte-reproducibility gate are in
  `docs/RELEASE_TEST_REPORT.md`. No full GGUF or 16 GiB target execution claim.
