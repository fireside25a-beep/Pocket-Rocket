# Native backend and ABI foundation

## Typed IR

`dxnative24 ir` lowers the supported DXS policy-v2 subset to deterministic textual `DXIR 1`, including distinct types for `owned_bytes`, `slice_bytes`, `utf8_text`, `error`, and `trit_i64`.

`dxldirect24` implements a deliberately controlled DXL native profile containing a `main` function, constant `print_i64` operations, and `return as(i32, 0)`. It lowers that source through the same typed IR/object writer. Inputs outside this grammar are rejected rather than silently interpreted.

## Direct object writer

The direct writer emits x86-64 System V ELF64 relocatable objects with:

- `.text` and `.rodata`;
- `.rela.text` using `R_X86_64_PC32`;
- `.symtab`, `.strtab`, and `.shstrtab`;
- `.debug_line` and `.rela.debug_line`;
- `.note.GNU-stack`.

## Calling convention

The exported entry is:

```text
int main(void)
```

It follows the x86-64 System V ABI, returns zero in `EAX`, preserves the platform stack contract, and writes prevalidated output with the Linux x86-64 `write` system call. The object is linked by a supported host C linker command:

```sh
cc program.o -o program
```

This contract is Linux x86-64 specific. Windows, macOS, AArch64, dynamic libraries, foreign calls, unwinding, and a native allocator ABI are not implemented here.

## Differential execution

The controlled suite compares:

- C DXB3 VM output;
- DXL DXB3 VM output;
- linked direct ELF output;
- for the controlled DXL profile, the canonical `dxlc` executable output and direct ELF output.

The current DXS object writer specializes a closed successful bounded program to its canonical output. It is a backend foundation, not yet a general instruction-by-instruction native compiler.
