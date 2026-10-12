# Ternary architecture

## Semantic model

Aegis 2.4 adds balanced ternary values with trits in `{-1, 0, +1}`. Source literals use:

```text
t:+0-
TRIT:+0-
```

The canonical numeric interpretation is most-significant trit first. `+0-` is decimal `8`. `trit::not` performs checked sign inversion and produces `-8`.

## Storage and execution

Ordinary target CPUs and object formats are binary. Aegis therefore stores ternary literals in packed binary form using base-3 digits, five trits per byte. The DXB3 instruction records the trit count and packed payload. Both C and DXL implementations decode the same canonical value.

This design avoids pretending that binary hardware is physically ternary. It also avoids expanding each trit to a full byte. The permitted maximum is 40 trits, whose complete balanced range fits in signed 64-bit arithmetic.

## Security properties

- invalid trit symbols are rejected;
- malformed packed counts are rejected;
- checked ternary negation rejects signed overflow;
- source, bytecode, output, and proof agreement remain fail closed;
- a sanitizer-discovered signed-overflow defect in the first decoder implementation was repaired before packaging.

## Performance boundary

No claim is made that ternary operations are free. Measurements are supplied in `proofs/measurements.csv`. They cover a tiny controlled application and include process startup. They are evidence, not a language-wide benchmark.
