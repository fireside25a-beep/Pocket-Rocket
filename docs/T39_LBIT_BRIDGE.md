# T39 Lbit validation bridge

The native bridge adds one exact, low-C validation token to the existing Lbit
control plane. It is not a second router or a tensor runtime.

T39 is a signed 39-trit balanced-ternary integer:

\[
-\frac{3^{39}-1}{2} \le x \le \frac{3^{39}-1}{2}
= 2{,}026{,}277{,}576{,}509{,}488{,}133.
\]

`nr_t39_pack` stores the unique unsigned code `x + T39_MAX` in eight
little-endian octets. This is exactly the base-3 representation obtained by
mapping each balanced trit `-1, 0, +1` to digit `0, 1, 2`. Codes greater than
`3^39 - 1` are noncanonical and fail closed. Add, subtract, multiply, and
negate reject every result outside the T39 domain; no signed-overflowing C
expression is used.

`nr_t39_lbit_validate` commits existing route evidence into one token:

| Trits | Existing Lbit evidence |
|---|---|
| 0–5 | `256 - Hamming distance` |
| 6–11 | negative stable expert rank |
| 12 | authenticated omission certificate decision |
| 13 | coupling-closure decision |
| 14 | resident/process-budget decision |
| 15 | registry-integrity decision |
| 16–38 | canonical zero |

Every decision is exactly `-1`, `0`, or `+1`. The result is `REJECT (-1)` when
any gate is negative, `RECURSE (0)` when no gate is negative but at least one
is unresolved, and `ALLOW (+1)` only when all four gates are positive.
Malformed evidence, invalid trits, noncanonical bytes, or arithmetic overflow
fails closed to rejection. The packed token can therefore be logged or
committed beside the current Lbit selection without changing model evaluation.

Run `make -C native test`, `test-asan`, and `test-ubsan`. The native suite
covers both extrema, canonical byte fixtures, the first rejected encoding,
checked-operation overflow, invalid trits/evidence, fail-closed collapse, and
10,000 deterministic pack/trit round trips.
