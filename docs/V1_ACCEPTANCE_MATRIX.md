# Pocket Rocket v1 acceptance matrix

This is the durable, fail-closed qualification ledger for the declarative CPU
v1 request. `PASS` means the named command executed against the named artifact.
`PENDING` is not a softened pass.

| Gate | Status | Evidence / remaining work |
| --- | --- | --- |
| Exact target identity | PASS | DeepSeek V4 Flash GGUF repository, revision, filename, byte size, SHA-256, 256 routed experts, top-6 and 43 layers are immutable in `model_target.py`. |
| User-space CPU lockdown | PASS | Read-only preflight reports Linux x86-64-v3, AVX2/FMA present, GPU disabled, no privileged tuning; ISA detection leaves arithmetic in `integer_oracle`. |
| Public arithmetic mode vocabulary | PASS | Only `integer_oracle`, `x87_verified`, and `avx2_verified` are admitted. Verified candidates require identical conformance digests. |
| Exact binary32 edge corpus | PASS | NaN, signed zero, overflow, subnormal, and ties-to-even vectors pass Python and native C. The local x87 candidate was admitted by bitwise comparison. |
| Deterministic neural primitives | PASS (reference) | Fixed-order dot, RMSNorm, SiLU, softmax, and attention reference tests pass. This does not yet certify ds4's complete transformer hot path. |
| T39 decoder and Lbit control | PASS | Exact 39-trit/eight-octet range, 10,000 round trips, checked arithmetic, symbol `3`/padding/truncation rejection, and reject/recurse/allow gates pass. |
| Sparse routing safety | PASS (control) | Hamming orders candidates. Authenticated omission bounds control stopping; missing evidence expands to all experts or aborts. Synthetic sparse quality is explicitly not accepted as evidence. |
| Python regression | PASS | `make test`: 133 project tests plus 6 GTK source-contract tests pass at this checkpoint. |
| Native sanitizers | PASS | Strict GCC, ASan, and UBSan pass for NPRQ, envelope, Pocket Pack, Flat32, binary32/x87, and T39/Lbit targets. |
| Source-only archive audit | PASS | Credential/model-artifact audit and deterministic release construction pass; weights and runtime binaries are excluded. |
| GTK4 compilation | PENDING (host dependency) | Real GTK4 C source is present. This container lacks `pkg-config`/GTK4 development headers, so no GTK executable is claimed here. |
| Per-token ds4 page/logit certificate | PENDING | Requires instrumentation inside the pinned ds4 GGUF parser, tensor reads, dequantizer, router, reductions, and token emission. Whole-file identity is not substituted for page ancestry. |
| Single native supervisor/HTTP executable | PENDING | The current recovered `/ask` and `/reset` service is Python WSGI. It is functional but is not the requested final native supervisor binary. |
| Full model download | PENDING | The 86,720,111,488-byte GGUF cannot fit in this container's currently available 52 GiB. No partial or substituted model is accepted. |
| 14.5 GiB real-token gate | PENDING | Cannot run until the exact GGUF and pinned ds4 are installed. The existing gate measures the complete process-tree RSS and fails closed. |
| 8K/2K product context gate | PENDING (target hardware) | The code now separates 512/16 smoke from the 512/16→2048/128→4096/512→8192/2048 qualification ladder. Exact ds4 CPU compressed-KV accounting is 124,202,514 bytes at 8K; real generation/RSS remains required. |
| Local image generation | PENDING | A pinned permissive CPU-runtime candidate and certificate boundary are documented. No image weights, worker binary, generated image, or 14.5 GiB measurement exists yet. |

## Current boundary

The source package is a tested engineering handoff, not a production-ready
claim for the full 86.72 GiB model. The next target-host sequence is exact
weight verification, pinned ds4 build, ds4 instrumentation, real-token memory
qualification, then GTK/image qualification. Any failure remains visible in
this table and must not be converted into documentation-only success.
