# Pocket Rocket unified architecture

## One execution path

The production token path is the pinned DeepSeek V4 Flash GGUF executed by the
pinned low-C DwarfStar engine. The model has 256 routed experts, selects six per
token, and contains 43 layers. Full compressed weights stay on SSD; non-routed
weights, KV state, and a bounded 1 GiB routed-expert cache form the RAM working
set. Python does not evaluate the production transformer. It performs source
verification, build orchestration, exact reference math, evidence capture, and
the loopback Lumus boundary.

## Lbit route, coupling, and collapse

Each query and expert page has an exact 256-bit coordinate. Ranking is the
stable pair `(popcount(query XOR expert), expert_id)`. Golden-Hamming indexing
uses `K=0x9E3779B97F4A7C15`, but every candidate is checked against the complete
coordinate and final ordering remains equal to linear Hamming ordering.

An Lbit coupling edge is a SHA-256-committed all-or-nothing page dependency.
Selecting one endpoint closes the complete connected component. Collapse is a
monotonic recursive schedule:

```text
A_0 subset A_1 subset ... subset A_n
w_e = 1 / (1 + d_H(query,e))^p
tail(A_i) = sum(e not in A_i, w_e) / sum(e, w_e)
```

The scheduler can stop only when the exact tail condition and an authenticated
omission-bound certificate both pass. Missing, altered, or incomplete evidence
expands recursively. If the all-expert safe state exceeds the RAM admission
budget, execution aborts instead of silently truncating.

## Balanced-ternary control bridge

Recovered Dexr Aegis 2.4 defines `T39`: 39 balanced trits in
`{-1,0,+1}`, exact range
`-2,026,277,576,509,488,133 .. +2,026,277,576,509,488,133`, canonically
packed into eight octets. It provides checked add/subtract/multiply/negate and
comparison. Pocket Rocket uses this for bounded control evidence and collapse
decisions, not as a duplicate tensor engine:

```text
-1 = reject / expand
 0 = unresolved / recurse
+1 = accept / collapse
```

Non-canonical encodings, invalid trits, overflow, mismatched proof bytes, and
tampering fail closed. The recovered NeuroBSD-T3 RV64 work supplies independent
T3V differential vectors and the Aegis DXB3/DXP3/DXP4 proof conventions; it is
a conformance source, not another inference process.

## NPRQ validation path

NPRQ is an experimental page format used for controlled conversion research.
Legacy v1 ternary pages use `{-1,0,+1}` and reserve two-bit symbol `3` as an
error. V2 signed-quaternary pages use `{-3,-1,+1,+3}`. Metadata chooses the
format; the decoder never guesses.

```text
W_hat_m = sum(i=0..m, stored_f16_scale_i * q_i)
SSE(W, W_hat_m) <= SSE(W, W_hat_(m-1))
```

Every page is length-bounded and SHA-256 authenticated. Conversion commits a
stage only after the stored float16 scale reduces SSE. Decode rejects reserved
symbols, non-canonical padding, non-finite scales, truncation, trailing bytes,
hash mismatch, unsafe paths, and non-monotonic metadata.

## Numeric backend admission

The canonical oracle is exact binary32 with canonical NaNs, signed zero,
gradual subnormals, ties-to-even, overflow, and fixed reduction order. RMSNorm,
SiLU, softmax, attention, and dot products build on that oracle. SIMD, GPU,
x87, RISC-V, or handwritten assembly are candidates only: each candidate must
match the conformance vectors bit-for-bit, including NaNs, signed zero,
overflow, subnormals, and ties. A mismatch returns the oracle result and counts
the fallback.

x87's 80-bit intermediates are useful only when explicit stores/rounding make
the selected binary32 boundary identical. They do not change the weight format;
their acceptance is based on measured vector equivalence and speed.

## Lumus ARH ephemeral worker boundary

The restored pre-React interface is `POST /ask` and `POST /reset`. `/ask`
normalizes a bounded request, computes a deterministic envelope identity, calls
one local model transport, and records bounded ephemeral history. Worker errors
or disabled state select `full_pipeline`. Promotion suggestions remain
ephemeral; there is no permanent-memory mutation path. `/reset` clears both the
history and deterministic envelope state.

## Memory and acceptance

- SSD: exact 86,720,111,488-byte pinned GGUF and runtime caches.
- RAM: approximately 8.20 GiB non-routed runtime observation, 1 GiB expert
  cache, KV/context state, executable and scratch memory.
- Admission: 512/16 first smoke, then 2048/128, 4096/512, and the
  8192-context/2048-output product frontier; temperature zero,
  streaming-layer safety switch, and 14.5 GiB measured process-tree RSS cap.

The release earns its 16 GiB status only when real local generation writes a
PASS report containing the pinned model hash, runtime commit, command/output
hashes, exit code, elapsed time, and observed peak RSS.
