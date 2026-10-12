# Aegis 2.4.0 — Source Bootstrap Release

Aegis 2.4.0 contains the complete DXL, DXS, DXASM, and DXB3 source tree together with an auditable stage-zero bootstrap. It is intended for compiler researchers and users who want to trace the build chain from a small bootstrap source into the DXL-authored tools.

## Requirements

- POSIX-like environment;
- Bash and Make;
- `cc` with C11 support for stage zero;
- Clang for the current DXL native-backend path.

## Build and test

```sh
make bootstrap
make toolchain
make test
make check
```

| Target | Action |
| --- | --- |
| `make bootstrap` | Compiles `bootstrap/dxlc_stage0.c` into `build/bin/dxlc` |
| `make toolchain` | Uses stage zero to construct the DXL-authored tools |
| `make test` | Runs DXL, DXS, DXASM, VM, audit, and determinism tests |
| `make check` | Runs the complete source-release gate |
| `make clean` | Removes locally generated build output |

Nothing is installed system-wide. Generated executables are written under `build/bin/`.

## Bootstrap architecture

```text
bootstrap/dxlc_stage0.c ──> cc ──> stage-zero dxlc
                                      │
                                      ├──> compiler/dxs/*.dxl ──> dxscc
                                      ├──> compiler/dxasm/*.dxl ─> dxasm
                                      └──> runtime/dxb3/*.dxl ───> dxvm + dxaudit
```

The DXL files in `compiler/` and `runtime/` are the canonical implementation of the higher toolchain layers. The stage-zero source exists to break the initial compiler dependency cycle; it is not an alternative implementation of DXS, DXASM, or DXB3.

## Commands after building

```sh
build/bin/dxlc check examples/dxl/hello.dxl
build/bin/dxlc run examples/dxl/hello.dxl

build/bin/dxscc examples/dxs/arithmetic.dxs build/arithmetic.dxb
build/bin/dxaudit build/arithmetic.dxb
build/bin/dxvm build/arithmetic.dxb examples/policy_all.bin build/arithmetic.proof

build/bin/dxasm examples/dxasm/arithmetic.dxasm build/arithmetic-asm.dxb
build/bin/dxvm build/arithmetic-asm.dxb examples/policy_all.bin build/arithmetic-asm.proof
```

## Source of truth

The 45 `.dxl` files in this release are byte-identical to the DXL source files shipped by Aegis 2.4.1. The two releases differ primarily at the initial bootstrap boundary.

## Status

This release is partially self-hosted: DXS, DXASM, the DXB3 VM, and associated tooling are authored in DXL. Complete stage-to-stage reproduction of the DXL frontend is not claimed.

See the repository-level [bootstrap documentation](../../docs/BOOTSTRAP.md) and [implementation status](../../docs/IMPLEMENTATION_STATUS.md).

## License

MIT. See the repository-level [`LICENSE`](../../LICENSE).
