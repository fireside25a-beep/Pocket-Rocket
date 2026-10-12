# Pocket Rocket v1.0 CPU-only specification review

This checkpoint translates the declarative request into one implementable,
user-space architecture. No privileged command is part of the build or runtime.

## Accepted invariants

- Linux x86-64 CPU only. Baseline x86-64-v1; accelerated admission requires
  the complete x86-64-v3 feature set including AVX2 and FMA.
- One local GGUF model identity and one native inference engine. No hosted
  service, GPU backend, tensor framework, or alternate model responder.
- Exact ternary control values: `REJECT=-1`, `RECURSE=0`, `ALLOW=+1`.
- Strict rejection of symbol `3`, noncanonical padding, truncation, arithmetic
  overflow, malformed ranges, and certificate-chain mismatch.
- x87 binary32 boundaries are the reference arithmetic mode. AVX2 acceleration
  is admitted only by a deterministic conformance certificate.
- `/ask` and `/reset` bind to loopback on an unprivileged port. Request history
  is RAM-only and scoped to the request.
- Full model path comes from one plain configuration/environment value.
- Release and qualification run without root, `sudo`, package installation,
  global sysctls, mounts, or automatic cron modification.

## Required corrections

| Requested mechanism | Problem | Implementable rule |
|---|---|---|
| `RLIMIT_AS = 14.5 GiB` | An engine that maps the 86.72 GiB file can receive `ENOMEM` even when RSS is small. | Apply the address-space limit only after the GGUF reader proves bounded window mapping. Until then, enforce 14.5 GiB with the guarded allocator plus process-tree RSS sampling and record the reason the AS limit was not armed. |
| Lock all future pages | `MCL_FUTURE` can turn ordinary future allocation into failure under the user's lock limit. | Never lock all future mappings. Attempt `mlock2(MLOCK_ONFAULT)` or `mlock` only on the bounded hot ring; failure is recorded and paging continues. |
| 1 GiB huge pages | Explicit HugeTLB mappings usually require pre-reserved pages and suitable backing/alignment. | Use ordinary aligned memory first; apply `MADV_HUGEPAGE` to anonymous hot buffers when available; retain a 4 KiB fallback. |
| Non-deterministic 5% sampling | Different samples break replay and certificate identity. | Select the sample with a domain-separated hash of model hash, request hash, layer, forward index, and fixed qualification seed. Same input selects the same coordinates. |
| FMA within a separate mul/add oracle | FMA rounds once; separate multiply and add round twice, so bit identity is not general. | Define separate oracle operations. AVX2 may vectorize add/mul; FMA is used only for an explicitly fused oracle or when interval proof shows the final significant-logit ordering cannot change. |
| Accept one ULP everywhere | A one-ULP change can reverse close logits and change a token. | Significant logits and routing comparisons require exact bits. Other sampled intermediates may use a one-ULP bound only when a certified interval proves the selected token and route remain invariant. |
| Six experts in one 950 MiB ring | Top-6 applies per MoE layer, not necessarily six total expert pages for all 43 layers. | Parse and certify real GGUF tensor offsets/sizes first. Admit a page window only when measured resident bytes fit; otherwise evict or reject before mapping. |
| Same-sign per-expert logits | MoE experts normally produce hidden contributions, not six independent vocabulary-logit vectors. | Certify the six routed contribution tensors and the final significant logits. A coupling gate operates on committed contribution bounds, not an invented per-expert vocabulary sign. |
| Expand KV cache without a token | KV positions represent sequence positions; adding one without emission corrupts attention semantics. | Recursion reuses a scratch residual/checkpoint at the same sequence position. KV state is committed only after `ALLOW` emits a token. |
| Integer lookup replaces a floating proposal | A finite table cannot reproduce arbitrary model logits. | Integer mode performs exact control/ranking/bounds or rejects the candidate. It never fabricates a neural token. |
| `POST /reset` always launches another binary | This conflicts with a single-process interpretation. | One executable uses a small supervisor mode that owns a replaceable inference child of the same pinned executable. Reset kills, waits, clears ephemeral state, and respawns that exact image. |
| Zero remote NUMA accesses | Affinity/mempolicy do not themselves prove zero hardware events, and counters may be unavailable. | Pin only inside the process's allowed CPU set. Record policy and observable placement; mark the counter gate skipped unless unprivileged counters are available. |
| Single portable binary plus GTK | A GTK desktop requires GTK runtime libraries and conflicts with a dependency-free headless executable. | Keep one dependency-light runtime binary. Build a real GTK4 local client as a second optional artifact communicating only over loopback. Both ship in one folder; the model executes only in the runtime binary. |

## Certificate chain v1 boundary

Each emitted token certificate must bind:

```text
model identity + GGUF SHA-256
runtime source revision + executable SHA-256
host-preflight certificate
request/history canonical hash
token position + token ID + prior-token certificate
significant-logit bits and arithmetic mode
deterministic verification-sample coordinates/results
exact GGUF tensor byte ranges touched by the certified forward pass
T39 reject/recurse/allow token
```

The page-range list must come from the instrumented GGUF loader, not from an
estimate. Ranges are page-aligned, length-bounded, inside the verified file,
and folded into a domain-separated Merkle root. A certificate is unavailable
until the native engine exposes those actual range events; the API must not
substitute the whole-file hash and call it a page trace.

## Qualification phases

1. CPU host certificate and no-GPU build lock.
2. x87/AVX2 operation contract, deterministic sampling, exact-significant-logit
   gate, and native sanitizer suite.
3. Windowed GGUF tensor inventory with byte-range/Merkle trace.
4. Single native supervisor/worker runtime with bounded allocator and HTTP.
5. Ordered memory ladder: 512/16 smoke, 2048/128, 4096/512, then the
   8192-context/2048-output product workload. Each frontier must pass before
   the next begins.
6. GTK4 local Git workspace, connected to the already-qualified loopback API.

No later phase may be marked complete using synthetic pages or fixture output
from an earlier phase.
