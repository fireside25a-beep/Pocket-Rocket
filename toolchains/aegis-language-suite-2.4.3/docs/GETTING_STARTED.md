# Getting started with Aegis 2.4.3

This guide verifies the bundled toolchain, builds and runs a native DXL counter, checks a broader DXL compile-time example, and executes equivalent DXS and DXASM counters through DXB3.

## Requirements

The supported host profile is:

- Linux;
- x86-64;
- glibc 2.34 or newer;
- `make` and common command-line utilities including `getconf`, `sha256sum`, `install`, `timeout`, `cmp`, `diff`, `awk`, `grep`, `sed`, `stat`, `mktemp`, `file`, `readelf`, `seq`, and `rg`.

The complete maintainer gate additionally uses `objdump` and a compatible host executable builder for source-reproduction tests. Release packaging uses `zip`, `unzip`, and `touch`. Setup and ordinary public commands require no network access or system-wide installation.

## Set up the toolchain

```sh
make setup
```

Setup:

1. checks the host operating system and architecture;
2. verifies every bundled tool and internal data file against [`toolchain/linux-x86_64/SHA256SUMS.txt`](../toolchain/linux-x86_64/SHA256SUMS.txt);
3. copies verified public commands into `build/bin/` and internal engines into `build/libexec/`.

Nothing is installed outside this repository.

## Build a native DXL loop

```sh
./build/bin/dxlc build examples/loops/dxl/native_counter.dxl -o build/native-counter
./build/native-counter
```

Output:

```text
10
```

The compiler writes a static Linux x86-64 executable directly. The same path is available as one command:

```sh
./build/bin/dxlc run examples/loops/dxl/native_counter.dxl
```

Run native-core test blocks with:

```sh
./build/bin/dxlc test tests/native/positive/assertions.dxl
```

See [DXL native core profile](NATIVE_PROFILE.md) before using `build`, `run`, or `test`; it lists the exact accepted syntax, limits, exit statuses, and nonclaims.

## Check the broader DXL profile

The general DXL counter uses a compile-time function and assertion:

```sh
./build/bin/dxlc check examples/loops/dxl/counter.dxl
./build/bin/dxlc emit-tir examples/loops/dxl/counter.dxl -o build/dxl-counter.tir
```

This source is valid for the general compatibility profile. It intentionally uses constructs outside the 2.4.3 native core profile.

## Run the DXS counter

```sh
./build/bin/dxscc examples/loops/dxs/counter.dxs build/dxs-counter.dxb
./build/bin/dxaudit build/dxs-counter.dxb
./build/bin/dxvm build/dxs-counter.dxb examples/policy_all.bin build/dxs-counter.proof
```

The VM prints `10` and writes a deterministic proof record.

## Run the DXASM counter

```sh
./build/bin/dxasm examples/loops/dxasm/counter.dxasm build/dxasm-counter.dxb
./build/bin/dxaudit build/dxasm-counter.dxb
./build/bin/dxvm build/dxasm-counter.dxb examples/policy_all.bin build/dxasm-counter.proof
```

This path also prints `10` and writes a deterministic proof record.

## Verify the installed release surface

```sh
make check
```

This runs the public regressions, native shipped-compiler matrix, cross-language loop matrix, static repository checks, and release inventory. To rebuild DXL-authored tools from their sources and run every compiler-foundation suite, use:

```sh
make maintainer-check
```

The maintainer gate has the additional build-tool requirements listed above.

Committed evidence can be verified independently:

```sh
(cd proofs/loops && sha256sum -c SHA256SUMS.txt)
sha256sum -c SHA256SUMS.txt
```

Continue with the [Toolchain guide](TOOLCHAIN.md), [Testing guide](TESTING.md), and the individual language references.
