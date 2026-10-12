# Binary32 numeric contract

`neuro_inverse.binary32` is a dependency-light reference for binary32 add,
multiply, divide, and square root. It consumes and returns unsigned 32-bit
encodings. The reference
path uses integer operations and `fractions.Fraction`; it does not use NumPy or
host floating-point arithmetic as its oracle.

## Required behavior

- Round-to-nearest, ties-to-even for normal and subnormal results.
- Gradual underflow with the binary32 minimum subnormal quantum `2^-149`.
- Overflow rounds to signed infinity.
- All NaN inputs and invalid operations return canonical quiet NaN
  `0x7fc00000`, independent of payload or sign.
- `+0 + -0` and exact finite cancellation return `+0`; `-0 + -0` returns
  `-0`. Multiplication uses XOR of operand signs, including signed zero and
  infinity results.
- `+inf + -inf` and infinity times zero are invalid and return canonical NaN.
- Division by zero returns signed infinity for a nonzero finite numerator;
  zero divided by zero and infinity divided by infinity are invalid.
- Square root of a negative nonzero value is invalid; square root preserves
  signed zero and maps positive infinity to positive infinity.

For a positive exact finite result `v`, the reference rounds an integer ratio
at the selected binary quantum. If the quotient remainder is exactly half, the
least-significant result bit is retained only when the quotient is odd. This
is the integer form of round-to-nearest-ties-to-even and avoids an implicit
double-round through a host `float`.

## Candidate hardware path

`evaluate_candidate(operation, left_bits, right_bits, candidate)` and
`evaluate_unary_candidate("sqrt", value_bits, candidate)` compute the reference
result first. A candidate is accepted only when it returns the exact same
32-bit encoding, including NaN canonicalization and signed zero. A bad,
malformed, or raising candidate is recorded as a mismatch and the exact
reference result is returned. No heuristic candidate can silently become the
numeric authority.

`dot_product_bits` uses only reference multiply and add. Its default is fixed
left-to-right accumulation; `pairwise=True` selects a separate balanced tree
and is allowed to round differently.

## Conformance artifact

`tests/data/binary32_vectors.json` contains 44 edge cases plus 64 seeded finite
random vectors (`seed=20260817`). It covers NaNs, invalid infinities, signed
zeros, max-finite overflow, normal/subnormal boundaries, gradual underflow,
halfway ties, division, and square root. The deterministic file SHA-256 is
`3413975bda7eb16c1d9a006e3ce379e056f7bb1b624eed0838ca54e47b0534ce`.
Regenerate it with:

```bash
PYTHONPATH=src python scripts/generate_binary32_vectors.py
```

This contract is a software reference and conformance gate. It does not claim
that any DPU, GPU, compiler, or Rendr implementation produces identical bits
until that implementation passes these vectors.
