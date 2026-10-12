# DXASM language reference

DXASM is the explicit textual assembly notation for DXB3. Source files use `.dxasm`; `#` starts a line comment.

```dxasm
PUSH 40
PUSH 2
ADD
PUSH 3
MUL
PRINT
HALT
```

## Mnemonics

`PUSH`, `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `DUP`, `DROP`, `SWAP`, `PRINT`, `NEG`, `EQ`, `LT`, `LE`, `ALLOC`, `MGET`, `MSET`, `FREE`, `ASSERT`, `BLEN`, `BGET`, `BSET`, `BWRITE`, and `HALT` map directly to bytecode operations.

Structured blocks use `REPEAT count`, `IFZERO`, and `END`. Exact byte literals use `BYTES:HEX`.

The assembler validates operands, block structure, instruction order, stack effects, resource bounds, and final termination before writing the bytecode artifact.

```sh
dxasm program.dxasm program.dxb
dxaudit program.dxb
dxvm program.dxb policy.bin program.proof
```
