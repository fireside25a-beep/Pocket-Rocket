# Native NPRQ control core

This directory contains the strict C11 reference layer for the NPRQ v2 page
format and the 256-bit routing control plane. It is deliberately a reader and
validator, not a transformer implementation.

NPRQ v2 pages are raw stage files produced by the Python encoder. A page has
one little-endian IEEE-754 binary16 scale followed by `block_size / 4` bytes of
packed two-bit symbols for every block. Symbol values `0..3` map to
`{-3,-1,+1,+3}`. Because the raw page has no header, callers must provide the
authenticated `block_size` and `numel` in `nprq_page_spec`.

The validator requires an exact file length, rejects non-finite scales, and can
also compare the complete page against a manifest SHA-256. Decoding never
writes padded elements beyond `numel`. Ranking is sorted by the explicit pair
`(Hamming distance, expert_id)`, so equal-distance results cannot depend on
library sort stability.

The legacy Python decoder's ternary payloads use `{-1,0,+1}` and reject the
reserved two-bit symbol `3`; native v2 pages use the signed-quaternary alphabet
`{-3,-1,+1,+3}`. Their metadata selects the format—payload contents never do.
Python conversion additionally rejects any residual stage whose stored-scale
SSE increases. Corruption tests cover hashes, invalid symbols, non-finite
scales, truncation, and trailing bytes.

The envelope in `envelope.c` uses exact input bytes as the default identity.
`nr_envelope_drift_key` is a separate, versioned whitespace-drift namespace;
it must not be used for prompts or code where whitespace is semantic. A
request that misses takes the fixed first-miss lock and must be committed or
aborted before another key can enter. Conflicts, shock scores, and a full
cache return the literal `FAIL_SAFE_FALLBACK` decision. Fallback keys are
bounded and immutable, so repeated unsafe inputs are deterministic fallback
hits. Counters include requests, controlled outputs, misses, validation
retries, conditional checks/pass/fail, and fallback hits.

The envelope test reports two deterministic N=1000 profiles: a low-miss
profile with 2 misses and 0 retries, and a first-miss-lock profile with 1 miss
and 299 validation retries. Neither profile claims a model-quality or global
entropy result.

The standalone `_flat32.dict` file is parsed by `flat32_dict_parse_bytes`.
The parser accepts only the Python-compatible `NRDICT32` version-1/flags-0
46-byte little-endian header, checks the exact `46 + count * 32` file length,
the payload SHA-256, the 256-entry bound, and uniqueness of every 32-byte
entry. The resulting fixed-capacity dictionary is passed directly to the
Flat32 stream validator/decoder; the parser performs no unbounded allocation.

`binary32.c` provides the `neuro-inverse-binary32-conformance-v1` arithmetic
contract used by the runtime audit. Add and multiply first use an integer-only
reference implementing canonical NaNs, round-to-nearest ties-to-even, signed
zero, gradual subnormals, and IEEE overflow/invalid rules. Hardware candidates
are accepted only after bitwise comparison with that reference; disagreement
increments the mismatch/fallback counters and returns the reference result.
The native test embeds the same edge and seeded cases as
`tests/data/binary32_vectors.json`.

Run the deterministic generated-vector and corruption tests from the project
root:

```sh
make -C native test
make -C native test-asan
make -C native test-ubsan
make -C native test-clang   # when clang is installed
```
