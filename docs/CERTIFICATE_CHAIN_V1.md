# Pocket Rocket certificate chain v1

This document defines the certificate that the CPU-only Pocket Rocket path must
emit for every generated token. It is an audit contract, not a claim that a
quantized model is mathematically exact or that a sampled kernel has been
proved for all possible inputs. A verifier must be able to reject a token when
any declared dependency is absent, altered, or outside the declared arithmetic
conformance scope.

## 1. Certificate meanings

The external certificate uses exactly these arithmetic mode names:

| Mode | Meaning | When it is legal |
| --- | --- | --- |
| `integer_oracle` | The checked software binary32 reference path produced the decision-critical values. | Always available on a valid CPU build. It is the fail-closed mode. |
| `x87_verified` | An x87 candidate produced the same bit patterns as the reference for the declared operation set and conformance vectors. | Only after the x87 gate passes and every decision-critical result is bit-identical. |
| `avx2_verified` | The AVX2 workhorse (with or without FMA as explicitly recorded) produced the same bit patterns as the reference for the declared operation set and verification scope. | Only after the candidate gate passes; a one-ULP result is not a pass. |

`x87_verified` does not mean that extended-precision x87 values are themselves
the oracle. x87 has 80-bit intermediates and can retain excess precision. The
reference is the existing checked binary32 implementation. An x87 operation
must store/round at the specified binary32 boundaries before comparison. If a
caller wants x87 to be the reference, it must define and ship a separately
verified correctly-rounded binary32 x87 contract; changing the label alone is
not evidence.

The source and public certificate boundary use these names directly; aliases
are not admitted because they would make verification policy ambiguous.

## 2. Immutable model and byte coordinate system

The certificate is anchored to the exact model identity in
`src/neuro_inverse/model_target.py`:

* model: DeepSeek V4 Flash;
* GGUF file size: 86,720,111,488 bytes;
* complete file SHA-256: `efc7ed607ff27076e3e501fc3fefefa33c0ed8cf1eff483a2b7fdc0c2e616668`.

All offsets are unsigned byte offsets from byte zero of that GGUF file. A
range is half-open: `[offset, offset + length)`. It is invalid for a range to
overflow 64-bit arithmetic, extend past the verified file size, or have a
different digest from the bytes actually read.

The runtime creates two authenticated manifests before the first token:

1. **GGUF tensor manifest.** For every tensor, record its canonical name,
   dimensions, GGML type, element count, data offset, data byte length, and
   the hash of the canonical metadata record. The parser must use the GGUF
   `data_offset` plus the file's alignment rule; it must never infer offsets
   from expert numbers or compressed sizes.
2. **File-page manifest.** Partition the complete file into fixed 4096-byte
   leaves, including one shorter final leaf when necessary. For page `p`,
   where `offset = p * 4096`, compute:

   ```text
   page_leaf = SHA256("PocketRocket/GGUF/page/v1\0"
                      || u64_be(offset) || u32_be(length) || raw_bytes)
   ```

   The ordered page leaves are the leaves of a binary Merkle tree. Duplicate
   the final node at an odd level. The root is `file_page_root`. The file SHA,
   tensor-manifest hash, page size, and Merkle algorithm/version are included
   in the root envelope. A read of a tensor subrange cites every intersecting
   page and also records the exact subrange; page alignment is not allowed to
   hide bytes outside the tensor range.

For a quantized tensor, the source range includes the quantization block bytes
(scales, codebooks, and packed codes) that were consumed. Dequantization does
not create a new unanchored source. An operation that cannot report its exact
source ranges must not receive an accelerated certificate; the result must be
recomputed in `integer_oracle` mode or the request must fail closed.

## 3. Dependency leaves and Merkle chain

Every significant arithmetic result is represented by a dependency leaf. A
leaf is canonical JSON encoded with UTF-8, sorted keys, no insignificant
whitespace, no JSON floating-point values, and lowercase hexadecimal digests.
Binary32 values are always written as eight hexadecimal characters containing
their raw bits. The leaf digest is:

```text
op_leaf = SHA256("PocketRocket/op/v1\0" || canonical_json({
  "token_index": u64,
  "layer": u32,
  "sequence_position": u32,
  "op_ordinal": u64,
  "op_kind": string,
  "arithmetic_mode": string,
  "kernel_id": string,
  "rounding": "RN-even-binary32",
  "input_bit_root": sha256,
  "source_ranges": [
    {"tensor": string, "offset": u64, "length": u64,
     "page_ids": [u64], "range_sha256": sha256}
  ],
  "output_bits": [hex32, ...],
  "verification": {
    "sampled": bool,
    "sample_rule": string,
    "candidate_bits_sha256": sha256,
    "oracle_bits_sha256": sha256,
    "max_ulp": u32,
    "bitwise_equal": bool
  }
}))
```

`input_bit_root` is the ordered Merkle root of the input values and the
preceding operation leaves. `output_bits` is complete for a small operation
(a scalar logit, normalization row, reduction, or attention row). For a large
matmul it is the digest of the complete ordered output vector plus the exact
decision-critical values listed in the token certificate. The verifier can
therefore detect a changed unlisted value without storing a massive JSON
response.

The operation leaves are ordered by `(token_index, layer, sequence_position,
op_ordinal)`. They form `dependency_root` for one token. Token roots form a
chain:

```text
token_root_i = SHA256("PocketRocket/token/v1\0" || canonical_json({
  "previous_token_root": token_root_(i-1),
  "dependency_root": dependency_root_i,
  "emission": emission_record_i,
  "ternary": ternary_record_i,
  "lbit": lbit_record_i
}))
```

The first `previous_token_root` is 64 zero hex characters. A reset starts a new
chain with a new `session_id`; ephemeral history cannot silently continue a
previous chain.

## 4. What counts as a significant logit

The certificate must not use an informal floating-point threshold to decide
which logits matter. For each token, `significant_logits` is the union of:

1. the emitted token's final logit;
2. the deterministic top-32 logits after applying the vocabulary mask, sorted
   by descending binary32 numeric value and then ascending token ID;
3. every token tied at the top-32 boundary by identical binary32 bits; and
4. every candidate whose exact integer token ID can change the selected token
   under the configured tie rule.

For each member, record token ID, final logit bits, probability bits if
computed, its operation-leaf digest, and the source-range set. The complete
vocabulary logit vector is also hashed in token-ID order. If top-32 is changed,
the value is part of the signed configuration and creates a new certificate
version.

For a 256-expert layer, the runtime must record each of the six expert
contributions separately before their fixed-order combination. An expert's
partial contribution is not a complete vocabulary logit. Consequently, the
specification's “all six experts have the same sign” rule is not a valid
general coupling proof: signs can cancel, residual streams can change signs,
and quantized dequantization can move a value across zero. The certificate
records expert IDs, router weights, contribution roots, and the combined-logit
operation. T39 coupling may reject disagreement, but it cannot convert a
partial sign check into a numerical proof.

## 5. Arithmetic verification rules

The reference and candidate must use an explicit operation graph. Fixed
reduction order, binary32 stores, canonical NaNs, signed zero, subnormals,
overflow, and ties are part of that graph. The operation record names the
graph version and kernel ID.

### 5.1 x87

x87 excess precision is a correctness hazard, not a free lossless mode. The
x87 candidate is legal only when:

* the control word is round-to-nearest, exceptions and FTZ/DAZ behavior are
  recorded, and every required intermediate is rounded to binary32;
* the edge/conformance vectors cover NaNs, infinities, signed zero, overflow,
  subnormals, exact halfway ties, reductions, RMSNorm, SiLU, softmax, and
  attention; and
* the candidate and reference bit roots are identical for the complete
  decision-critical scope.

If any condition fails, use `integer_oracle`. The word “oracle” in a build
description must not permit an unrounded 80-bit intermediate to enter the
certificate.

### 5.2 AVX2/FMA

FMA changes the rounding graph: `round(a*b) + c` is not generally the same as
`round(a*b+c)`. Therefore, a workhorse compiled with FMA cannot be certified
against a separate multiply-then-add oracle merely because the result is
within one ULP. There are two legal configurations:

* disable contraction (`-ffp-contract=off`) and compare the AVX2 result to the
  existing binary32 graph; or
* define and verify a correctly-rounded binary32 fused operation in the
  reference graph, then compare the FMA graph to that reference.

The first configuration is the Pocket Rocket default. A one-ULP tolerance may
be reported as a diagnostic, but `max_ulp = 1` never yields
`avx2_verified`. The certificate requires `bitwise_equal = true` and
`max_ulp = 0` for every checked output. If it is not, recompute the affected
scope in `integer_oracle` and record the fallback.

### 5.3 The nominal 5% check

“A random 5% subset” is not reproducible if it uses process-global randomness.
The sample is deterministic and independently reproducible:

```text
sample_digest = SHA256("PocketRocket/sample/v1\0"
                       || session_id || token_index || layer || op_ordinal
                       || candidate_binary_sha256)
sampled = (u16_be(sample_digest[0:2]) % 20) == 0
```

The exact sample rule and candidate binary digest are in the certificate. The
sample covers operation kinds in a balanced way rather than only contiguous
matmul elements. A 5% sample is evidence about the sampled scope, not a proof
of every untested operation. Decision-critical logits, reductions, and all
values that affect an ALLOW/REJECT decision are always checked against the
reference, even when their sample bit is false. A candidate that cannot meet
that coverage is labelled `integer_oracle`.

## 6. T39 and Lbit certificate fields

The ternary record contains:

```json
{
  "state": "REJECT|RECURSE|ALLOW",
  "state_value": -1,
  "encoding": "T39-v1",
  "input_sha256": "...",
  "canonical": true,
  "forbidden_symbol_3": false,
  "padding_valid": true,
  "recursion_remaining": 0,
  "decision_leaf": "..."
}
```

`state_value` must match the name (`-1`, `0`, `+1`). A decoder rejects symbol
3, truncation, overflow, and noncanonical tail padding before producing a
decision leaf. The certificate is invalid if the decoder silently repairs any
of them.

The Lbit record names the query commitment, ranked expert IDs, active six,
coupling commitment, collapse decision, authenticated page certificates, and
resident-cache result. It includes the exact page IDs and the source ranges
consumed. A missing or inconsistent omission certificate produces a
fail-closed record and cannot be presented as a successful sparse proof.

## 7. API envelope

`POST /ask` returns the normal response plus one `certificate` object. The
following is the minimum shape; fields not shown are versioned extensions:

```json
{
  "answer": "...",
  "certificate": {
    "version": "PocketRocket-Certificate-1",
    "session_id": "...",
    "token_index": 0,
    "token_id": 123,
    "arithmetic_mode": "integer_oracle",
    "model": {
      "file_sha256": "...",
      "file_size": 86720111488,
      "tensor_manifest_sha256": "...",
      "file_page_root": "...",
      "page_size": 4096
    },
    "significant_logits": [{
      "token_id": 123,
      "logit_bits": "3f800000",
      "probability_bits": "00000000",
      "operation_leaf": "...",
      "source_ranges": [{"tensor": "...", "offset": 0,
                         "length": 0, "page_ids": [],
                         "range_sha256": "..."}]
    }],
    "dependency_root": "...",
    "ternary": {},
    "lbit": {},
    "previous_token_root": "...",
    "token_root": "..."
  }
}
```

No JSON number is used for a binary32 result. `probability_bits` is omitted
when probability was not computed, rather than being filled with a host
float. A streaming implementation emits the token only after its certificate
record is complete; a failed certificate emits no token.

## 8. Required ds4 instrumentation boundary

The pinned ds4 runtime remains the only model executor. Certificate support
must be added at these native boundaries; a Python wrapper cannot reconstruct
the ancestry after ds4 has discarded it:

1. **GGUF parser/load manifest:** immediately after tensor metadata and
   `data_offset` are parsed, publish the tensor manifest and file-page root.
2. **SSD streaming read/cache:** wrap every `pread`/mapped-range fill with
   `(file_offset, length, tensor, page IDs, range SHA-256)`. The callback must
   run before bytes enter a dequantizer and must reject out-of-file ranges.
3. **Dequantization:** attach packed-code, scale, and codebook ranges to the
   dequantization operation leaf. A cache hit reuses the original immutable
   range digest; it does not create a new source.
4. **Router/top-k:** emit the fixed-order router logits, all 256 expert IDs in
   rank order, active six, gate weights, and routing commitment.
5. **Expert kernels and reductions:** instrument RMSNorm, SiLU, attention,
   softmax, matmul/reduction, and the six expert contribution accumulators.
   Each callback receives token/layer/sequence/op ordinal and returns output
   bits plus an operation leaf. Reduction order and contraction mode are
   explicit kernel metadata.
6. **Sampling/emission:** after the complete vocabulary vector is hashed and
   significant logits are selected, create the T39 decision record and token
   root. The emission function must take a validated certificate handle, not
   an unannotated integer token.

At the pinned commit, implementation should locate these sites by the GGUF
`data_offset` parser, SSD streaming/cache read, dequantization, router top-k,
matmul/reduction, and token-emission symbols. If a release renames a symbol,
the integration must be re-audited against the six semantic boundaries above;
adding a guessed callback in a wrapper is not sufficient.

## 9. Verification and failure policy

A verifier recomputes, in order:

1. model filename, size, header, complete file SHA-256, GGUF manifest, and
   page Merkle root;
2. all cited range bounds and raw-range hashes;
3. sampled and decision-critical arithmetic outputs using the declared graph;
4. the complete ordered logit-vector hash and significant-logit tie rule;
5. T39 canonical decoding and Lbit commitments;
6. dependency root, previous token root, and current token root.

The result is invalid on any mismatch, missing source range, unknown arithmetic
mode, unverified candidate, malformed ternary input, stale session chain, or
certificate that claims sparse omission without authenticated bounds. The
runtime may continue by recomputing the token in `integer_oracle`; it must not
silently downgrade a claimed accelerated certificate or emit an uncertified
token.

The certificate artifact can be stored as a sidecar containing all operation
leaves and Merkle proofs. The HTTP response contains the compact roots and
decision-critical proofs. This keeps the local API bounded while retaining a
complete, independently verifiable audit trail.
