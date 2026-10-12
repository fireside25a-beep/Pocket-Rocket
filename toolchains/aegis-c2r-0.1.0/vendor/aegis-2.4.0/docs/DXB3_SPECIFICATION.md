# DXB3 bytecode specification

## Encoding

All multi-byte integers are unsigned 32-bit little-endian values. The file limit is 64 MiB.

| Offset | Size | Meaning |
|---:|---:|---|
| 0 | 4 | ASCII `DXB3` |
| 4 | 1 | format version, value 3 |
| 5 | 3 | reserved, must be zero |
| 8 | 4 | payload length |
| 12 | 4 | Adler-32 of payload |
| 16 | 4 | exact capability mask |
| 20 | 4 | exact verified maximum stack depth |
| 24 | 4 | exact verified worst-case step bound |
| 28 | 4 | heap-cell budget, 1 through 65,536 |
| 32 | 4 | Adler-32 of source bytes |
| 36 | 4 | Aegis policy version, value 1 |
| 40 | variable | instruction payload |

The verifier recomputes the capability mask, maximum stack and worst-case step bound. Declared values must match exactly.

## Opcodes

| Value | Instruction | Stack effect |
|---:|---|---|
| 0 | `HALT` | none; final top-level instruction only |
| 1 | `PUSH_I32 imm32` | `-- value` |
| 2–6 | `ADD SUB MUL DIV MOD` | `a b -- result` |
| 7 | `DUP` | `a -- a a` |
| 8 | `DROP` | `a --` |
| 9 | `SWAP` | `a b -- b a` |
| 10 | `PRINT` | `value --`; requires print capability |
| 11 | `NEG` | `a -- -a` |
| 12–14 | `EQ LT LE` | `a b -- bool` |
| 15 | `ALLOC` | `cells -- handle` |
| 16 | `MGET` | `handle index -- value` |
| 17 | `MSET` | `handle index value -- handle` |
| 18 | `FREE` | `handle --` |
| 19 | `REPEAT count body_len body` | body must preserve stack depth |
| 20 | `IFZERO body_len body` | consumes condition; body must preserve merge depth |
| 21 | `ASSERT` | consumes condition and fails if zero |
| 22 | `BYTES length payload` | `-- handle`; length is u32 followed by exact bytes |
| 23 | `BLEN` | `handle -- handle length` |
| 24 | `BGET` | `handle index -- handle byte` |
| 25 | `BSET` | `handle index byte -- handle` |
| 26 | `BWRITE` | `handle -- handle`; requires byte-output capability |

`BYTES` length must be 1 through 65,536 and its payload must fit completely inside the enclosing bytecode range. `BGET`, `BSET`, `BLEN`, and `BWRITE` use generation-checked handles. Byte values are restricted to `0..255` for byte-specific operations.

`REPEAT` is bounded to 1,000,000 iterations. Structured nesting is limited to 64. A nested block cannot contain `HALT`.

## Verification

Verification fails closed on malformed headers, unsupported versions, length or checksum disagreement, unknown opcodes, truncated immediates, stack underflow/overflow, invalid structured-body lengths, mismatched stack merges, invalid metrics, excessive fuel, invalid heap budgets, missing final `HALT` or content after `HALT`.

Adler-32 is an accidental-corruption check, not a cryptographic signature. Distribution integrity is provided separately by the release SHA-256 manifest.
