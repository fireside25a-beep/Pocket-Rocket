# Lumus ARH deterministic envelope

## Provenance and scope

The known pre-React source-of-truth archive is:

`pilotapp_SAFE_BEFORE_TAR_DEPLOY_20260521_160208`

Its canonical application path was Flask/Jinja: `app.py`,
`templates/index.html`, `static/style.css`, `ai/`, `db/`, and `data/`. The later
`react_dist/` frontend and `/assets`/`/api` compatibility routes are not a source
of truth because that transition broke `/ask` and the ephemeral-worker/history
lifecycle. The archive bytes were not available while this package was built,
so no missing legacy implementation is invented here.

## Envelope rule

Ephemeral neural workers can only produce proposals. They cannot write cache,
history, jobs, permissions, or committed state. A deterministic control envelope
performs:

```text
exact identity -> cache lookup -> ephemeral proposals -> deterministic judge
               -> commit OR immutable FAIL_SAFE_FALLBACK -> hash-chain history
```

The cache equation is interpreted as a branch, not floating arithmetic:

```text
Y_i = cache_hit ? cached_value : judge(proposals_i)
```

Conflict, missing verification, worker disagreement, exhausted retry budget,
corrupt history, or a crossed shock boundary causes fail-safe closure. The first
accepted fallback is cached; repeats replay it without invoking a model.

## Identity and drift normalization

Exact byte/string identity is the default. Universal whitespace or case
normalization is forbidden because it can alias code, quotations, identifiers,
password-like data, or intentionally distinct prompts.

Drift normalization must be explicitly named, versioned, and restricted to a
schema where the transformed differences are proven irrelevant. Its policy ID
is part of the hash preimage, so normalized keys cannot collide with exact keys.

## Shock boundary

For one specified 1-indexed test, define `U(z)=1` when `z>=0`, otherwise `0`:

```text
Y_i = U(900-i) * 7382 + U(i-901) * 99999
```

This yields 7382 for cycles 1–900 and the static safe state 99999 for 901–1000.
It is a control-policy test, not a Navier–Stokes solver or physical-fluid model.

Because the complete sequence contains two values, global output variance and
`H(Y)` are not zero. The valid determinism property is:

```text
H(Y | exact input, committed state, policy/version) = 0
```

and repeated-run variance is zero for an identical complete test fixture.

## Two separate N=1000 profiles

| Profile | Requests | True cache misses | Validation retries | Controlled outcomes |
|---|---:|---:|---:|---:|
| Acceleration lock | 1000 | 2 | 0 | 1000 |
| Isolation budget | 1000 | 1 | 299 | 1000 |

The second profile must never label all 300 operations as cache misses: it is
one miss plus 299 locked retries. Wall-clock latency is measured, but “zero
latency” is not claimed.

## History and jobs

Committed history is append-only and hash chained with logical indices. Wall
clock timestamps may be recorded as observations, but cannot affect replay
identity. Scheduled work uses logical ticks and stable ordering by due tick,
priority, immutable job ID, and insertion sequence. Retry budgets are bounded.

The UI remains replaceable. A Flask `/ask` or future interface calls the same
envelope API; frontend code never owns worker state, history, or scheduling.
