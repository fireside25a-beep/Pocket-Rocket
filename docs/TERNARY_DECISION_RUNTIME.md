# Exact ternary decision runtime

## Scope

Pocket Rocket 0.2 has a real three-state decision plane. `reject`, `abstain`,
and `accept` are the semantic values `-1`, `0`, and `+1`; the middle state is
not a Boolean confidence label. Choice operations also abstain on an exact tie
or an insufficient exact margin.

The arithmetic does not use host floating point:

- weights and scores are canonical triadic rationals `n / 3^k`;
- general decision-boundary values use reduced integer rationals;
- ternary vectors are disjoint positive and negative sign planes;
- dot products are `popcount(same signs) - popcount(opposite signs)`;
- certificates serialize integer numerators and powers, never JSON decimals.

`native/ternary_core.c` is a strict C11 bounded fast path. It rejects rather
than rounds when an exact intermediate exceeds its `int64_t` range. The Python
semantic path is unbounded and is the canonical implementation for decisions.

## Surreal-number boundary

The surreal numbers are a proper class, so no finite application can contain
the “full universe.” Pocket Rocket implements the computable values it uses:
exact dyadics for binary-aligned I/O quantities, exact triadics for ternary
scales, and reduced rationals for certificates. These are genuine surreal
values mathematically; they are not floating-point translations. The project
does not mislabel a finite representation as all surreal numbers.

## Typed local decisions

The primitives are deliberately small:

- `Criterion` is an exact score and exact weight.
- `gate` combines criteria and returns one ternary status.
- `Choice` selects a unique highest exact score or abstains.
- `ScoreLevel` carries non-negative triadic support for an ordered label.
- `ordered_score` produces the exact normalized distribution, exact expected
  ordinal score, and exact peak-versus-runner confidence. A tie or confidence
  below the requested rational threshold is semantic `abstain`.
- `route-decide` feeds the existing local 256-bit expert router into `Choice`
  and binds the request, expert index, route distances, margin, and result into
  a SHA-256 certificate.

This structure is influenced by Jev's Choice/Score and confidence-gated
decision patterns, but it does not call Jev, copy its implementation, parse
model-generated JSON, or send prompts to an external service.

## Commands

```sh
PYTHONPATH=src python -m neuro_inverse ternary-dot -- '-0++' '+0+-'

PYTHONPATH=src python -m neuro_inverse decide \
  --criterion safety:2:1 \
  --criterion quality:1:1:2:0 \
  --reject-below=-1:0 --accept-at=1:0 \
  --model-root "$(printf '%064d' 0)" \
  --request-root "$(printf '%064d' 0)"

PYTHONPATH=src python -m neuro_inverse route-decide \
  'review this parser' --minimum-margin 2

PYTHONPATH=src python -m neuro_inverse score \
  --level low:1:0 --level medium:2:0 --level high:6:0 \
  --minimum-confidence 1:3 \
  --model-root 0000000000000000000000000000000000000000000000000000000000000000 \
  --request-root 1111111111111111111111111111111111111111111111111111111111111111
```

The criterion grammar is
`NAME:SCORE_NUM:SCORE_POWER[:WEIGHT_NUM:WEIGHT_POWER]`.
The ordered-level grammar is `NAME:SUPPORT_NUM:SUPPORT_POWER`; confidence is
`NUMERATOR:DENOMINATOR`. All emitted values are reduced integer rationals.

## Non-goals and hard boundary

This decision plane does not convert DeepSeek's GGUF tensors or DwarfStar's
upstream compute kernels to ternary. The existing chat path remains the pinned
upstream model path and must not be advertised as ternary inference. A full
model conversion requires the verified 86,720,111,488-byte model, a tensor-by-
tensor calibration record, graph coverage, and measured output-quality and
16 GiB gates. Those gates cannot be inferred from unit tests.
