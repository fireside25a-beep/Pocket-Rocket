# Recovered accelerator facts and evidence boundary

This file records recovered notes that may guide future work. They are not
implemented backends, benchmark results, or proof that a compatible hardware or
software toolchain exists in this repository.

## DPU and Rendr notes

The retained `Dexr-2.6.0-Renderer-DPU-Driver-AIO.zip` was inspected directly;
its SHA-256 is
`c424e22966250aa75e8c02cee0cbccb12ab416d1565cf8a54d2ff58ee48bb8d9`,
matching its retained checksum file. No source from that archive is copied into
Pocket Rocket.

- DPU render reuse used exact render-signature equality. It did not use
  Hamming distance as a render-cache equivalence test.
- T3DPU and T3V are virtual deterministic accelerator concepts. The word
  “deterministic” describes their specified execution model; it is not a
  measurement of latency, throughput, numerical identity, or hardware
  availability.
- DXT4 T39 uses checked int64 host execution. This is an execution-safety
  boundary, not a recovered floating-point format or a claim about GPU/DPU
  arithmetic.
- That archive contains a compact C ABI, pthread CPU dispatch, Vulkan/D3D12
  adapters, and a software triangle path. Its rasterizer uses ordinary C
  `float` arithmetic; temporal reuse is triggered by equality of a caller
  supplied 64-bit dependency signature. It does not provide a software-float
  format or a cross-hardware neural arithmetic kernel.
- The thesis's floating-point-control discussion explicitly says strict
  compilation can reduce reordering but does not automatically guarantee
  identical results across processors and compilers; it calls for conformance
  vectors around ties, NaNs, signed zero, overflow, and subnormals.
- Therefore the project does not integrate the image/rendering code or claim a
  deterministic floating-point backend. Only its verified architectural rule
  is reused: heuristic/cache acceleration must be followed by exact acceptance
  before output identity is claimed.

These notes must remain separate from the measured Python NPRQ evidence. In
particular, Golden-Hamming is a verified routing-index optimization in this
repository; it must not be described as the DPU render-reuse rule.

## What is actually measured here

The seeded NPRQ proof uses four independently stored residual stages:

```text
W_hat_m = sum(i=0..m) s_i q_i,
q_i in {-3,-1,+1,+3}
```

With the stored-scale SSE gate, the measured relative weight errors are:

| stages | bytes | relative error |
| ---: | ---: | ---: |
| 1 | 4,224 | 0.3417472541 |
| 2 | 8,448 | 0.1385093033 |
| 3 | 12,672 | 0.0867866725 |
| 4 | 16,896 | 0.0628760308 |

The synthetic all-expert dense reconstruction error is
`3.826764896075474e-7`. Hamming-only sparse output relative errors at
1/2/4/8/16 experts are `0.9611841440`, `0.9270318747`, `0.8842302561`,
`0.7401971817`, and `3.8267648961e-7`. These values demonstrate monotonic
NPRQ reconstruction and the failure of zero-shot Hamming order as an accuracy
certificate; they do not establish full-model task quality.

## Integration rules

1. Keep DPU render reuse keyed by exact signatures unless a separate measured
   equivalence proof is added. The Python binary32 reference is a conformance
   oracle only; it does not make DPU/GPU/Rendr execution equivalent.
2. Treat T3DPU/T3V as virtual specifications until a real implementation and
   benchmark are supplied.
3. Keep DXT4 T39 integer execution checked and host-side unless the missing
   numeric specification is recovered and tested.
4. Do not relabel ordinary C `float` execution as cross-platform bit identity.
   The written Python binary32 mode and differential vectors in
   `docs/BINARY32_NUMERIC_CONTRACT.md` are the current reference gate; a native
   or accelerator backend must pass them before use.
