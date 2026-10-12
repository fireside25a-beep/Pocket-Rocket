# DXS language reference

DXS is a compact deterministic scripting language compiled to verified DXB3 bytecode. Tokens are separated by whitespace; `#` starts a line comment.

```dxs
40 2 +
3 *
print
halt
```

## Core words

| Group | Words |
|---|---|
| Arithmetic | `+`, `-`, `*`, `/`, `%`, `neg` |
| Stack | `dup`, `drop`, `swap` |
| Comparison | `eq`, `lt`, `le` |
| Control | `repeat:N ... end`, `ifzero ... end`, `halt` |
| Validation | `assert` |
| Memory | `alloc`, `mget`, `mset`, `free` |
| Bytes | `bytes:HEX`, `blen`, `bget`, `bset`, `bwrite` |
| Output | `print` |

Signed decimal literals push values. The compiler rejects unknown words, malformed numbers, instructions after `halt`, unbalanced blocks, and programs that fail structural verification.

DXB3 verification derives stack depth, maximum steps, required capabilities, and heap bounds before execution. Runtime arithmetic and memory access remain checked.

```sh
dxscc program.dxs program.dxb
dxaudit program.dxb
dxvm program.dxb policy.bin program.proof
```
