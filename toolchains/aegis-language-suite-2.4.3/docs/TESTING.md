# Testing Aegis 2.4.3

Aegis separates the installed release gate from maintainer source-reproduction gates. This makes the dependency boundary explicit while still requiring every layer before packaging an official archive.

## Host and test dependencies

The supported bundled-tool host is Linux x86-64 with glibc 2.34 or newer.

The public gate uses `make`, `getconf`, `sha256sum`, `install`, `timeout`, `cmp`, `diff`, `awk`, `grep`, `sed`, `stat`, `mktemp`, `file`, `readelf`, `seq`, and `rg`.

Maintainer compiler-foundation tests additionally use `objdump` and a compatible host executable builder. Deterministic source-to-shipped byte reproduction is pinned in CI to Ubuntu 24.04 x86-64, glibc 2.39, and the distribution's version 13.3.0 host builder. Other supported runtime hosts may execute the binaries correctly while producing different seed bytes in `make reproduce`.

Release packaging additionally uses `zip`, `unzip`, and `touch`.

Disposable generated work stays under `build/`, `dist/`, or a temporary directory. `make matrix` is the documented exception: it refreshes tracked evidence under `proofs/loops/`.

## Public gate map

| Command | What it validates |
| --- | --- |
| `make setup` | Host ABI, bundled checksums, and local installation |
| `make regressions` | Public DXL/DXS/DXASM/DXB3 commands, corpora, diagnostics, and repeat artifacts |
| `make native` | Shipped DXL-native compiler matrix without rebuilding the compiler seed |
| `make matrix` | General DXL TIR, native DXL executable, DXS/DXASM DXB3, output, audit, and proof evidence |
| `make static` | Version consistency, manifests, source hygiene, links, shell syntax, diagnostics, commands, and source checks |
| `make verify` | Required source, executable, test, proof, and documentation inventory |
| `make test` | `regressions` + shipped `native` + cross-language `matrix` |
| `make check` | Complete installed release gate: `test` + `static` + `verify` |

Run the installed gate with:

```sh
make clean
make check
```

`make check` uses the checksum-pinned `dxlc-native`; it does not rebuild compiler executables.

## Maintainer gate map

| Command | What it validates |
| --- | --- |
| `make native-source` | Builds the DXL native compiler twice, compares both, matches the shipped seed, then runs the native matrix |
| `make foundations-native` | Focused lexer, parser-arena/recovery, and fixed object-layout component suites |
| `make frontend` | Integrated lexer→parser→semantics→typed-IR suite |
| `make foundations` | Focused component suites plus integrated frontend suite |
| `make reproduce` | Rebuilds seven DXL-authored tools twice and compares with shipped bytes |
| `make maintainer-check` | Public `check` plus all source, foundation, and reproduction gates |
| `make release` | `maintainer-check`, deterministic packaging, extraction, and a fresh extracted `make check` |

Before publishing:

```sh
make clean
make maintainer-check
make release
```

The CI workflow runs the component gates independently and blocks artifact publication on any failure.

## Public regression coverage

[`scripts/test.sh`](../scripts/test.sh) exercises:

- general DXL checking, formatting, typed-IR repeat identity, positive programs, and negative programs;
- native DXL build/run/test, repeat executable identity, exact output, exact diagnostics, command-mode separation, source-size preflight, failed-output preservation, and invalid targets;
- native compilation in an isolated layout containing no compatibility frontend;
- DXS compilation, audit, execution, negative rejection, and byte identity;
- DXASM assembly, audit, execution, negative rejection, and byte identity;
- the extended DXS/DXB3 profile pair with repeat bytecode, output, and proof identity.

Every command is time bounded. A negative case passes only on a non-timeout rejection.

## Native compiler matrix

[`tests/native/test_native.sh`](../tests/native/test_native.sh) has two modes:

- `AEGIS_NATIVE_MODE=shipped` uses the checksum-pinned compiler and requires no seed rebuild;
- `AEGIS_NATIVE_MODE=source` checks the compiler source, builds it twice, compares the builds, and requires an exact match with the shipped compiler.

Both modes then verify:

- repeat source-to-executable byte identity;
- distinct outputs for distinct sources;
- exact counter, branch, and signed-integer output;
- static ELF64 shape, one load segment, no interpreter/dynamic dependency, and non-executable stack;
- direct compilation with compiler/build-tool paths poisoned;
- native test blocks, short-circuit behavior, and rejection of early test returns;
- overflow/cast status `70`, assertion status `71`, loop-fuel status `72`, and invalid-return status `73`;
- exact acceptance of 1,000,000 loop-condition evaluations and rejection of evaluation 1,000,001;
- accepted user exit `63` plus deterministic rejection of reserved and negative returns;
- lexical scope, total return, types, source size, and expression/block/unary nesting;
- exact numeric diagnostic rejection and no failed output artifact.

## Integrated frontend matrix

[`tests/selfhost/full/test_full_frontend.sh`](../tests/selfhost/full/test_full_frontend.sh) builds the ten-module implementation with the pinned frontend and runs arbitrary input through the new DXL-native pipeline. It verifies:

- deterministic frontend executable and output bytes;
- token, AST, symbol, typed-expression, and TIR counts;
- one-literal mutation sensitivity;
- maximum and derived-minimum integers without digest overflow;
- forward inference beyond eight links;
- multiple exact syntax and semantic diagnostics;
- expression and statement recursion rejection;
- unknown aggregate fail-closed behavior;
- end-to-end acceptance of the bounded model module;
- explicit, deterministic rejection at the remaining full-source semantic boundary.

The runner parses the integrated entry module; the pinned frontend separately checks and builds its import closure. This gate is not a self-hosting stage test.

## Focused compiler foundations

[`scripts/test_foundations.sh`](../scripts/test_foundations.sh) invokes:

1. the table lexer and diagnostic suite, including every token kind, source coordinates, multiple errors, bounds, and repeat builds;
2. the parser arena/recovery suite, including synchronization progress and deterministic output;
3. the fixed relocatable-object writer suite, including sections, symbols, relocation, minimal line data, bounds, and golden bytes.

The fixed object writer is a layout fixture. The source-dependent native executable backend is tested separately.

## DXL-authored tool reproduction

[`scripts/reproduce_toolchain.sh`](../scripts/reproduce_toolchain.sh) creates fresh isolated source groups, builds each twice, compares repeat bytes, and matches the bundled executable. It covers `dxscc`, `dxasm`, `dxvm`, `dxaudit`, `dxs24cc`, `dxvm24`, and `dxlc-native`.

This proves deterministic source-to-seed reproduction in the pinned maintainer environment. It does not prove that `dxlc-native` compiles itself.

## Cross-language loop matrix

[`scripts/test_loop_matrix.sh`](../scripts/test_loop_matrix.sh) uses:

- [general DXL compile-time counter](../examples/loops/dxl/counter.dxl);
- [native DXL runtime counter](../examples/loops/dxl/native_counter.dxl);
- [DXS counter](../examples/loops/dxs/counter.dxs);
- [DXASM counter](../examples/loops/dxasm/counter.dxasm).

| Path | Repeat comparison | Execution/evaluation | Committed evidence |
| --- | --- | --- | --- |
| General DXL | Check transcript and TIR | Compile-time assertion reaches `10` | `.check`, `.tir` |
| Native DXL | Static executable bytes and output | Native process prints `10` | `.bin`, `.audit`, `.out` |
| DXS | DXB3, output, proof | Audited VM prints `10` | `.dxb`, `.audit`, `.proof`, `.out` |
| DXASM | DXB3, output, proof | Audited VM prints `10` | `.dxb`, `.audit`, `.proof`, `.out` |

The matrix compares all three runtime outputs. Native DXL evidence is not called a DXB3 proof.

Regenerate and verify:

```sh
make matrix
(cd proofs/loops && sha256sum -c SHA256SUMS.txt)
```

## Adding coverage

- General DXL positives: `tests/dxl/`
- General DXL negatives: `tests/negative/`
- Native DXL: `tests/native/positive/` and `tests/native/negative/`
- DXS: `tests/dxs/positive/` and `tests/dxs/negative/`
- DXASM: `tests/dxasm/positive/` and `tests/dxasm/negative/`
- Compiler frontend/foundations: `tests/selfhost/`
- Cross-language fixtures: `tests/matrix/`

A new feature requires positive behavior, negative diagnostics, deterministic repeat output, integration behavior, and matching documentation before it becomes a release claim.
