# Native core profile test matrix

`test_native.sh` first builds the DXL-authored profile compiler from the pinned
frontend seed, then validates the independent native path.

The matrix covers deterministic compiler seeding, repeated byte identity,
source-dependent output, static ELF structure, exact runtime output, real test
blocks, failed assertions, all four checked-arithmetic traps, loop-fuel
exhaustion, stable negative diagnostics, type rejection, and syntax nesting.
Its environment supplies an unusable `PATH` and poisons conventional external
compiler variables. When process tracing is permitted, the matrix additionally
requires exactly one `execve`: the profile compiler itself. Restricted hosts
fall back to a source scan that rejects process-launch primitives.

The initial seed construction is not a self-hosting stage and is kept distinct
from the no-subprocess proof for profile compilation.
